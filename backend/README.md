# Python Backend (ADK + FastAPI)

This backend uses Google ADK with Gemini Live and exposes a websocket for your frontend.

## 1) Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` from `.env.example`:

```env
GOOGLE_API_KEY=your_gemini_api_key
DEMO_AGENT_MODEL=gemini-2.5-flash-native-audio-preview-12-2025
```

## 2) Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

`GET http://localhost:8000/health`

WebSocket endpoint:

`ws://localhost:8000/ws/live`

Optional query params:

- `userId` (default: `local-dev`)
- `audio` (`true`/`false`, default: `true`)

## 3) Client message protocol

Send JSON messages to the websocket:

- Text
```json
{ "type": "text", "text": "Hello" }
```

- Audio chunk (base64 PCM16 @16kHz)
```json
{ "type": "audio", "mimeType": "audio/pcm;rate=16000", "data": "<base64>" }
```

- Image frame
```json
{ "type": "image", "mimeType": "image/jpeg", "data": "<base64>" }
```

- End audio stream
```json
{ "type": "audio_end" }
```

- Interrupt current response
```json
{ "type": "interrupt" }
```

Server messages are sent as:
```json
{
  "type": "gemini_event",
  "text": "aggregated text when available",
  "turnComplete": false,
  "interrupted": false,
  "audioChunks": [],
  "payload": { "full Gemini event payload" }
}
```

## 4) Deploy backend only to Google Cloud Run

Set variables in your shell:

```bash
PROJECT_ID="your-gcp-project-id"
REGION="us-central1"
SERVICE_NAME="gemini-live-backend"
```

Enable required services:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project "$PROJECT_ID"
```

Build and deploy directly from `backend/`:

```bash
cd backend
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --timeout 3600 \
  --set-env-vars DEMO_AGENT_MODEL=gemini-2.5-flash-native-audio-preview-12-2025 \
  --set-env-vars GOOGLE_API_KEY=YOUR_API_KEY
```

After deploy, use the service URL for websocket:

`wss://<service-url>/ws/live`

Recommended for production:
- Store `GOOGLE_API_KEY` in Secret Manager and mount via `--set-secrets` instead of plain env var.
