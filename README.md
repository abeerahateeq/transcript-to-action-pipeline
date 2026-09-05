# Transcript-to-Action Pipeline

A structured-extraction pipeline for meeting transcripts, built to **minimize
hallucinated action items and preserve uncertainty** when meeting information
is ambiguous — not "an AI meeting summarizer."
**Live demo:** https://transcript-to-action-pipeline-fu2qxclibyrvepspsjq7cu.streamlit.app/
## Problem

Meeting-note tools like Otter.ai and Fireflies.ai are good at transcription
and produce readable summaries with action items and named owners. But in
practice:

- They rarely show **why** an item was extracted — there's no way to check
  whether an action item was actually said, or smoothed over from vague
  discussion.
- They tend toward **completeness over honesty**: when ownership or a
  deadline is unclear, the tool still fills in a name or a date rather than
  admitting it doesn't know.
- Ambiguity, disagreement, and "this is still unresolved" get quietly
  dropped, because a clean-looking summary sells better than an honest one.

For a business tool people are supposed to act on, a false "Ali owns this,
due Friday" is worse than no answer at all.

## Solution

This pipeline treats **evidence and uncertainty as first-class output**, not
an afterthought:

- Every action item ships with a **verbatim/near-verbatim evidence quote**
  from the transcript, so a human can verify it in seconds instead of
  trusting the model.
- Owner and deadline are `null` whenever the transcript doesn't actually
  support them — the prompt explicitly forbids inferring from role or
  seniority.
- A **confidence rating** (high/medium/low) is required per item, and an
  **ambiguities list** captures unresolved ownership, contested decisions,
  and open questions instead of forcing a clean answer.
- A **second, independent, rule-based validation pass** (not another LLM
  call) checks whether each evidence quote actually overlaps with the source
  transcript's own wording, and flags items where it doesn't — a cheap,
  deterministic hallucination detector that runs after the model, not
  instead of good prompting.

## Architecture

```
Meeting Transcript (paste or .txt upload)
        │
        ▼
Input / Validation          — length checks, empty-input handling
        │
        ▼
AI Extraction Pipeline      — Claude, forced tool-use call against a fixed
        │                      JSON schema (extraction.py)
        ▼
Structured JSON             — validated against Pydantic models (schema.py):
 ┌───────────────┐            summary, decisions, action items, owners,
 │ Summary       │            deadlines, confidence, evidence
 │ Decisions     │
 │ Action Items  │
 │ Owners        │
 │ Deadlines     │
 │ Confidence    │
 └───────────────┘
        │
        ▼
Validation / Grounding Check — validation.py: does each evidence quote
        │                       actually appear in the transcript?
        ▼
Streamlit Dashboard          — app.py: decisions, action items grouped by
        │                       owner, ambiguities, flagged items
        ▼
Export .docx                 — docx_export.py: python-docx, grouped tables,
                                confidence tags, ambiguity + flags sections
```

## Features

- Paste or upload a `.txt` transcript
- Input validation (empty/too-short/too-long) with clear error states
- Structured extraction via forced tool-use (guaranteed schema, no
  regex-scraping JSON out of prose)
- Pydantic validation as a hard gate before anything reaches the UI
- Rule-based grounding check that flags ungrounded evidence, unsupported
  owners/deadlines, and overstated confidence
- Dashboard with decisions, action items grouped by owner, ambiguities, and
  inline evidence (expandable, with flag reasons shown when relevant)
- One-click `.docx` export: grouped-by-owner tables, confidence tags,
  ambiguities section, and an automated-flags section for reviewers
- Empty-state and error-state handling throughout (no data, failed
  extraction, failed validation all render distinctly instead of crashing)

## Tech Stack

- **Python 3.10+**
- **Streamlit** — UI
- **Google Gemini API** (free tier — structured JSON output)
- **Pydantic v2** — schema enforcement
- **python-docx** — .docx export
- Git/GitHub, VS Code

## API Used

Google's **Gemini API** (`google-genai` SDK), on the free Gemini Developer
API tier (get a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
— no billing account required). Structured output is enforced via
`response_mime_type="application/json"` + `response_schema=MeetingExtraction`,
passing the Pydantic model directly to the SDK. This guarantees a single,
schema-shaped JSON response rather than prose that happens to contain JSON —
no markdown-fence stripping, no partial parses. `response.parsed` returns an
already-validated instance of the exact Pydantic class.

The model is pinned to the `gemini-flash-latest` alias rather than a dated
model name, so the code doesn't need edits every time Google rotates which
generation is "current" — Google manages that mapping. If you hit free-tier
rate limits, swap in `gemini-flash-lite-latest` for a lighter/faster
alternative with the same API shape.

## Prompt Strategy

The system prompt (see `extraction.py::SYSTEM_PROMPT`) encodes ten explicit
rules, arrived at through the Day 6 evaluation cycle:

1. Do not invent action items
2. Distinguish decisions from suggestions
3. Do not infer an owner unless directly supported
4. Do not infer a deadline unless directly stated
5. Every action item requires an evidence quote
6. Preserve uncertainty — record it as an ambiguity instead of resolving it
7. Confidence must be assigned honestly (high/medium/low, defined explicitly)
8. General discussion is not an action item
9. Summary is neutral/factual, not prescriptive
10. Use corrected statements, not retracted ones, but still flag genuine
    unresolved disagreement

Structure enforcement (schema, types, enums) is handled separately by
Pydantic — the prompt's job is exclusively **extraction behavior**, not
formatting.

## Output Schema

```json
{
  "meeting_title": "string",
  "summary": "string",
  "key_decisions": [
    { "decision": "string", "confidence": "high | medium | low" }
  ],
  "action_items": [
    {
      "task": "string",
      "owner": "string | null",
      "deadline": "string | null",
      "confidence": "high | medium | low",
      "evidence": "short transcript quote"
    }
  ],
  "ambiguities": [
    { "issue": "string", "related_item": "string" }
  ]
}
```

Full enforcement lives in `schema.py` (Pydantic models + the JSON schema
handed to the model as the tool's `input_schema`).

## Testing & Evaluation

Four transcripts in `/transcripts` were built specifically to stress the
failure modes that matter for this problem:

| Transcript | Stresses |
|---|---|
| `01_normal_project_meeting.txt` | Baseline correctness |
| `02_messy_interruptions.txt` | Self-corrections, crosstalk, retracted statements, a "vented about but never assigned" item that must NOT become an action item |
| `03_ambiguous_ownership.txt` | Genuinely unclear ownership/deadlines — correct behavior is `null` + an ambiguity entry, not a guess |
| `04_no_action_items.txt` | Small talk and a floated (non-committed) idea — correct behavior is zero or near-zero action items |

Run the harness:

```bash
python eval/run_eval.py
```

This runs every transcript through the full pipeline (extraction →
Pydantic validation → grounding check) and prints per-item confidence,
owner, deadline, evidence, and any grounding flags. Findings, before/after
prompt fixes, and grounding-threshold calibration are logged in
`eval/results.md` — fill that in after your own run, since actual model
output will vary by run and by model version.

## Known Limitations

- The grounding check (`validation.py`) is a **word-overlap heuristic**, not
  semantic verification — it can miss a hallucination phrased with
  transcript-adjacent vocabulary, and can false-flag a legitimate paraphrase
  that uses different words than the transcript.
- No speaker-diarization input — the tool assumes the transcript already has
  speaker labels (or works reasonably without them, but attribution quality
  depends on the source transcript).
- Single transcript at a time; no meeting history, search, or cross-meeting
  tracking (unlike Otter/Fireflies' "AI Chat over meeting history").
- No live/streaming transcription — this pipeline starts from a finished
  transcript, not a live call.
- Evidence quotes are near-verbatim, not guaranteed byte-for-byte exact,
  since the model may lightly normalize whitespace or punctuation.

## Challenges & Solutions

- **Models defaulting to "helpful completeness."** Early prompt drafts still
  produced inferred owners based on role (e.g., assigning backend tasks to
  whoever did backend work generally, not who was actually asked). Fixed by
  making Rule 3 explicit about *what counts* as support (named directly, or
  self-assigned) and adding the `04_no_action_items.txt` regression test to
  catch backsliding.
- **Trusting the model's own confidence score.** A model can mark something
  "high confidence" while still paraphrasing loosely. The grounding check in
  `validation.py` cross-checks confidence against actual evidence-transcript
  overlap and downgrades trust in the UI when they disagree, instead of
  taking the self-reported score at face value.
- **JSON reliability.** Early prototyping without a response schema
  occasionally produced prose-wrapped or truncated JSON. Passing the
  Pydantic model directly as `response_schema` (rather than describing the
  shape in the prompt) removed this failure mode almost entirely; the code
  still falls back to manual `json.loads` + Pydantic validation for the rare
  case where `response.parsed` comes back empty (e.g. output truncated at
  the token limit).

## Future Improvements

- Replace the word-overlap grounding check with sentence-embedding
  similarity for better paraphrase tolerance.
- Multi-transcript / meeting-history view with cross-meeting action-item
  tracking (open vs. closed).
- Direct export to task trackers (Jira/Asana/Trello) alongside .docx.
- Support audio input via a transcription step ahead of extraction.
- Human-in-the-loop correction: let a reviewer edit an item in the dashboard
  and have that correction re-checked against the transcript.

## How to Run

```bash
git clone <your-repo-url>
cd meeting-extractor
pip install -r requirements.txt

# Get a free API key (no billing account needed): https://aistudio.google.com/apikey
cp .env.example .env
# edit .env and add your GEMINI_API_KEY, then:
export $(cat .env | xargs)     # or use a tool like python-dotenv / direnv

streamlit run app.py
```

**Cost:** $0. The Gemini Developer API free tier is quota-based (not a
time-limited trial) and is enough for building, testing, and demoing this
project. No credit card is required to generate a key.

Then in the app: paste or upload a transcript (try the samples in
`/transcripts`), click **Run extraction**, review the dashboard, and
download the `.docx`.

To run the evaluation harness instead of the UI:

```bash
python eval/run_eval.py
```

---

**Demo script (for a short walkthrough):** load
`transcripts/03_ambiguous_ownership.txt` → run extraction → open the
Evidence expander on a couple of action items to show verification → point
out the `null` owner/deadline fields and the Ambiguities section → download
the `.docx` and show the owner-grouped tables and the automated flags
section.
