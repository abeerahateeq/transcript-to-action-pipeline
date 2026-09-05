"""
schema.py
---------
Pydantic models that define the contract between the LLM and the rest of the
application. The extraction pipeline asks the model to return JSON matching
this shape; Pydantic then validates it before anything touches the UI or the
.docx export. If the model returns malformed JSON, an out-of-range confidence
value, or a field of the wrong type, validation fails loudly here instead of
silently corrupting the dashboard downstream.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Confidence(str, Enum):
    """How sure the model is that an item was actually stated, not inferred."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class KeyDecision(BaseModel):
    decision: str = Field(..., min_length=1, description="The decision, stated as a fact.")
    confidence: Confidence

    @field_validator("decision")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("decision text cannot be blank")
        return v


class ActionItem(BaseModel):
    task: str = Field(..., min_length=1, description="What needs to be done.")
    owner: Optional[str] = Field(
        default=None, description="Person responsible. Null if not stated in the transcript."
    )
    deadline: Optional[str] = Field(
        default=None, description="Due date/time as stated. Null if not stated."
    )
    confidence: Confidence
    evidence: str = Field(
        ...,
        min_length=1,
        description="A short verbatim-or-near-verbatim quote from the transcript that supports this item.",
    )

    @field_validator("task", "evidence")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("field cannot be blank")
        return v

    @field_validator("owner", "deadline")
    @classmethod
    def empty_string_becomes_none(cls, v: Optional[str]) -> Optional[str]:
        # Models sometimes emit "" or "unknown"/"n/a" instead of null. Normalize.
        if v is None:
            return None
        v = v.strip()
        if v == "" or v.lower() in {"n/a", "na", "unknown", "none", "tbd"}:
            return None
        return v


class Ambiguity(BaseModel):
    issue: str = Field(..., min_length=1, description="What is unclear or contested.")
    related_item: str = Field(
        ..., min_length=1, description="The decision or action item this ambiguity relates to."
    )


class MeetingExtraction(BaseModel):
    meeting_title: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    key_decisions: List[KeyDecision] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    ambiguities: List[Ambiguity] = Field(default_factory=list)

    class Config:
        use_enum_values = False


# JSON schema handed to the model as part of the prompt (kept separate from
# MeetingExtraction.model_json_schema() so we control exactly what the model sees —
# terser and with descriptions tuned for extraction behavior, not developer docs).
EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "meeting_title": {"type": "string"},
        "summary": {"type": "string", "description": "3-6 sentence neutral summary of what was discussed."},
        "key_decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["decision", "confidence"],
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": ["string", "null"]},
                    "deadline": {"type": ["string", "null"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "evidence": {"type": "string", "description": "Short quote from the transcript."},
                },
                "required": ["task", "owner", "deadline", "confidence", "evidence"],
            },
        },
        "ambiguities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string"},
                    "related_item": {"type": "string"},
                },
                "required": ["issue", "related_item"],
            },
        },
    },
    "required": ["meeting_title", "summary", "key_decisions", "action_items", "ambiguities"],
}
