"""CLI entrypoint — investigate a real transaction file end to end and print
the governed audit trail plus each verdict.

    python -m src.main examples/sample_transactions.csv
    python -m src.main ledger.xlsx --focus ACC1042
    python -m src.main export.json --limit 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows consoles default to cp1252; force UTF-8 so the audit-trail emoji render.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from .band.interface import AuditEvent
from .casework import get_department
from .data.user_upload import cases_from_upload
from .models.client import TOKEN_LEDGER


def _print_event(ev: AuditEvent) -> None:
    tag = {"joined": "👥", "evidence": "🔎", "challenge": "🥊", "verify": "✅",
           "rejected": "⛔", "consortium": "🤝", "verdict": "⚖️", "gate": "🧑‍⚖️",
           "clear": "🟢"}.get(ev.kind, "•")
    if ev.kind == "verify":
        tag = "✅" if ev.payload.get("verified") else "❌"
    summary = ev.payload.get("claim") or ev.payload.get("note") or ev.payload.get(
        "verdict") or ev.payload.get("role") or ev.kind
    print(f"  {tag} [{ev.actor}] {summary}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Investigate a transaction file (CSV / Excel / JSON / text PDF).")
    ap.add_argument("file", help="path to the transaction file to investigate")
    ap.add_argument("--focus", default=None,
                    help="investigate one named account instead of risk-triaging")
    ap.add_argument("--limit", type=int, default=3,
                    help="how many top-risk accounts to investigate (default 3)")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")
    try:
        cases = cases_from_upload(path.read_bytes(), path.name, args.focus, args.limit)
    except ValueError as exc:
        raise SystemExit(f"Could not parse {path.name}: {exc}")

    dept = get_department()
    print(f"\n{path.name}: {len(cases)} account(s) selected by risk triage")
    for case in cases:
        print(f"\n=== AEGIS investigating {case.focus_account} "
              f"({case.alert_type}, {len(case.transactions)} txns) ===\n")
        result = dept.orchestrator().investigate(case, on_event=_print_event)
        row = dept.record_case(case, result, source_file=path.name)

        print("\n--- VERDICT ---")
        print(f"  Verdict:    {result.verdict.value}  (confidence {result.confidence})")
        print(f"  Decision:   {result.decision.value}")
        print(f"  Rationale:  {result.rationale}")
        print(f"  Casebook:   filed as {row['uid']} · priority {row['priority']}"
              + (f" · review due {row['sla_due'][:16]}" if row["sla_due"] else ""))
        if result.qa_findings:
            print(f"  QA:         score {result.qa_score} — "
                  + "; ".join(result.qa_findings))
        if result.rejected_claims:
            print(f"  Rejected:   {len(result.rejected_claims)} claim(s) during verification")
        if result.consortium_confirmation:
            print(f"  Consortium: {result.consortium_confirmation}")
        if result.report:
            print(f"\n--- DRAFT SAR ---\n{result.report}")

    approx = sum(e["approx_tokens"] for e in TOKEN_LEDGER)
    print(f"\n(approx LLM tokens this run: {approx}; provider calls logged: {len(TOKEN_LEDGER)})")


if __name__ == "__main__":
    main()
