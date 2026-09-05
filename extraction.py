"""
extraction.py
-------------
The AI extraction pipeline. Calls Google's Gemini API (free tier) with a
Pydantic response_schema so the SDK enforces structure at decode time -
the same reliability guarantee tool-use gives on other providers, just
via Gemini's native structured-output support.

The prompt is the main hallucination-control mechanism. See PROMPT_RULES
below and eval/test_cases.md for how these rules were arrived at.

MODEL = "gemini-flash-lite-latest" is a Google-managed alias that always points
at their current recommended flash model, so this code doesn't need
updating every time Google ships a new generation. It's covered by the
free Gemini Developer API tier (ai.google.dev) - no billing required.
If you hit free-tier rate limits, gemini-flash-lite-latest is an even
cheaper/faster fallback with the same API shape.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import ValidationError

from schema import MeetingExtraction

MODEL = "gemini-flash-lite-latest"

SYSTEM_PROMPT = """You are a meeting-extraction engine. You read a raw meeting \
transcript and extract ONLY what was actually said. You are not a creative \
assistant and you do not fill in gaps to make output look complete.

Extraction rules (follow all of them; violating any of them is a failure):

1. Do not invent action items. If no one actually committed to or was assigned \
a task, do not create one just because a topic was discussed.
2. Distinguish decisions from suggestions. A decision was agreed to or settled. \
A suggestion, idea, or "maybe we should" was raised but not settled. Suggestions \
that were not adopted are not decisions and are not action items.
3. Do not infer an owner unless the transcript directly supports it (someone was \
named, or said "I'll do it" / "I've got it" / was directly assigned by another \
speaker). If ownership is unclear or unstated, set "owner" to null - do not \
guess based on role or seniority.
4. Do not infer a deadline unless one was actually stated (a date, "by Friday", \
"next sprint", etc.). If no deadline was mentioned, set "deadline" to null - do \
not default to "ASAP" or invent a date.
5. Every action item MUST include an "evidence" field: a short quote or close \
paraphrase from the transcript (under ~20 words) that a human could use to find \
and verify the line it came from. If you cannot point to specific words that \
justify the item, do not include the item.
6. Preserve uncertainty rather than resolving it. If the transcript is genuinely \
ambiguous about who owns something, what the deadline is, or whether something \
was actually decided, record that ambiguity in the "ambiguities" list rather \
than silently picking the most likely interpretation.
7. Assign "confidence" honestly per item:
   - high: explicitly and unambiguously stated
   - medium: stated but with some vagueness, indirection, or partial information
   - low: implied or inferable but not directly stated - include with caution
8. General discussion, brainstorming, or background context is not an action \
item unless it resulted in a concrete task assigned to someone or the group.
9. The summary should be neutral and factual - describe what was discussed and \
decided, not what should happen next (that belongs in action_items).
10. If the transcript contains interruptions, crosstalk, or corrections \
("actually, scratch that", "no wait, I meant..."), use the final, corrected \
statement - not the retracted one - but still capture genuine unresolved \
disagreement as an ambiguity.

Return your extraction matching the provided response schema exactly. Use null \
(not empty strings, not "unknown", not "N/A") for owner/deadline fields that \
the transcript does not support."""


@dataclass
class ExtractionResult:
    success: bool
    data: Optional[MeetingExtraction] = None
    raw_input: Optional[dict] = None
    error: Optional[str] = None
    stop_reason: Optional[str] = None


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey "
            "and export it (or add it to a .env file) before running the app."
        )
    return genai.Client(api_key=api_key)


def extract_meeting(transcript: str, meeting_title_hint: Optional[str] = None) -> ExtractionResult:
    """
    Run the transcript through Gemini with a Pydantic response schema, then
    re-validate the result explicitly. Returns an ExtractionResult that the
    UI can render regardless of whether extraction succeeded, partially
    succeeded, or failed outright - failure is a normal, expected path here,
    not an exception to be swallowed.
    """
    client = _get_client()

    user_content = "Extract structured data from this meeting transcript.\n\n"
    if meeting_title_hint:
        user_content += (
            f'Suggested meeting title (use if the transcript does not state one clearly): '
            f'"{meeting_title_hint}"\n\n'
        )
    user_content += f"--- TRANSCRIPT START ---\n{transcript}\n--- TRANSCRIPT END ---"

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=MeetingExtraction,
                temperature=0.2,
            ),
        )
    except APIError as e:
        return ExtractionResult(success=False, error=f"Gemini API error: {e}")

    if not response.candidates:
        return ExtractionResult(
            success=False,
            error="Model returned no candidates (likely blocked by safety filters).",
            stop_reason=getattr(response, "prompt_feedback", None) and str(response.prompt_feedback),
        )

    finish_reason = response.candidates[0].finish_reason

    # response.parsed is the SDK's already-instantiated Pydantic object when
    # response_schema is a Pydantic model and parsing succeeded. If parsing
    # failed (e.g. truncated output), it will be None and we fall back to
    # validating the raw text ourselves so we always know exactly why.
    if response.parsed is not None:
        validated = response.parsed
        raw_input = validated.model_dump()
        return ExtractionResult(success=True, data=validated, raw_input=raw_input, stop_reason=str(finish_reason))

    raw_text = response.text
    if not raw_text:
        return ExtractionResult(
            success=False,
            error="Model returned an empty response.",
            stop_reason=str(finish_reason),
        )

    try:
        raw_input = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return ExtractionResult(
            success=False,
            error=f"Model output was not valid JSON: {e}",
            stop_reason=str(finish_reason),
        )

    try:
        validated = MeetingExtraction.model_validate(raw_input)
    except ValidationError as e:
        return ExtractionResult(
            success=False,
            raw_input=raw_input,
            error=f"Schema validation failed: {e}",
            stop_reason=str(finish_reason),
        )

    return ExtractionResult(success=True, data=validated, raw_input=raw_input, stop_reason=str(finish_reason))
