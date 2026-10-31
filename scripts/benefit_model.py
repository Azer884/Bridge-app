"""The benefit model behind section 4 of the final report: owner time and steps per WhatsApp enquiry, before and with Gesir.

    python scripts/benefit_model.py                      # the team's stated assumptions
    python scripts/benefit_model.py --enquiries 30       # change one assumption

The baseline is the Phase 1 figure (10 to 15 hours a week on enquiries, midpoint used). The "with Gesir" times are
assumptions, not measurements: replace them with the numbers from /api/audit once real owners use it. The step counts come
from the business config, so they follow the fields the assistant really collects.
"""
import argparse
import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config" / "business_config.example.json"


def model(enquiries=20, baseline_hours=12.5, review_min=2.0, approve_min=0.5, handover_rate=0.15, handover_min=5.0,
          quote_hours=None, fields=None):
    fields = fields if fields is not None else len(json.loads(CONFIG.read_text(encoding="utf-8"))["required_fields"])
    before_min = baseline_hours * 60 / enquiries
    with_min = review_min + approve_min + handover_rate * handover_min
    # manual steps for one enquiry: ask each detail, then work out the area, price it, write the quote, propose a slot, send it
    steps_before = fields + 4
    steps_with = 2 + handover_rate                      # review and approve, plus a reply when a chat is handed over
    return {
        "enquiries_per_week": enquiries,
        "owner_minutes_per_enquiry_before": round(before_min, 1),
        "owner_minutes_per_enquiry_with_gesir": round(with_min, 2),
        "owner_hours_per_week_before": baseline_hours,
        "owner_hours_per_week_with_gesir": round(enquiries * with_min / 60, 2),
        "hours_saved_per_week": round(enquiries * (before_min - with_min) / 60, 1),
        "time_reduction_percent": round(100 * (1 - with_min / before_min), 1),
        "manual_steps_before": steps_before,
        "manual_steps_with_gesir": round(steps_with, 2),
        "steps_removed_percent": round(100 * (1 - steps_with / steps_before), 1),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--enquiries", type=int, default=20, help="enquiries the owner handles per week (assumption)")
    ap.add_argument("--baseline-hours", type=float, default=12.5, help="Phase 1 baseline, hours per week")
    ap.add_argument("--review-min", type=float, default=2.0, help="minutes to read the draft and the photos")
    ap.add_argument("--approve-min", type=float, default=0.5)
    ap.add_argument("--handover-rate", type=float, default=0.15, help="share of chats handed to the owner")
    ap.add_argument("--handover-min", type=float, default=5.0, help="minutes to answer a handed-over chat")
    args = ap.parse_args()
    for key, value in model(args.enquiries, args.baseline_hours, args.review_min, args.approve_min,
                            args.handover_rate, args.handover_min).items():
        print(f"{key:42} {value}")
