# ComfyUI FastAPI Bridge

A FastAPI application that acts as a bridge to control a remote ComfyUI server for AI image generation.

## Overview

This project allows you to control a ComfyUI server (running on a GPU machine) through a RESTful API. It handles prompt injection, workflow execution, and image retrieval automatically.

## Architecture

- **Server A (GPU):** Runs ComfyUI at `192.168.1.7:8188` (or your configured IP)
- **Server B (Backend):** Runs this FastAPI application

## Prerequisites

- Python 3.8+
- A running ComfyUI instance accessible via network
- A workflow exported from ComfyUI (see instructions below)

## Installation

1. Clone or download this project

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy the example environment file:
```bash
cp .env.example .env
```

4. Edit `.env` with your ComfyUI server details:
```env
COMFY_URL=http://192.168.1.7:8188
COMFY_OUTPUT_DIR=./output
WORKFLOW_PATH=./workflow_api.json
```

## Getting Your workflow_api.json

This is **crucial** - you need to export your ComfyUI workflow in API format:

### Step-by-Step Instructions:

1. Open your ComfyUI web interface (e.g., `http://192.168.1.7:8188`)

2. Load or create the workflow you want to use for generation

3. Enable **Dev Mode** in ComfyUI:
   - Click the ⚙️ **Settings** button (gear icon)
   - Check ✅ **Enable Dev mode Options**
   - Close the settings

4. Export the workflow:
   - Click the **Save (API Format)** button
   - This downloads a JSON file (usually named `workflow_api.json`)

5. Place the downloaded file in your project root:
```
ai-fast-api-comfy-ui/
├── main.py
├── requirements.txt
├── .env
└── workflow_api.json  ← Place it here
```

### Understanding Node IDs in workflow_api.json

The API works by finding specific nodes in your workflow:

**CLIPTextEncode nodes** - For prompts:
```json
{
  "6": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "beautiful scenery",  ← Positive prompt injected here
      "clip": ["4", 1]
    }
  },
  "7": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "ugly, bad quality",  ← Negative prompt injected here
      "clip": ["4", 1]
    }
  }
}
```

**KSampler node** - For randomization:
```json
{
  "3": {
    "class_type": "KSampler",
    "inputs": {
      "seed": 12345,  ← Random seed injected here
      "steps": 20,
      "cfg": 8.0,
      ...
    }
  }
}
```

The API automatically:
- Finds `CLIPTextEncode` nodes and injects your prompts
- Finds `KSampler` nodes and randomizes the seed
- No manual configuration needed!

## Running the Server

Start the FastAPI server:

```bash
python main.py
```

Or using uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once running, visit:
- **Interactive docs:** `http://localhost:8000/docs`
- **Alternative docs:** `http://localhost:8000/redoc`

## API Endpoints

### 1. Health Check
```bash
GET /health
```

Response:
```json
{
  "status": "healthy",
  "comfy_ui": "online",
  "comfy_url": "http://192.168.1.7:8188"
}
```

### 2. Generate Image
```bash
POST /generate-image
Content-Type: application/json

{
  "prompt": "beautiful landscape, mountains, sunset, detailed",
  "negative_prompt": "ugly, blurry, low quality"
}
```

Response:
```json
{
  "status": "success",
  "message": "Image generated successfully",
  "image_path": "./output/abc123_image.png",
  "prompt_id": "abc123"
}
```

### 3. Download Generated Image
```bash
GET /download/{prompt_id}
```

Returns the image file directly.

## Usage Examples

### Using cURL:

```bash
curl -X POST "http://localhost:8000/generate-image" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a beautiful cat, photorealistic, 4k",
    "negative_prompt": "cartoon, ugly, deformed"
  }'
```

### Using Python:

```python
import requests

response = requests.post(
    "http://localhost:8000/generate-image",
    json={
        "prompt": "a beautiful cat, photorealistic, 4k",
        "negative_prompt": "cartoon, ugly, deformed"
    }
)

result = response.json()
print(f"Image saved to: {result['image_path']}")
print(f"Prompt ID: {result['prompt_id']}")
```

### Using JavaScript/Fetch:

```javascript
fetch('http://localhost:8000/generate-image', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    prompt: 'a beautiful cat, photorealistic, 4k',
    negative_prompt: 'cartoon, ugly, deformed'
  })
})
.then(res => res.json())
.then(data => console.log('Image generated:', data));
```

## How It Works

1. **Load Workflow:** Reads your `workflow_api.json` template
2. **Inject Prompts:** Finds `CLIPTextEncode` nodes and replaces text with your prompts
3. **Randomize Seed:** Finds `KSampler` nodes and generates random seeds
4. **Queue Job:** Sends the modified workflow to ComfyUI via `POST /prompt`
5. **Wait for Completion:** Connects to ComfyUI's WebSocket to track execution status
6. **Download Image:** Retrieves the generated image via `GET /view`
7. **Return Result:** Saves the image locally and returns the path

## Error Handling

The API handles common errors:

- **ComfyUI Offline:** Returns 503 with connection error
- **Workflow Not Found:** Returns 500 with file not found error
- **Generation Timeout:** Returns 504 if generation takes >5 minutes
- **Execution Errors:** Returns 500 with ComfyUI error details

## Project Structure

```
ai-fast-api-comfy-ui/
├── main.py              # Main FastAPI application
├── requirements.txt     # Python dependencies
├── .env                 # Environment configuration (create from .env.example)
├── .env.example         # Environment template
├── workflow_api.json    # Your ComfyUI workflow (you provide this)
├── output/              # Generated images saved here
└── README.md           # This file
```

## Configuration Options

Edit `.env` to customize:

| Variable | Description | Example |
|----------|-------------|---------|
| `COMFY_URL` | ComfyUI server URL | `http://192.168.1.7:8188` |
| `COMFY_OUTPUT_DIR` | Where to save images | `./output` |
| `WORKFLOW_PATH` | Path to workflow file | `./workflow_api.json` |

## Troubleshooting

### "Workflow file not found"
- Make sure `workflow_api.json` exists in your project root
- Check the `WORKFLOW_PATH` in your `.env` file

### "Failed to connect to ComfyUI"
- Verify ComfyUI is running: visit `http://192.168.1.7:8188` in your browser
- Check firewall settings on the GPU server
- Ensure the `COMFY_URL` in `.env` is correct

### "No output images found"
- Check your workflow has a SaveImage or similar output node
- Verify the workflow executes successfully in ComfyUI directly

### WebSocket connection issues
- ComfyUI must be accessible via WebSocket (usually automatic)
- Check for proxy/firewall blocking WebSocket connections

## Advanced Usage

### Custom Timeout

The default timeout is 300 seconds (5 minutes). To modify:

```python
# In main.py, line with wait_for_completion:
await client.wait_for_completion(prompt_id, timeout=600)  # 10 minutes
```

### Multiple Workflows

You can support multiple workflows:

1. Create different workflow files: `workflow_api_landscape.json`, `workflow_api_portrait.json`
2. Add a `workflow_type` parameter to the request
3. Modify `load_workflow()` to select the appropriate file

## License

This project is provided as-is for educational purposes.

## Support

For issues related to:
- **This API:** Check the logs and error messages
- **ComfyUI:** Visit [ComfyUI GitHub](https://github.com/comfyanonymous/ComfyUI)
- **FastAPI:** Visit [FastAPI Documentation](https://fastapi.tiangolo.com/)
