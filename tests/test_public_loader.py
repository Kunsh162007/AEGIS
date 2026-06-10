"""The public-benchmark loader must aggregate rows into multi-transaction cases
so AEGIS's structural detectors actually fire (a single-transaction case can't
exhibit structuring / pass-through / a mule hub). These checks pin that down on
a tiny PaySim-shaped CSV so a regression to one-row-per-case is caught."""
from __future__ import annotations

import pandas as pd

from src.data.public_loader import bundled_sample_path, load_public
from src.data.schema import Verdict
from src.eval.harness import evaluate
from src.orchestrator import Orchestrator


def _write_paysim_csv(path) -> str:
    rows = [
        # A money mule: three feeders transfer in, then a fast cash-out (pass-through).
        {"step": 1, "type": "TRANSFER", "amount": 5000, "nameOrig": "C1", "nameDest": "MULE0", "isFraud": 1},
        {"step": 1, "type": "TRANSFER", "amount": 5200, "nameOrig": "C2", "nameDest": "MULE0", "isFraud": 1},
        {"step": 2, "type": "TRANSFER", "amount": 4800, "nameOrig": "C3", "nameDest": "MULE0", "isFraud": 1},
        {"step": 3, "type": "CASH_OUT", "amount": 14500, "nameOrig": "MULE0", "nameDest": "MERCH", "isFraud": 1},
        # A benign but LARGE one-off credit — the classic size-only false positive.
        {"step": 1, "type": "PAYMENT", "amount": 50000, "nameOrig": "BIGPAY", "nameDest": "CUST0", "isFraud": 0},
        # Benign noise.
        {"step": 2, "type": "PAYMENT", "amount": 300, "nameOrig": "SHOP", "nameDest": "CUST1", "isFraud": 0},
        {"step": 4, "type": "PAYMENT", "amount": 420, "nameOrig": "SHOP", "nameDest": "CUST2", "isFraud": 0},
    ]
    p = str(path / "paysim_mini.csv")
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def test_loader_aggregates_into_multitransaction_cases(tmp_path):
    csv = _write_paysim_csv(tmp_path)
    cases = load_public(path=csv, kind="paysim", limit=20)

    # At least one case must carry several transactions (proves aggregation).
    assert any(len(c.transactions) > 1 for c in cases)

    mule = next(c for c in cases if c.focus_account == "MULE0")
    assert mule.label == Verdict.SUSPICIOUS
    assert len(mule.transactions) >= 4               # 3 feeders + 1 cash-out
    # The fix's whole point: AEGIS now reaches a verdict on real structure.
    assert Orchestrator().investigate(mule).verdict == Verdict.SUSPICIOUS


def test_loader_lets_aegis_clear_a_big_benign_credit(tmp_path):
    csv = _write_paysim_csv(tmp_path)
    cases = load_public(path=csv, kind="paysim", limit=20)
    cust = next(c for c in cases if c.focus_account == "CUST0")
    assert cust.label == Verdict.BENIGN
    # One large credit with no structure must NOT be called suspicious.
    assert Orchestrator().investigate(cust).verdict != Verdict.SUSPICIOUS


def test_aegis_actually_engages_on_public_style_data(tmp_path):
    # Regression guard: the old one-row-per-case loader gave AEGIS ~0 recall
    # because no structural signal could form. Aggregated, it must catch > 0.
    csv = _write_paysim_csv(tmp_path)
    cases = load_public(path=csv, kind="paysim", limit=20)
    report = evaluate(cases, "public-test")
    assert report["aegis"]["recall_catch_rate"] > 0.0


def test_bundled_ibm_benchmark_engages_and_does_not_worsen_fp():
    """The committed IBM AML slice (powers the demo's 'public benchmark' button)
    must let AEGIS catch laundering structure and never have MORE false positives
    than the size-only baseline. Guards the whole public-benchmark path."""
    path = bundled_sample_path("ibm")
    assert path, "ibm_sample.csv should ship with the repo"
    report = evaluate(load_public(path=path, kind="generic", limit=200),
                      "public:ibm-aml-sample")
    assert report["aegis"]["recall_catch_rate"] >= 0.6
    assert report["aegis"]["false_positive_rate"] <= report["baseline"]["false_positive_rate"]
