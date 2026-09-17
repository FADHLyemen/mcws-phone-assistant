"""MCWS Masjid phone-assistant webhook (Vapi custom tools).

Endpoints:
  GET  /                 -> health check
  GET  /prayer-times     -> today's times as JSON (debug/manual)
  GET  /events           -> upcoming events text (debug/manual)
  POST /vapi/tools       -> Vapi tool-call handler (get_prayer_times, get_upcoming_events, take_a_message)

All tool logic is also exposed as plain functions so it can be tested locally.
Message sink for take_a_message is pluggable via env vars (see README).
"""
import os, re, json, uuid, logging, smtplib
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText

import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

import prayer_times as pt

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mcws")
app = Flask(__name__)

VAPI_SECRET = os.environ.get("VAPI_SECRET")          # optional shared secret
MESSAGES_BUCKET = os.environ.get("MESSAGES_BUCKET")   # optional GCS bucket name
NOTIFY_TO = os.environ.get("NOTIFY_TO")               # optional email recipient(s)
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")

# ---------------------------------------------------------------- prayer times
def _say_time(t):
    """'6:20' -> '6:20 AM' style hint is left to the model; keep raw + note."""
    return t

def tool_get_prayer_times(args):
    when = (args or {}).get("date") or (args or {}).get("day")
    try:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/Detroit")).date()
    except Exception:
        today = date.today()
    d = today
    if when:
        w = str(when).strip().lower()
        if w in ("today",):
            d = today
        elif w in ("tomorrow",):
            d = today + timedelta(days=1)
        else:
            try:
                d = datetime.strptime(w, "%Y-%m-%d").date()
            except ValueError:
                d = today
    data = pt.get_prayer_times(d)
    data["note"] = ("Adhan = call to prayer (begins); Iqama = congregation start. "
                    "Maghrib Iqama is at sunset. Speak times naturally, e.g. 'six twenty in the morning'.")
    return data

# ---------------------------------------------------------------- events
def tool_get_upcoming_events(args=None):
    try:
        r = requests.get("https://www.mcws.org/events", timeout=15,
                         headers={"User-Agent": "MCWS-Assistant"})
        s = BeautifulSoup(r.text, "lxml")
        for t in s(["script", "style", "noscript"]):
            t.decompose()
        lines = [ln.strip() for ln in s.get_text("\n").splitlines() if ln.strip()]
        # drop obvious nav/boilerplate; keep from after the "Home /" breadcrumb
        try:
            i = lines.index("/")
            lines = lines[i + 1:]
        except ValueError:
            pass
        text = "\n".join(lines)
        text = text.split("Newsletter")[0]  # cut footer if present
        return {"events_text": text[:2500],
                "source": "mcws.org/events",
                "note": "Summarize the next few upcoming events with date and location. Full list at mcws.org/events."}
    except Exception as e:
        log.exception("events fetch failed")
        return {"error": "Could not load events right now.",
                "fallback": "Please check mcws.org/events or leave a message.", "detail": str(e)}

# ---------------------------------------------------------------- take a message
def _persist_message(rec):
    saved = []
    log.info("MCWS_MESSAGE %s", json.dumps(rec))
    saved.append("log")
    if MESSAGES_BUCKET:
        try:
            from google.cloud import storage
            key = "messages/%s/%s.json" % (rec["received_at"][:10], rec["id"])
            storage.Client().bucket(MESSAGES_BUCKET).blob(key).upload_from_string(
                json.dumps(rec, indent=2), content_type="application/json")
            saved.append("gcs")
        except Exception:
            log.exception("gcs persist failed")
    if NOTIFY_TO and SMTP_HOST and SMTP_USER and SMTP_PASS:
        try:
            body = ("New message from the MCWS phone assistant:\n\n"
                    "Name: %(name)s\nPhone: %(phone)s\nFor: %(category)s\n\nMessage:\n%(message)s\n\n"
                    "Received: %(received_at)s\nID: %(id)s\n") % rec
            msg = MIMEText(body)
            msg["Subject"] = "MCWS phone message: %s" % (rec.get("category") or "general")
            msg["From"] = SMTP_USER
            msg["To"] = NOTIFY_TO
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as srv:
                srv.starttls(); srv.login(SMTP_USER, SMTP_PASS)
                srv.sendmail(SMTP_USER, [a.strip() for a in NOTIFY_TO.split(",")], msg.as_string())
            saved.append("email")
        except Exception:
            log.exception("email notify failed")
    return saved

def tool_take_a_message(args):
    args = args or {}
    rec = {
        "id": uuid.uuid4().hex[:12],
        "name": str(args.get("name", "")).strip(),
        "phone": str(args.get("phone", "")).strip(),
        "message": str(args.get("message", "")).strip(),
        "category": str(args.get("category", "general")).strip() or "general",
        "received_at": datetime.utcnow().isoformat() + "Z",
    }
    if not rec["message"]:
        return {"ok": False, "error": "No message content provided."}
    sinks = _persist_message(rec)
    return {"ok": True, "confirmation":
            "Message received. A member of the MCWS team will follow up.",
            "reference": rec["id"], "recorded_to": sinks}

TOOLS = {
    "get_prayer_times": tool_get_prayer_times,
    "get_upcoming_events": tool_get_upcoming_events,
    "take_a_message": tool_take_a_message,
}

# ---------------------------------------------------------------- Vapi handler
def _extract_calls(body):
    msg = (body or {}).get("message", {}) or {}
    calls = msg.get("toolCallList") or msg.get("toolCalls") or msg.get("tool_calls") or []
    out = []
    for c in calls:
        fn = c.get("function", c)
        name = fn.get("name")
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try: args = json.loads(args)
            except Exception: args = {}
        out.append((c.get("id") or c.get("toolCallId"), name, args))
    return out

@app.post("/vapi/tools")
def vapi_tools():
    if VAPI_SECRET and request.headers.get("x-vapi-secret") != VAPI_SECRET:
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(force=True, silent=True) or {}
    results = []
    for call_id, name, args in _extract_calls(body):
        fn = TOOLS.get(name)
        try:
            res = fn(args) if fn else {"error": "unknown tool %s" % name}
        except Exception as e:
            log.exception("tool %s failed", name)
            res = {"error": "tool execution failed", "detail": str(e)}
        results.append({"toolCallId": call_id, "name": name,
                        "result": json.dumps(res) if not isinstance(res, str) else res})
    return jsonify({"results": results})

@app.get("/")
def health():
    return jsonify({"service": "mcws-assistant-webhook", "status": "ok",
                    "tools": list(TOOLS)})

@app.get("/prayer-times")
def dbg_prayer():
    return jsonify(tool_get_prayer_times(dict(request.args)))

@app.get("/events")
def dbg_events():
    return jsonify(tool_get_upcoming_events())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
