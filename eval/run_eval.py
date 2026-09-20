#!/usr/bin/env python3
"""MCWS phone-assistant evaluation harness (deterministic core + pluggable judge).

Runs a golden question set through the DEPLOYED Vapi assistant via the chat API
(which exercises the real model + tools + live webhook) and scores:

  - tool_choice    did it call the expected tool? ("none" = no tool)      [deterministic]
  - prayer_value   does the stated time match the value the tool returned? [deterministic]
  - language       does it reply in the caller's language (en/ar)?         [deterministic]
  - refusal        does a fatwa/ruling question defer to the Imam?         [heuristic]
  - groundedness   answer supported by tool/KB context (LLM-as-judge)      [only if JUDGE_URL set]

Env:
  VAPI_API_KEY   required  - Vapi private key
  ASSISTANT_ID   required  - the assistant to evaluate
  JUDGE_URL      optional  - OpenAI-compatible chat-completions endpoint for groundedness
  JUDGE_KEY      optional  - bearer token for the judge
  JUDGE_MODEL    optional  - judge model name (default: 'default')

Usage:
  VAPI_API_KEY=... ASSISTANT_ID=... python run_eval.py            # run + score
  ... python run_eval.py --set-baseline                            # save current as baseline
Outputs (to --outdir, default .): results.json, report.md; reads/writes baseline.json.
"""
import os, re, json, argparse
from collections import defaultdict
import requests

API = "https://api.vapi.ai"
AR_RE = re.compile(r"[\u0600-\u06FF]")
TIME_RE = re.compile(r"\d{1,2}:\d{2}")
UA = {"User-Agent": "mcws-eval"}


def chat(key, aid, text):
    H = {"Authorization": "Bearer " + key, "Content-Type": "application/json", **UA}
    r = requests.post(API + "/chat", headers=H, json={"assistantId": aid, "input": text}, timeout=90)
    r.raise_for_status()
    return r.json()


def parse(d):
    out = d.get("output", []) or []
    tools = [tc["function"]["name"] for m in out if isinstance(m, dict) and m.get("tool_calls")
             for tc in m["tool_calls"]]
    tool_results = []
    for m in out:
        if isinstance(m, dict) and m.get("role") == "tool":
            try:
                tool_results.append(json.loads(m.get("content", "")))
            except Exception:
                pass
    answer, alltxt = "", []
    for m in out:
        if isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
            answer = m["content"]
            alltxt.append(m["content"])
    return tools, tool_results, answer, " ".join(alltxt)


def _prayer_values(tool_results, prayer):
    vals = []
    for tr in tool_results:
        if prayer == "jumuah":
            vals += [str(x) for x in tr.get("jumuah", [])]
        else:
            for kind in ("adhan", "iqama"):
                v = (tr.get(kind) or {}).get(prayer)
                if v:
                    vals.append(str(v))
    return vals


_ONES = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
         8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
         15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen"}
_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty"}


def _num_words(n):
    if n in _ONES:
        return _ONES[n]
    t, o = (n // 10) * 10, n % 10
    return _TENS.get(t, "") + ("-" + _ONES[o] if o else "")


def _worded_time_forms(v):
    """English spoken forms of a 'H:MM' time, e.g. 9:02 -> 'nine oh two', 2:00 -> "two o'clock"."""
    m = re.match(r"(\d{1,2}):(\d{2})", v)
    if not m:
        return []
    h, mi = int(m.group(1)), int(m.group(2))
    hw = _num_words(h if h else 12)
    if mi == 0:
        return [hw + " o'clock", hw + " oclock"]
    if mi < 10:
        return [hw + " oh " + _num_words(mi), hw + " o " + _num_words(mi)]
    return [hw + " " + _num_words(mi)]


def _value_in_answer(v, answer):
    a = answer.lower()
    m = TIME_RE.search(v)
    if m and m.group(0) in a:
        return True
    if "sunset" in v.lower() and "sunset" in a:
        return True
    return any(f in a for f in _worded_time_forms(v))


def _judge_groundedness(answer, tool_results):
    """LLM-as-judge groundedness. Returns True/False/None (None = not configured/failed)."""
    url = os.environ.get("JUDGE_URL")
    if not url or not answer:
        return None
    ctx = json.dumps(tool_results)[:2000] if tool_results else "(no tool data; general/KB answer)"
    prompt = ("You are grading a masjid phone assistant. Given the CONTEXT the assistant had and "
              "its ANSWER, reply with exactly 'SCORE: 1' if every factual claim in the answer is "
              "supported by the context (or is a safe non-factual/redirect statement), or 'SCORE: 0' "
              "if it states an unsupported/invented fact.\n\nCONTEXT:\n" + ctx + "\n\nANSWER:\n" + answer)
    try:
        H = {"Authorization": "Bearer " + os.environ.get("JUDGE_KEY", ""), "Content-Type": "application/json", **UA}
        body = {"model": os.environ.get("JUDGE_MODEL", "default"),
                "messages": [{"role": "user", "content": prompt}], "temperature": 0}
        r = requests.post(url, headers=H, json=body, timeout=60)
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"SCORE:\s*([01])", txt)
        return (m.group(1) == "1") if m else None
    except Exception:
        return None


def score(item, tools, tool_results, answer, alltext):
    checks = {}
    exp = item.get("expect_tool")
    if exp is not None:
        checks["tool_choice"] = (len(tools) == 0) if exp == "none" else (exp in tools)
    lang = item.get("expect_lang")
    if lang:
        has_ar = bool(AR_RE.search(answer))
        checks["language"] = has_ar if lang == "ar" else (not has_ar)
    if item.get("expect_refusal"):
        t = alltext.lower()
        checks["refusal"] = ("imam" in t) or ("take a message" in t) or ("can't answer" in t) or ("cannot answer" in t)
    pr = item.get("prayer")
    # Deterministic word-matching only handles English number-words; Arabic-worded times
    # are left to the groundedness judge, so skip prayer_value for Arabic items.
    if pr and item.get("expect_lang") != "ar":
        vals = _prayer_values(tool_results, pr)
        checks["prayer_value"] = bool(vals) and any(_value_in_answer(v, answer) for v in vals)
    g = _judge_groundedness(answer, tool_results)
    if g is not None:
        checks["groundedness"] = g
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="questions.json")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--baseline", default="baseline.json")
    ap.add_argument("--set-baseline", action="store_true")
    ap.add_argument("--tolerance", type=float, default=0.0)
    a = ap.parse_args()
    key, aid = os.environ["VAPI_API_KEY"], os.environ["ASSISTANT_ID"]
    items = json.load(open(a.questions, encoding="utf-8"))

    results = []
    agg = defaultdict(lambda: [0, 0])
    for it in items:
        try:
            tools, trs, answer, alltxt = parse(chat(key, aid, it["input"]))
            checks = score(it, tools, trs, answer, alltxt)
            err = None
        except Exception as e:
            tools, answer, checks, err = [], "", {}, str(e)
        for mname, ok in checks.items():
            agg[mname][1] += 1
            agg[mname][0] += 1 if ok else 0
        results.append({"id": it.get("id"), "category": it.get("category"), "input": it["input"],
                        "tools": tools, "answer": answer[:400], "checks": checks, "error": err})
        line = " ".join("%s=%s" % (k, "OK" if v else "FAIL") for k, v in checks.items())
        print("%-5s %-15s %s" % (it.get("id"), it.get("category", ""), line or ("ERROR: " + str(err) if err else "(no checks)")))

    summary = {m: round(p / t, 3) if t else None for m, (p, t) in agg.items()}
    op = sum(p for p, t in agg.values())
    ot = sum(t for p, t in agg.values())
    summary["_overall"] = round(op / ot, 3) if ot else None
    os.makedirs(a.outdir, exist_ok=True)
    json.dump({"summary": summary, "n": len(items), "results": results},
              open(os.path.join(a.outdir, "results.json"), "w"), indent=2, ensure_ascii=False)

    # baseline compare / write
    bpath = os.path.join(a.outdir, a.baseline)
    regressions = []
    if a.set_baseline:
        json.dump(summary, open(bpath, "w"), indent=2)
    elif os.path.exists(bpath):
        base = json.load(open(bpath))
        for m, v in summary.items():
            if v is not None and base.get(m) is not None and v < base[m] - a.tolerance:
                regressions.append((m, base[m], v))

    # report.md
    lines = ["# MCWS Assistant Evaluation\n", "## Metric pass rates\n", "| Metric | Pass rate |", "|---|---|"]
    for m, v in summary.items():
        lines.append("| %s | %s |" % (m, ("%.0f%%" % (v * 100)) if v is not None else "n/a"))
    lines.append("\n## Per-question\n")
    lines.append("| id | category | tools | checks |")
    lines.append("|---|---|---|---|")
    for r in results:
        ch = " ".join("%s:%s" % (k, "✓" if v else "✗") for k, v in r["checks"].items())
        lines.append("| %s | %s | %s | %s |" % (r["id"], r["category"], ",".join(r["tools"]) or "—", ch or (r["error"] or "")))
    if regressions:
        lines.append("\n## ⚠ Regressions vs baseline\n")
        for m, b, v in regressions:
            lines.append("- **%s**: %.0f%% → %.0f%%" % (m, b * 100, v * 100))
    open(os.path.join(a.outdir, "report.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    print("\nSUMMARY:", json.dumps(summary))
    if regressions:
        print("REGRESSIONS:", regressions)


if __name__ == "__main__":
    main()
