"""Diagnose: which evidence drives each verdict for the generated test set."""
import os

os.environ["MODEL_PROVIDER"] = "mock"

from pathlib import Path

from src.data.user_upload import cases_from_upload
from src.orchestrator import Orchestrator

data = Path("examples/test_dataset.csv").read_bytes()
cases = cases_from_upload(data, "test_dataset.csv", limit=10)
for case in cases:
    res = Orchestrator().investigate(case)
    print(f"\n{case.focus_account:<16} alert={case.alert_type:<15} "
          f"verdict={res.verdict.value} conf={res.confidence} dec={res.decision.value}")
    for e in res.evidence:
        mark = "+" if e.verified else "-"
        print(f"   {mark} [{e.agent}] w={e.weight} {e.supports.value:<10} {e.claim[:90]}")
        print(f"       src={e.source[:80]}")
