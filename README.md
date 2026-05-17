# Reverie

Reverie is a FastAPI and Supabase web app for capturing notes, reminders, recommendations, and screenshot memories. It uses server-side Supabase Auth sessions, optional LLM extraction, OCR for uploaded images, and PWA assets for mobile testing or Android TWA wrapping.

## Local Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Set the required environment variables:

```powershell
$env:SUPABASE_URL="https://your-project.supabase.co"
$env:SUPABASE_ANON_KEY="your-supabase-anon-key"
$env:SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
```

4. Run required Supabase SQL migrations:

Open Supabase SQL Editor and run:

- `supabase_entity_aliases.sql`
- `supabase_user_sessions.sql`
- `supabase_profiles.sql`

The `user_sessions` table stores Supabase access and refresh tokens on the server. Browser and Android clients receive only an opaque `reverie_app_session` cookie.
The `profiles` table stores editable account profile fields such as display name, phone number, timezone, and preferred language.

5. Optional OCR and AI variables:

```powershell
$env:OPENAI_API_KEY="your-openai-api-key"
$env:OPENAI_VISION_MODEL="gpt-4o-mini"
$env:SUPABASE_IMAGE_BUCKET="memory-images"
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
```

6. Run the app:

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`.

## Required Environment Variables

- `SUPABASE_URL`: Supabase project URL.
- `SUPABASE_ANON_KEY` or `SUPABASE_KEY`: Public anon JWT key used for auth calls. Use the anon key that starts with `eyJ...`, not a newer `sb_publishable_...` key.
- `SUPABASE_SERVICE_ROLE_KEY`: Server-only JWT key used by the backend. This should also start with `eyJ...`. Never expose this in frontend code, Android projects, or browser JavaScript.
- `OPENAI_API_KEY`: Optional. Enables LLM extraction and vision OCR fallback.
- `OPENAI_VISION_MODEL`: Optional. Defaults to `gpt-4o-mini`.
- `SUPABASE_IMAGE_BUCKET`: Optional. Defaults to `memory-images`.
- `TESSERACT_CMD`: Optional path to the Tesseract executable when it is not on `PATH`.

## Image Upload Limits

Image uploads are limited before OCR runs:

- At most 10 images per request.
- At most 20 image memories per user.
- Allowed types: JPG, PNG, WEBP.
- Default maximum file size: 8 MB.
- Default maximum dimensions: 6000 x 6000.
- Default decompression-bomb guard: 36,000,000 pixels.

These defaults can be overridden with:

```powershell
$env:MAX_IMAGE_FILE_SIZE_BYTES="8388608"
$env:MAX_IMAGE_WIDTH="6000"
$env:MAX_IMAGE_HEIGHT="6000"
$env:MAX_IMAGE_PIXELS="36000000"
```

## Render Deployment

The repo includes `Dockerfile`, `Aptfile`, `runtime.txt`, and `render.yaml` style assets for Render-style deployment. Configure all secrets in Render environment variables. Do not commit `.env` files, Google credential files, refresh tokens, or Supabase service keys.

Tesseract is installed for Docker deployments by the `Dockerfile`. If using a non-Docker Render runtime, keep `Aptfile` configured with `tesseract-ocr`.

## Security Notes

- `google_calendar_credentials.json` and `google_calendar_token.json` must not be committed.
- If these files were previously pushed to GitHub, revoke/rotate the Google OAuth client and refresh token in Google Cloud.
- Calendar sync is disabled for beta and does not use local Google credential or token files.
- `SUPABASE_SERVICE_ROLE_KEY` must remain server-side only.
- Browser cookies store only an opaque session ID. Supabase access and refresh tokens are stored server-side in `user_sessions`.
- Uploaded images are validated by MIME type, extension, file size, dimensions, and Pillow image verification before being stored or processed.

## PWA / Android TWA

The app includes a manifest, service worker, and static icons. For Android Play Store packaging, deploy the PWA over HTTPS first, then generate a Trusted Web Activity project with Bubblewrap using the deployed manifest URL.
