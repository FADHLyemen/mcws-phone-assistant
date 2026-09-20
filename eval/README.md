# MCWS Assistant Evaluation

A lightweight evaluation suite that runs a fixed set of questions through the
**deployed** assistant (via the Vapi chat API, which exercises the real model +
tools + live webhook) and scores its behavior. Use it after any change to the
prompt, model, knowledge base, or tools to prove nothing regressed.

## Metrics
| Metric | How | Type |
|---|---|---|
| `tool_choice` | did it call the expected tool (`none` = no tool)? | deterministic |
| `prayer_value` | does the stated time match the value the tool returned? (matches digit **and** spoken-word forms) | deterministic |
| `language` | does it reply in the caller's language (en/ar)? | deterministic |
| `refusal` | does a fatwa/ruling question defer to the Imam? | heuristic |
| `groundedness` | is every factual claim supported by tool/KB context? | LLM-as-judge (only if `JUDGE_URL` set) |

The first four need no model to grade. `groundedness` is optional and runs only
when a judge endpoint is configured — point `JUDGE_URL` at any OpenAI-compatible
chat-completions API (e.g. a self-hosted model) to enable it.

## Run
```bash
pip install requests
VAPI_API_KEY=<private key> ASSISTANT_ID=<assistant id> python run_eval.py
# optional groundedness judge:
#   JUDGE_URL=<.../v1/chat/completions> JUDGE_KEY=<token> JUDGE_MODEL=<name> ...
```
Outputs `results.json` (per-question detail) and `report.md` (pass-rate tables).

## Baseline / regression tracking
`baseline.json` holds the accepted per-metric pass rates. A normal run compares
against it and flags any metric that drops (beyond `--tolerance`). To re-anchor
the baseline after an intended change:
```bash
... python run_eval.py --set-baseline
```

## Editing the question set
`questions.json` is a list of items. Fields: `input`, `category`, and optional
`expect_tool` (`get_prayer_times`|`get_upcoming_events`|`take_a_message`|`none`),
`prayer` (fajr/dhuhr/asr/maghrib/isha/jumuah), `expect_lang` (en/ar),
`expect_refusal` (true for fatwa/ruling questions). Add rows to cover new cases.
