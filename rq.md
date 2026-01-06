# Role
Act as a Senior Python Backend Developer. Your task is to create a robust API using **FastAPI** that acts as a bridge to control a remote **ComfyUI** server.

# Context
I have a two-computer setup:
1. **Server A (GPU):** Runs ComfyUI, listening on a LAN IP 192.168.1.7:8188.
2. **Server B (Backend):** Runs this FastAPI application.

# Objective
Create a FastAPI application with the following requirements:

## 1. Environment Configuration
- Use `python-dotenv` to load configurations.
- Variables needed: `COMFY_URL` (e.g., http://192.168.1.50:8188), `COMFY_OUTPUT_DIR`.

## 2. Core Logic (ComfyUI Interfacing)
- You need to implement functions to:
  - Load a `workflow_api.json` template.
  - Modify the **Prompt Text** (find the node with "CLIPTextEncode" class).
  - Randomize the **Seed** (find the node with "KSampler" class).
  - Send the payload to ComfyUI (`POST /prompt`).
  - **Crucial:** Wait for the generation to finish. Use `websocket` library to listen to ComfyUI's websocket at `/ws` to track execution status (look for "execution_success"), OR implement a robust polling mechanism checking `/history`.
  - Download the resulting image from ComfyUI (`GET /view`).

## 3. API Endpoints
Create a POST endpoint `/generate-image`:
- **Input (JSON Body):** - `prompt` (string): The positive prompt text.
  - `negative_prompt` (string): Optional negative prompt.
- **Process:**
  - Connect to ComfyUI.
  - Inject the prompts into the workflow.
  - Trigger generation.
  - Wait for the result.
  - Save the image locally (on Server B) or hold it in memory.
- **Output:** - Return the image file directly (using `FileResponse` or `StreamingResponse`) OR return a JSON with the status and path/URL to the image.

## 4. Code Structure
- Use `pydantic` for data validation.
- Use `httpx` or `requests` for HTTP calls.
- Include error handling (e.g., if ComfyUI is offline).
- Include comments explaining how to find `node_id` for text inputs in the JSON workflow.

## Deliverables
1. `main.py`: The complete FastAPI code.
2. `requirements.txt`: List of dependencies.
3. `.env.example`: Template for environment variables.
4. Instructions on how to extract `workflow_api.json` from ComfyUI and where to place it.