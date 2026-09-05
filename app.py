"""
app.py
------
Streamlit dashboard for the transcript-to-action pipeline.

Flow: transcript input -> validation -> AI extraction -> pydantic-checked
structured JSON -> rule-based grounding check -> dashboard -> .docx export.
"""

from __future__ import annotations

import os
from datetime import datetime

import streamlit as st

from docx_export import build_docx
from extraction import extract_meeting
from schema import Confidence
from validation import validate_extraction

st.set_page_config(page_title="Transcript-to-Action Pipeline", page_icon="🗒️", layout="wide")

MIN_TRANSCRIPT_CHARS = 100
MAX_TRANSCRIPT_CHARS = 60_000

CONFIDENCE_BADGE = {
    "high": "🟢 High",
    "medium": "🟡 Medium",
    "low": "🔴 Low",
}


def confidence_badge(value) -> str:
    v = value.value if isinstance(value, Confidence) else str(value)
    return CONFIDENCE_BADGE.get(v, v)


def init_state():
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("validation_report", None)
    st.session_state.setdefault("transcript_used", "")
    st.session_state.setdefault("source_filename", None)


init_state()

st.title("🗒️ Transcript-to-Action Pipeline")
st.caption(
    "A structured extraction pipeline built to minimize hallucinated action items and "
    "preserve uncertainty when meeting information is ambiguous — not just another summarizer."
)

with st.sidebar:
    st.header("About this tool")
    st.markdown(
        """
Most meeting-note tools optimize for **completeness** — they'd rather guess an
owner or deadline than leave a blank. This tool optimizes for **trustworthiness**:

- Every action item carries an **evidence quote** you can check against the transcript.
- Owners and deadlines are `null` when the transcript doesn't actually support them.
- Ambiguous ownership or unresolved decisions are surfaced explicitly, not smoothed over.
- A second, rule-based pass flags any item whose evidence doesn't actually match the transcript text.
        """
    )
    st.divider()
    api_key_present = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    st.markdown(f"**API key detected:** {'✅ yes' if api_key_present else '❌ no — set GEMINI_API_KEY'}")
    st.caption("Free key: https://aistudio.google.com/apikey")
    st.divider()
    st.markdown("**Sample transcripts** (in `/transcripts`):")
    st.markdown(
        "- `01_normal_project_meeting.txt` — clean baseline\n"
        "- `02_messy_interruptions.txt` — corrections & crosstalk\n"
        "- `03_ambiguous_ownership.txt` — unclear owners/deadlines"
    )

tab_input, tab_dashboard = st.tabs(["📝 Input", "📊 Dashboard"])

with tab_input:
    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded = st.file_uploader("Upload a transcript (.txt)", type=["txt"])
        transcript_text = ""
        if uploaded is not None:
            transcript_text = uploaded.read().decode("utf-8", errors="ignore")
            st.session_state["source_filename"] = uploaded.name
        else:
            st.session_state["source_filename"] = None

        transcript_text = st.text_area(
            "Or paste the transcript here",
            value=transcript_text,
            height=350,
            placeholder="Paste a raw meeting transcript, including speaker names if available...",
        )

    with col2:
        meeting_title_hint = st.text_input("Meeting title (optional)", placeholder="e.g. Q3 Planning Sync")
        st.markdown(" ")
        run_button = st.button("🚀 Run extraction", type="primary", use_container_width=True)

    # --- Input validation ---
    validation_errors = []
    stripped = transcript_text.strip()
    if run_button:
        if not stripped:
            validation_errors.append("Transcript is empty. Paste or upload a transcript first.")
        elif len(stripped) < MIN_TRANSCRIPT_CHARS:
            validation_errors.append(
                f"Transcript looks too short ({len(stripped)} chars) to contain a real meeting. "
                f"Minimum expected: {MIN_TRANSCRIPT_CHARS} characters."
            )
        elif len(stripped) > MAX_TRANSCRIPT_CHARS:
            validation_errors.append(
                f"Transcript is too long ({len(stripped)} chars, max {MAX_TRANSCRIPT_CHARS}). "
                "Split it into smaller segments."
            )

        if validation_errors:
            for err in validation_errors:
                st.error(err)
        else:
            with st.spinner("Running extraction pipeline — calling the model, then validating the result..."):
                try:
                    result = extract_meeting(stripped, meeting_title_hint or None)
                except RuntimeError as e:
                    result = None
                    st.error(str(e))

            if result is not None:
                if not result.success:
                    st.error(f"Extraction failed: {result.error}")
                    if result.raw_input:
                        with st.expander("Raw model output (failed validation)"):
                            st.json(result.raw_input)
                else:
                    st.session_state["result"] = result
                    st.session_state["transcript_used"] = stripped
                    st.session_state["validation_report"] = validate_extraction(result.data, stripped)
                    st.success("Extraction complete. Switch to the Dashboard tab to review.")

with tab_dashboard:
    result = st.session_state.get("result")

    if result is None:
        st.info("No extraction yet. Go to the **Input** tab, add a transcript, and run the pipeline.")
    else:
        data = result.data
        report = st.session_state["validation_report"]

        st.subheader(data.meeting_title)
        st.write(data.summary)

        if report.warnings:
            for w in report.warnings:
                st.warning(w)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Decisions", len(data.key_decisions))
        m2.metric("Action items", len(data.action_items))
        m3.metric("Ambiguities flagged", len(data.ambiguities))
        m4.metric(
            "Validation flags",
            len(report.flagged_action_items),
            delta=None if not report.flagged_action_items else "review needed",
            delta_color="inverse",
        )

        st.divider()

        left, right = st.columns([1, 1])

        with left:
            st.markdown("### ✅ Key Decisions")
            if data.key_decisions:
                for d in data.key_decisions:
                    st.markdown(f"- {d.decision}  \n  {confidence_badge(d.confidence)}")
            else:
                st.caption("No firm decisions were extracted.")

            st.markdown("### ❓ Ambiguities & Open Questions")
            if data.ambiguities:
                for a in data.ambiguities:
                    st.markdown(f"- **{a.issue}**  \n  _related to: {a.related_item}_")
            else:
                st.caption("None identified by the model.")

        with right:
            st.markdown("### 📋 Action Items — grouped by owner")
            if data.action_items:
                grouped: dict = {}
                for item in data.action_items:
                    grouped.setdefault(item.owner or "Unassigned", []).append(item)
                ordered_keys = sorted(k for k in grouped if k != "Unassigned")
                if "Unassigned" in grouped:
                    ordered_keys.append("Unassigned")

                flagged_tasks = {f.item.task for f in report.flagged_action_items}

                for owner in ordered_keys:
                    st.markdown(f"**{owner}**")
                    for item in grouped[owner]:
                        flag = " ⚠️" if item.task in flagged_tasks else ""
                        deadline_str = item.deadline if item.deadline else "_no deadline stated_"
                        st.markdown(
                            f"- {item.task}{flag}  \n"
                            f"  {confidence_badge(item.confidence)} · {deadline_str}"
                        )
                        with st.expander("Evidence"):
                            st.markdown(f"> {item.evidence}")
                            if item.task in flagged_tasks:
                                flagged = next(f for f in report.flagged_action_items if f.item.task == item.task)
                                for reason in flagged.reasons:
                                    st.caption(f"⚠️ {reason}")
            else:
                st.caption("No action items were extracted from this transcript.")

        st.divider()
        st.markdown("### 📄 Export")
        docx_buffer = build_docx(
            data,
            validation_report=report,
            source_filename=st.session_state.get("source_filename"),
        )
        filename = f"meeting-notes-{datetime.now().strftime('%Y%m%d-%H%M')}.docx"
        st.download_button(
            "⬇️ Download meeting notes (.docx)",
            data=docx_buffer,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=False,
        )

        with st.expander("🔍 Raw structured JSON (for debugging / evaluation)"):
            st.json(result.raw_input)
