\# Evaluation Log



Run against the live deployed app (Streamlit Cloud) using `gemini-flash-latest`,

2026-09-05, all 4 sample transcripts. Local CLI run (`eval/run\_eval.py`) was

blocked by a local Windows TLS/SSL issue unrelated to the pipeline itself

(confirmed: the same code runs cleanly on Streamlit Cloud); results below were

gathered by running each transcript through the live app UI and exporting the

.docx for review instead.



\## Test matrix



| Test | What it verifies | Result | Notes |

|---|---|---|---|

| `01\_normal\_project\_meeting.txt` | Correct summary, decisions vs. suggestions distinguished, owners/deadlines correctly captured | ✅ Pass | Color-palette revisit correctly kept as a suggestion/ambiguity, not a decision. All 4 owners (Daniyal, Hina, Omar) and their deadlines/evidence extracted correctly. |

| `02\_messy\_interruptions.txt` | Corrected statements used over retracted ones; vented-about packaging item NOT extracted as an action item | ✅ Pass | Deadline correctly resolved to "tomorrow afternoon" (the correction), not the retracted "tomorrow morning." Packaging-supplier venting correctly excluded from action\_items entirely. |

| `03\_ambiguous\_ownership.txt` | Owner/deadline left `null` where genuinely unstated; these show up in `ambiguities`, not confidently assigned | ✅ Pass (with a nuance) | Deadline correctly null. Launch date / press release / social-post ownership correctly left as ambiguities only, with NO invented action items or owners for them — this is the important hallucination-avoidance behavior. One judgment call: Noor was listed as owner of "try to start the copy" (self-volunteered, so defensible) while ownership of the broader copy task was separately flagged as ambiguous — not a contradiction, but worth watching in future runs. |

| `04\_no\_action\_items.txt` | Zero false-positive action items from small talk / the "onboarding revamp" idea | ✅ Pass | Zero action items extracted. Onboarding-revamp idea correctly treated as a non-committal idea, not a task. Strongest result of the four — this is exactly the false-positive trap this transcript exists to catch. |



\## First-version weaknesses found



No outright failures on this run — all 4 transcripts behaved as expected on

the first prompt version. The one soft issue:



1\. \*\*What happened:\*\* In `03\_ambiguous\_ownership.txt`, the model both (a)

&#x20;  assigned an owner (Noor) to a scoped-down version of a task, and (b)

&#x20;  flagged the broader version of the same task as an ownership ambiguity.

2\. \*\*Which prompt rule is involved:\*\* Rule 3 (owner inference) and Rule 6

&#x20;  (preserve ambiguity) can both fire on the same underlying task when a

&#x20;  person volunteers conditionally ("I'll try if I get time"). The prompt

&#x20;  doesn't currently say how to handle partial/conditional self-assignment.

3\. \*\*Possible fix (not yet applied):\*\* Add a clarifying rule: "If someone

&#x20;  volunteers conditionally or partially for a task that the group has not

&#x20;  fully resolved ownership of, extract the conditional commitment as a

&#x20;  low-confidence action item AND note the remaining ambiguity separately —

&#x20;  this is not a contradiction, but state both explicitly in the evidence

&#x20;  text so it reads as 'partial ownership,' not full ownership."

4\. \*\*Re-test result:\*\* Not yet re-tested — flagged for next iteration.



\## Grounding-check calibration



No items were flagged by the rule-based grounding check (`validation.py`)

on any of the 4 transcripts — every evidence quote had strong word overlap

with the source transcript. No threshold adjustment needed based on this run.

Note: this run was evaluated via the deployed app's dashboard/docx output,

which does surface grounding flags in the UI and in the exported .docx

("Automated Validation Flags" section) — none appeared, so the check had

nothing to catch here. A future eval pass should include a transcript with a

deliberately fabricated action item to confirm the grounding check still

fires correctly (it was previously verified locally with a mock, see

project history).



\## Summary



Across all 4 test transcripts, the pipeline showed no hallucinated action

items, correctly distinguished decisions from suggestions, correctly used

corrected statements over retracted ones, and correctly left owner/deadline

fields null when the transcript didn't support them — recording the

uncertainty as an ambiguity instead of guessing. The only nuance worth

tracking is how the prompt should describe \*partial\* or \*conditional\*

self-assignment, which surfaced once (transcript 03) as a defensible but

slightly ambiguous double-classification. Known limitation carried over from

the README: the grounding check is word-overlap based, not semantic, so this

run cannot confirm how well it catches paraphrased hallucinations — only that

it stayed quiet when the extraction was clean.

