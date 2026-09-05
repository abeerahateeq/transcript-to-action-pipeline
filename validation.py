"""
validation.py
--------------
A second, independent layer of hallucination control that runs AFTER the LLM
call and does NOT trust the model. Pydantic (schema.py) only checks shape
(types, enums, non-blank strings). This module checks substance:

- Does the "evidence" quote for each action item actually appear in the
  source transcript (fuzzy match)? If not, the item is very likely invented
  or badly paraphrased, and we flag it instead of silently trusting it.
- Are there action items with high confidence but weak/short evidence?
- Are there owners or deadlines that don't appear anywhere in the transcript?

This is deliberately simple (token overlap, not another LLM call) so it is
fast, free, deterministic, and auditable - a reviewer can see exactly why
something was flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from schema import ActionItem, MeetingExtraction

_WORD_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> set:
    return set(_WORD_RE.findall(text.lower()))


def _overlap_ratio(evidence: str, transcript_tokens: set) -> float:
    """Fraction of the evidence's meaningful words that appear in the transcript."""
    ev_tokens = _tokenize(evidence)
    if not ev_tokens:
        return 0.0
    matched = ev_tokens & transcript_tokens
    return len(matched) / len(ev_tokens)


@dataclass
class FlaggedItem:
    item: ActionItem
    reasons: List[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    flagged_action_items: List[FlaggedItem] = field(default_factory=list)
    unsupported_owners: List[str] = field(default_factory=list)
    unsupported_deadlines: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.flagged_action_items or self.unsupported_owners or self.unsupported_deadlines)


EVIDENCE_OVERLAP_THRESHOLD = 0.55  # below this, evidence probably isn't really in the transcript
MIN_EVIDENCE_WORDS = 3


def validate_extraction(extraction: MeetingExtraction, transcript: str) -> ValidationReport:
    report = ValidationReport()
    transcript_tokens = _tokenize(transcript)

    for item in extraction.action_items:
        reasons = []

        overlap = _overlap_ratio(item.evidence, transcript_tokens)
        if overlap < EVIDENCE_OVERLAP_THRESHOLD:
            reasons.append(
                f"Evidence quote only overlaps {overlap:.0%} with transcript wording — "
                "possibly paraphrased too loosely or not actually present."
            )

        if len(_tokenize(item.evidence)) < MIN_EVIDENCE_WORDS:
            reasons.append("Evidence is very short — hard to verify against the transcript.")

        if item.confidence == "high" and overlap < 0.8:
            reasons.append(
                "Marked 'high' confidence but evidence isn't a close match to transcript text — "
                "confidence may be overstated."
            )

        if item.owner:
            owner_tokens = _tokenize(item.owner)
            if owner_tokens and not (owner_tokens & transcript_tokens):
                report.unsupported_owners.append(item.owner)
                reasons.append(f"Owner '{item.owner}' does not appear anywhere in the transcript text.")

        if item.deadline:
            deadline_tokens = _tokenize(item.deadline)
            if deadline_tokens and not (deadline_tokens & transcript_tokens):
                report.unsupported_deadlines.append(item.deadline)
                reasons.append(f"Deadline '{item.deadline}' does not appear anywhere in the transcript text.")

        if reasons:
            report.flagged_action_items.append(FlaggedItem(item=item, reasons=reasons))

    if not extraction.action_items:
        report.warnings.append("No action items were extracted — verify this transcript actually contained none.")

    if not extraction.ambiguities and len(extraction.action_items) > 0:
        # Not necessarily wrong, but worth a soft note in the UI.
        pass

    return report
