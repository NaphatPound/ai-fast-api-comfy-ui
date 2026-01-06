import os
import json
import uuid
import asyncio
import httpx
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import websockets
from contextlib import asynccontextmanager

load_dotenv()

COMFY_URL = os.getenv("COMFY_URL", "http://192.168.1.7:8188")
COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "./output")
WORKFLOW_PATH = os.getenv("WORKFLOW_PATH", "./workflow_api.json")

os.makedirs(COMFY_OUTPUT_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting FastAPI ComfyUI Bridge")
    print(f"ComfyUI URL: {COMFY_URL}")
    print(f"Output Directory: {COMFY_OUTPUT_DIR}")
    yield
    print("Shutting down FastAPI ComfyUI Bridge")


app = FastAPI(
    title="ComfyUI Bridge API",
    description="FastAPI bridge to control a remote ComfyUI server",
    version="1.0.0",
    lifespan=lifespan
)


class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., description="Positive prompt text for image generation")
    negative_prompt: Optional[str] = Field("", description="Negative prompt text (optional)")


class GenerateImageResponse(BaseModel):
    status: str
    message: str
    image_path: Optional[str] = None
    prompt_id: Optional[str] = None


class ComfyUIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")

    def load_workflow(self, workflow_path: str) -> Dict[str, Any]:
        try:
            with open(workflow_path, "r", encoding="utf-8") as f:
                workflow = json.load(f)
            return workflow
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail=f"Workflow file not found: {workflow_path}. Please place your workflow_api.json in the project root."
            )
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=500,
                detail="Invalid workflow JSON file"
            )

    def modify_workflow(
        self,
        workflow: Dict[str, Any],
        positive_prompt: str,
        negative_prompt: str = ""
    ) -> Dict[str, Any]:
        modified = False

        for node_id, node_data in workflow.items():
            if isinstance(node_data, dict):
                class_type = node_data.get("class_type", "")

                if class_type == "CLIPTextEncode":
                    inputs = node_data.get("inputs", {})
                    current_text = inputs.get("text", "")

                    if "negative" in current_text.lower() or "bad" in current_text.lower():
                        inputs["text"] = negative_prompt
                        print(f"Set negative prompt in node {node_id}")
                    else:
                        inputs["text"] = positive_prompt
                        print(f"Set positive prompt in node {node_id}")
                    modified = True

                elif class_type == "KSampler":
                    inputs = node_data.get("inputs", {})
                    inputs["seed"] = uuid.uuid4().int % (2**32)
                    print(f"Randomized seed in node {node_id}: {inputs['seed']}")
                    modified = True

        if not modified:
            print("Warning: No CLIPTextEncode or KSampler nodes found in workflow")

        return workflow

    async def queue_prompt(self, workflow: Dict[str, Any]) -> str:
        payload = {"prompt": workflow}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(f"{self.base_url}/prompt", json=payload)
                response.raise_for_status()
                result = response.json()
                prompt_id = result.get("prompt_id")

                if not prompt_id:
                    raise HTTPException(status_code=500, detail="No prompt_id returned from ComfyUI")

                print(f"Queued prompt with ID: {prompt_id}")
                return prompt_id

            except httpx.HTTPError as e:
                raise HTTPException(
                    status_code=503,
                    detail=f"Failed to connect to ComfyUI at {self.base_url}: {str(e)}"
                )

    async def wait_for_completion(self, prompt_id: str, timeout: int = 300) -> bool:
        ws_url = f"{self.ws_url}/ws?clientId={uuid.uuid4()}"

        try:
            async with websockets.connect(ws_url) as websocket:
                print(f"Connected to ComfyUI websocket")
                start_time = asyncio.get_event_loop().time()

                while True:
                    if asyncio.get_event_loop().time() - start_time > timeout:
                        raise HTTPException(status_code=504, detail="Timeout waiting for image generation")

                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        data = json.loads(message)

                        msg_type = data.get("type")

                        if msg_type == "executing":
                            exec_data = data.get("data", {})
                            exec_prompt_id = exec_data.get("prompt_id")
                            node = exec_data.get("node")

                            if exec_prompt_id == prompt_id and node is None:
                                print(f"Execution completed for prompt {prompt_id}")
                                return True

                        elif msg_type == "execution_error":
                            error_data = data.get("data", {})
                            if error_data.get("prompt_id") == prompt_id:
                                raise HTTPException(
                                    status_code=500,
                                    detail=f"ComfyUI execution error: {error_data}"
                                )

                    except asyncio.TimeoutError:
                        continue

        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=500,
                detail=f"WebSocket error: {str(e)}"
            )

    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(f"{self.base_url}/history/{prompt_id}")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get history: {str(e)}"
                )

    async def download_image(self, prompt_id: str, output_dir: str) -> str:
        history = await self.get_history(prompt_id)

        if prompt_id not in history:
            raise HTTPException(status_code=404, detail="Prompt ID not found in history")

        outputs = history[prompt_id].get("outputs", {})

        image_info = None
        for node_id, node_output in outputs.items():
            if "images" in node_output and len(node_output["images"]) > 0:
                image_info = node_output["images"][0]
                break

        if not image_info:
            raise HTTPException(status_code=404, detail="No output images found")

        filename = image_info.get("filename")
        subfolder = image_info.get("subfolder", "")
        folder_type = image_info.get("type", "output")

        if not filename:
            raise HTTPException(status_code=500, detail="No filename in output")

        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.get(f"{self.base_url}/view", params=params)
                response.raise_for_status()

                output_path = Path(output_dir) / f"{prompt_id}_{filename}"

                with open(output_path, "wb") as f:
                    f.write(response.content)

                print(f"Image saved to: {output_path}")
                return str(output_path)

            except httpx.HTTPError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to download image: {str(e)}"
                )


client = ComfyUIClient(COMFY_URL)


@app.get("/")
async def root():
    return {
        "message": "ComfyUI Bridge API is running",
        "comfy_url": COMFY_URL,
        "endpoints": {
            "generate_image": "/generate-image (POST)",
            "health": "/health (GET)"
        }
    }


@app.get("/health")
async def health_check():
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            response = await http_client.get(f"{COMFY_URL}/system_stats")
            response.raise_for_status()
            return {
                "status": "healthy",
                "comfy_ui": "online",
                "comfy_url": COMFY_URL
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "comfy_ui": "offline",
            "comfy_url": COMFY_URL,
            "error": str(e)
        }


@app.post("/generate-image", response_model=GenerateImageResponse)
async def generate_image(request: GenerateImageRequest):
    try:
        print(f"\n{'='*60}")
        print(f"New image generation request")
        print(f"Positive prompt: {request.prompt[:100]}...")
        print(f"Negative prompt: {request.negative_prompt[:100] if request.negative_prompt else 'None'}...")
        print(f"{'='*60}\n")

        workflow = client.load_workflow(WORKFLOW_PATH)

        modified_workflow = client.modify_workflow(
            workflow,
            positive_prompt=request.prompt,
            negative_prompt=request.negative_prompt
        )

        prompt_id = await client.queue_prompt(modified_workflow)

        await client.wait_for_completion(prompt_id)

        image_path = await client.download_image(prompt_id, COMFY_OUTPUT_DIR)

        return GenerateImageResponse(
            status="success",
            message="Image generated successfully",
            image_path=image_path,
            prompt_id=prompt_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


@app.get("/download/{prompt_id}")
async def download_generated_image(prompt_id: str):
    output_dir = Path(COMFY_OUTPUT_DIR)

    matching_files = list(output_dir.glob(f"{prompt_id}_*"))

    if not matching_files:
        raise HTTPException(
            status_code=404,
            detail=f"No image found for prompt ID: {prompt_id}"
        )

    image_path = matching_files[0]

    return FileResponse(
        path=str(image_path),
        media_type="image/png",
        filename=image_path.name
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
