# Build your own masjid / community phone assistant

This is a working reference implementation (built for MCWS, Canton MI). To stand
up your own, you change three things: the **knowledge base**, the **prayer-times
source**, and the **assistant identity**. Architecture and full deploy steps are
in `README.md`.

## Architecture (recap)
```
Caller -> Vapi number -> Vapi assistant (STT + LLM + TTS)
                              |  tool calls
                              v
                    Cloud Run webhook (backend/) -> live prayer feed
                                                 -> live events (your site)
                                                 -> take-a-message sink
```
Static facts live in the assistant's system prompt (from your knowledge base);
anything that changes (prayer times, events, messages) is served live by the webhook.

## 1. Knowledge base
- Replace `kb/mcws_knowledge_base.md` with your org's facts: locations, contacts,
  services, education programs, donation link, leadership, request procedures.
- `scrape_site.py` helps: it fetches a site, strips repeated nav/footer boilerplate
  by line frequency, and dumps the page text you can curate into the KB. Run:
  `python scrape_site.py https://your-site.org`
- Keep the KB small (a few KB). It gets embedded directly into the system prompt.

## 2. Prayer times
- If your masjid publishes on **AthanPlus**, just set `ATHANPLUS_MASJID_ID` to your
  masjid id (find it in your AthanPlus widget URL, `...?masjid_id=XXXX`).
- If you use a different provider, rewrite `backend/prayer_times.py:get_prayer_times`
  to return the same dict shape (`adhan`, `iqama`, `sunrise`, `jumuah`).
- Not a masjid? Drop the prayer tool entirely and keep `get_upcoming_events` +
  `take_a_message`.

## 3. Assistant identity
- Edit `vapi/system_prompt.md`: greeting, scope, tone, guardrails (e.g. the
  "don't issue fatwas — refer to the Imam" rule), and handoff contacts.
- The deploy script rebuilds `vapi/assistant_config.json` by embedding
  `system_prompt.md` + your KB, so edit the prompt/KB and re-run — don't hand-edit
  the JSON's system message.
- Change voice/model via the `VOICE_*` / `MODEL_*` env vars.

## 4. Events tool
- `backend/app.py:tool_get_upcoming_events` fetches `mcws.org/events` and returns
  the page text for the model to summarize. Point it at your own events page URL.

## 5. Deploy
Follow `README.md`:
1. Deploy the webhook to Cloud Run, note its URL.
2. Get a Vapi private API key, run `deploy_vapi.py` — it creates the assistant and
   provisions a free pilot number.

## Notes / gotchas
- Free Vapi numbers are **inbound-only** and occasionally recycled with stale
  carrier routing (a call goes to a voicemail and Vapi logs zero calls). If that
  happens, release and re-provision, or import a Twilio number for production.
- New Vapi orgs must **complete one real credit purchase** before any call/chat runs
  (the signup promo credit does not count).
- Never commit your Vapi private key. `deploy_vapi.py` reads it from the env only.
- Test the assistant end-to-end via the Vapi chat API before a live call:
  `POST https://api.vapi.ai/chat` with `{assistantId, input}` (use curl; the default
  Python user-agent is blocked at Vapi's edge).
