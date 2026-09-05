# Evaluation Log

Fill this in after running `python eval/run_eval.py` against your API key.
This is the artifact that proves the hallucination-control claims — keep the
before/after entries even after you fix issues, don't just delete the "before".

## Test matrix

| Test | What it verifies | Result | Notes |
|---|---|---|---|
| `01_normal_project_meeting.txt` | Correct summary, decisions vs. suggestions distinguished (color palette = suggestion, not decision), owners/deadlines correctly captured | ☐ Pass / ☐ Fail | |
| `02_messy_interruptions.txt` | Corrected statements used over retracted ones (customs call was "yesterday" not "Tuesday"; follow-up is "afternoon" not "morning"); vented-about packaging item NOT extracted as an action item | ☐ Pass / ☐ Fail | |
| `03_ambiguous_ownership.txt` | Owner/deadline left `null` where genuinely unstated (landing page copy owner, launch date, social post owner); these show up in `ambiguities`, not confidently assigned | ☐ Pass / ☐ Fail | |
| `04_no_action_items.txt` | Zero false-positive action items from small talk / the "onboarding revamp" idea, which was explicitly floated as a non-commitment | ☐ Pass / ☐ Fail | |

## First-version weaknesses found

Document anything the first prompt/pipeline version got wrong, e.g.:

- [ ] False-positive action items (discussion treated as a commitment)
- [ ] Owner inferred from role/seniority rather than explicit statement
- [ ] Deadline defaulted to "ASAP" or invented instead of `null`
- [ ] Evidence quote didn't actually match the transcript wording
- [ ] Confidence marked "high" for something that was actually vague

For each one found, note:
1. **What happened** (paste the bad output)
2. **Which prompt rule was missing or too weak**
3. **The fix** (the exact rule/wording added to `SYSTEM_PROMPT` in `extraction.py`)
4. **Re-test result** after the fix

## Grounding-check calibration

`validation.py` flags an action item when its evidence quote overlaps less
than `EVIDENCE_OVERLAP_THRESHOLD` (default 0.55) with the transcript's own
vocabulary. Record here if that threshold produced too many false alarms
(over-flagging good paraphrases) or missed real hallucinations, and what you
changed it to.

## Summary

_One paragraph: what the evaluation showed about the pipeline's reliability,
and what remains a known limitation (see README's "Known Limitations")._
