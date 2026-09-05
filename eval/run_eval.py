"""
eval/run_eval.py
-----------------
Day-6 evaluation harness. Runs every transcript in /transcripts through the
extraction pipeline + validation layer and prints a report:

- Did extraction succeed / pass schema validation?
- How many decisions / action items / ambiguities were found?
- Did the rule-based grounding check flag anything (potential hallucination)?
- For 04_no_action_items.txt specifically: did the model correctly extract
  zero (or near-zero) action items instead of inventing some from small talk?

Run with:  python eval/run_eval.py
Requires GEMINI_API_KEY to be set (free key: https://aistudio.google.com/apikey).
"""

from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extraction import extract_meeting
from validation import validate_extraction

TRANSCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "transcripts")

EXPECTATIONS = {
    "01_normal_project_meeting.txt": "Baseline: expect several decisions + action items, most with named owners/deadlines.",
    "02_messy_interruptions.txt": "Expect corrected statements used (not retracted ones); the vented-about 'packaging supplier' item should NOT appear as an action item.",
    "03_ambiguous_ownership.txt": "Expect owner/deadline fields left null in several places, and 2-3 ambiguities recorded (copy ownership, launch date, social post ownership).",
    "04_no_action_items.txt": "Expect zero or near-zero action items — the 'onboarding revamp' idea is a suggestion, not a task, and must not be invented as one.",
}


def run():
    files = sorted(glob.glob(os.path.join(TRANSCRIPT_DIR, "*.txt")))
    if not files:
        print("No transcripts found in /transcripts.")
        return

    for path in files:
        name = os.path.basename(path)
        print("=" * 80)
        print(f"FILE: {name}")
        if name in EXPECTATIONS:
            print(f"EXPECTATION: {EXPECTATIONS[name]}")
        with open(path, "r", encoding="utf-8") as f:
            transcript = f.read()

        result = extract_meeting(transcript)
        if not result.success:
            print(f"  ❌ Extraction/validation FAILED: {result.error}")
            continue

        data = result.data
        report = validate_extraction(data, transcript)

        print(f"  Decisions: {len(data.key_decisions)} | Action items: {len(data.action_items)} | Ambiguities: {len(data.ambiguities)}")
        for item in data.action_items:
            owner = item.owner or "— (null)"
            deadline = item.deadline or "— (null)"
            print(f"    - [{item.confidence}] {item.task} | owner={owner} | deadline={deadline}")
            print(f'      evidence: "{item.evidence}"')

        if report.flagged_action_items:
            print(f"  ⚠️  {len(report.flagged_action_items)} item(s) flagged by grounding check:")
            for flagged in report.flagged_action_items:
                print(f"     - {flagged.item.task}")
                for reason in flagged.reasons:
                    print(f"         reason: {reason}")
        else:
            print("  ✅ No grounding issues flagged.")

    print("=" * 80)
    print("Done. Compare output against EXPECTATIONS above and log findings in eval/results.md.")


if __name__ == "__main__":
    run()
