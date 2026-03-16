

## Run Locally

**Prerequisites:**  Node.js


1. Install dependencies:
   `npm install`
2. Set the `GEMINI_API_KEY` in [.env.local](.env.local) to your Gemini API key
3. Run the app:
   `npm run dev`

## Python backend (separate)

If you want Gemini Live handled server-side, see:

`backend/README.md`

## Deploy frontend to Cloud Run

Set values:

```bash
PROJECT_ID="your-project-id"
REGION="us-central1"
FRONTEND_SERVICE="gemini-live-frontend"
BACKEND_WS_URL="wss://gemini-live-backend-xxxxx.us-central1.run.app/ws/live"
```

Deploy from repo root:

```bash
gcloud run deploy "$FRONTEND_SERVICE" \
  --source . \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-build-env-vars VITE_BACKEND_WS_URL="$BACKEND_WS_URL"
```
