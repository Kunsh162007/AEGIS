"""CLI entrypoint — run one investigation end to end and print the result.

    python -m src.main                     # structuring fixture
    python -m src.main --fixture mule --consortium
    python -m src.main --fixture salary    # benign-but-flagged -> watch it get cleared
"""
from __future__ import annotations

import argparse
import sys

# Windows consoles default to cp1252; force UTF-8 so the demo emoji render.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from .band import LocalMesh
from .band.interface import AuditEvent
from .data.synthetic import DEMO_FIXTURES, get_fixture
from .models.client import TOKEN_LEDGER
from .orchestrator import Orchestrator


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
    ap = argparse.ArgumentParser(description="Run an AEGIS investigation.")
    ap.add_argument("--fixture", default="structuring", choices=list(DEMO_FIXTURES))
    ap.add_argument("--consortium", action="store_true")
    args = ap.parse_args()

    case = get_fixture(args.fixture)
    print(f"\n=== AEGIS investigating {case.case_id} ({case.alert_type}) ===\n")

    peers = []
    if args.consortium:
        peer = LocalMesh(tenant_id="bank-beta")
        peer.publish_pattern({"typology": "fan-in-then-burst", "txn_window_h": 72,
                              "legs": 5, "passthrough": True})
        peers = ["bank-beta"]

    orch = Orchestrator()
    result = orch.investigate(case, peers, on_event=_print_event)

    print("\n--- VERDICT ---")
    print(f"  Verdict:    {result.verdict.value}  (confidence {result.confidence})")
    print(f"  Decision:   {result.decision.value}")
    print(f"  Rationale:  {result.rationale}")
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
