# MCWS Masjid AI Phone Assistant

A 24/7 AI phone assistant for MCWS (Muslim Community of Western Suburbs), Canton, MI.
Built on **Vapi** (voice platform) + a **Cloud Run webhook** for live data.

## What it does
Answers common caller questions: daily prayer & Iqama times, Jumu'ah times, upcoming
events/programs, donations, services (embrace Islam, matrimonial, counseling, elder
care, funeral/Janazah), education programs, locations, and contacts. It refers
religious rulings (fatwas) to the Imam and can take a message for staff or the Imam.

## Architecture
```
Caller -> Vapi phone number -> Vapi assistant (speech-to-text, LLM, text-to-speech)
                                     |
                                     |  tool calls (prayer times, events, messages)
                                     v
                         Cloud Run webhook  (backend/)  -> AthanPlus live prayer feed
                                                        -> mcws.org/events (live)
                                                        -> message sink (log/GCS/email)
```
- Static facts (about, services, contacts, donation) are embedded in the assistant's
  system prompt from `kb/mcws_knowledge_base.md`.
- Dynamic data (daily prayer/iqama times, current events, take-a-message) is served
  by the webhook so answers are always current.

## Files
- `backend/`            Flask webhook (deploy to Cloud Run)
  - `app.py`            tool handler for Vapi (`/vapi/tools`) + debug routes
  - `prayer_times.py`   live prayer/iqama parser (AthanPlus, masjid RKxwV5dO)
  - `Dockerfile`, `requirements.txt`
- `vapi/`
  - `system_prompt.md`      the assistant persona / call-flow
  - `assistant_config.json` full Vapi assistant object (system prompt + KB embedded)
  - `deploy_vapi.py`        creates the assistant + provisions a free pilot number
- `kb/`
  - `mcws_knowledge_base.md`  curated knowledge base
  - `mcws_pages_raw.json`     raw scraped site content

## Deploy — step 1: the webhook (Cloud Run)
```
cd backend
gcloud run deploy mcws-assistant \
  --source . --region us-central1 --allow-unauthenticated \
  --memory 512Mi --timeout 60 --min-instances 1
```
Note the service URL it prints, e.g. `https://mcws-assistant-xxxx.run.app`.
Verify: `curl https://mcws-assistant-xxxx.run.app/`  -> should return status ok.

Optional env for take-a-message delivery (set with `--set-env-vars`):
- `MESSAGES_BUCKET=<gcs-bucket>`  store each message as JSON in the bucket
- `NOTIFY_TO`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`  email notifications
- `VAPI_SECRET=<random>`  require this shared secret on webhook calls
If none set, messages are written to Cloud Run logs (searchable as `MCWS_MESSAGE`).

## Deploy — step 2: the Vapi assistant + pilot number
Get a Vapi PRIVATE API key from the Vapi dashboard (API Keys), then:
```
cd vapi
VAPI_API_KEY=<your-private-key> \
WEBHOOK_URL=https://mcws-assistant-xxxx.run.app \
AREA_CODE=734 \
python deploy_vapi.py
```
This creates (or updates) the "MCWS Masjid Assistant" and provisions a **free Vapi
US phone number** linked to it. The script prints the phone number — call it to test.
(A payment method may need to be on file with Vapi for the free number, but free
Vapi numbers are not charged. To use your own Twilio number instead, import it in the
Vapi dashboard and skip number provisioning with `SKIP_NUMBER=1`.)

Re-running the script updates the existing assistant in place (safe to iterate).

## Test checklist
- "What time is Fajr today?" / "When is Isha iqama tomorrow?"
- "When is Jumu'ah?"
- "What events are coming up?"
- "How do I donate?"
- "Can the Imam call me about a religious question?" (should take a message, not answer)
- "Can someone call me back?" (take-a-message flow)

## Going live later
Once you're happy with the pilot, forward the main line (734-210-1947) to the pilot
number, or import the main number into Vapi. The live line stays untouched until you
choose to do this.

## Customizing
- Voice: set `VOICE_PROVIDER` / `VOICE_ID` (default 11labs). Change in the Vapi dashboard too.
- Model: set `MODEL_PROVIDER` / `MODEL` (default openai / gpt-4o; e.g. anthropic, google).
- Knowledge/persona: edit `vapi/system_prompt.md` and `kb/mcws_knowledge_base.md`, then
  rebuild the config (re-embed the KB into the system message) and re-run `deploy_vapi.py`.
