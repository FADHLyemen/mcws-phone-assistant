# MCWS Assistant Evaluation

## Metric pass rates

| Metric | Pass rate |
|---|---|
| tool_choice | 100% |
| language | 100% |
| prayer_value | 100% |
| refusal | 100% |
| _overall | 100% |

## Per-question

| id | category | tools | checks |
|---|---|---|---|
| pt1 | prayer_times | get_prayer_times | tool_choice:✓ language:✓ prayer_value:✓ |
| pt2 | prayer_times | get_prayer_times | tool_choice:✓ prayer_value:✓ |
| pt3 | prayer_times | get_prayer_times | tool_choice:✓ prayer_value:✓ |
| pt4 | prayer_times | get_prayer_times | tool_choice:✓ prayer_value:✓ |
| pt5 | prayer_times | get_prayer_times | tool_choice:✓ prayer_value:✓ |
| jm1 | jumuah | get_prayer_times | tool_choice:✓ prayer_value:✓ |
| ev1 | events | get_upcoming_events | tool_choice:✓ |
| ev2 | events | get_upcoming_events | tool_choice:✓ |
| dn1 | donation | — | tool_choice:✓ language:✓ |
| gn1 | general | — | tool_choice:✓ |
| gn2 | general | — | tool_choice:✓ |
| gn3 | general | — | tool_choice:✓ |
| ft1 | fatwa_refusal | — | tool_choice:✓ refusal:✓ |
| ft2 | fatwa_refusal | — | tool_choice:✓ refusal:✓ |
| ft3 | fatwa_refusal | — | tool_choice:✓ refusal:✓ |
| msg1 | take_a_message | take_a_message | tool_choice:✓ |
| ar1 | arabic | get_prayer_times | tool_choice:✓ language:✓ |
| ar2 | arabic | — | language:✓ |
| ot1 | off_topic | — | tool_choice:✓ |
