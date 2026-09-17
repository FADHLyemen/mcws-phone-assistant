#!/usr/bin/env python3
"""Create/update the MCWS assistant on Vapi and provision a free pilot number.

Required env:
  VAPI_API_KEY   Vapi PRIVATE API key (dashboard -> API Keys)
  WEBHOOK_URL    Base URL of the deployed tool webhook, e.g. https://mcws-assistant-xxxx.run.app

Optional env:
  AREA_CODE      3-digit US area code for the free number (default 734)
  VAPI_SECRET    shared secret sent to the webhook as x-vapi-secret header
  VOICE_PROVIDER / VOICE_ID   override the default voice
  MODEL_PROVIDER / MODEL      override the default model (default openai / gpt-4o)
  SKIP_NUMBER=1  create/update the assistant only, do not provision a number

Usage:
  VAPI_API_KEY=... WEBHOOK_URL=https://... python deploy_vapi.py
"""
import os, sys, json, requests

API = "https://api.vapi.ai"
KEY = os.environ.get("VAPI_API_KEY")
WEBHOOK = os.environ.get("WEBHOOK_URL", "").rstrip("/")
AREA_CODE = os.environ.get("AREA_CODE", "734")
SECRET = os.environ.get("VAPI_SECRET")
NAME = "MCWS Masjid Assistant"

if not KEY or not WEBHOOK:
    sys.exit("ERROR: set VAPI_API_KEY and WEBHOOK_URL environment variables.")

H = {"Authorization": "Bearer %s" % KEY, "Content-Type": "application/json"}
here = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(here, "assistant_config.json")))

# inject webhook URL everywhere the placeholder appears
cfg = json.loads(json.dumps(cfg).replace("{{WEBHOOK_URL}}", WEBHOOK))

# optional overrides
if os.environ.get("VOICE_PROVIDER") and os.environ.get("VOICE_ID"):
    cfg["voice"] = {"provider": os.environ["VOICE_PROVIDER"], "voiceId": os.environ["VOICE_ID"]}
if os.environ.get("MODEL_PROVIDER"):
    cfg["model"]["provider"] = os.environ["MODEL_PROVIDER"]
if os.environ.get("MODEL"):
    cfg["model"]["model"] = os.environ["MODEL"]

# attach shared secret to every server object pointing at our webhook
if SECRET:
    def add_secret(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get("url"), str) and obj["url"].startswith(WEBHOOK):
                obj.setdefault("secret", SECRET)
            for v in obj.values():
                add_secret(v)
        elif isinstance(obj, list):
            for v in obj:
                add_secret(v)
    add_secret(cfg)

def die(r, msg):
    print(msg, r.status_code)
    print(r.text[:1500])
    sys.exit(1)

# find existing assistant by name
r = requests.get("%s/assistant" % API, headers=H, timeout=30)
if r.status_code != 200:
    die(r, "list assistants failed:")
existing = next((a for a in r.json() if a.get("name") == NAME), None)

if existing:
    aid = existing["id"]
    r = requests.patch("%s/assistant/%s" % (API, aid), headers=H, json=cfg, timeout=30)
    if r.status_code not in (200, 201):
        die(r, "update assistant failed:")
    print("Updated assistant:", aid)
else:
    r = requests.post("%s/assistant" % API, headers=H, json=cfg, timeout=30)
    if r.status_code not in (200, 201):
        die(r, "create assistant failed:")
    aid = r.json()["id"]
    print("Created assistant:", aid)

if os.environ.get("SKIP_NUMBER") == "1":
    print("SKIP_NUMBER set -> not provisioning a phone number.")
    sys.exit(0)

# reuse a free vapi number already linked to this assistant if present
r = requests.get("%s/phone-number" % API, headers=H, timeout=30)
nums = r.json() if r.status_code == 200 else []
mine = next((n for n in nums if n.get("assistantId") == aid), None)
if mine:
    print("Existing number linked:", mine.get("number"), "(id %s)" % mine.get("id"))
    sys.exit(0)

# provision a free Vapi number
payload = {"provider": "vapi", "assistantId": aid, "name": "MCWS Pilot Line",
           "numberDesiredAreaCode": AREA_CODE}
r = requests.post("%s/phone-number" % API, headers=H, json=payload, timeout=60)
if r.status_code not in (200, 201):
    # retry without area code (desired area code may be unavailable)
    payload.pop("numberDesiredAreaCode", None)
    r = requests.post("%s/phone-number" % API, headers=H, json=payload, timeout=60)
if r.status_code not in (200, 201):
    die(r, "provision number failed:")
num = r.json()
print("\n==============================")
print("Pilot phone number:", num.get("number"))
print("Phone number id:   ", num.get("id"))
print("Assistant id:      ", aid)
print("Call it to test the MCWS assistant.")
print("==============================")
