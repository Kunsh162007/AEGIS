"""evaluate() — runs the baseline and full AEGIS over a labeled dataset and
computes the headline numbers: false-positive reduction and true-positive catch
rate (§9), on the PUBLIC benchmark (externally-authored labels — the credible
number). CLI-only by design: the product UI shows nothing but the user's data.

    python -m src.eval.harness                 # bundled IBM AML slice, or
                                               # PUBLIC_DATASET_PATH if set
"""
from __future__ import annotations

import argparse
import json

from ..data.schema import Case, Verdict
from ..orchestrator import Orchestrator
from .baseline import baseline_verdict


def _metrics(labels: list[Verdict], preds: list[Verdict]) -> dict:
    tp = sum(1 for y, p in zip(labels, preds)
             if y == Verdict.SUSPICIOUS and p == Verdict.SUSPICIOUS)
    fp = sum(1 for y, p in zip(labels, preds)
             if y == Verdict.BENIGN and p == Verdict.SUSPICIOUS)
    fn = sum(1 for y, p in zip(labels, preds)
             if y == Verdict.SUSPICIOUS and p != Verdict.SUSPICIOUS)
    tn = sum(1 for y, p in zip(labels, preds)
             if y == Verdict.BENIGN and p != Verdict.SUSPICIOUS)
    pos = tp + fn
    neg = fp + tn
    return {
        "recall_catch_rate": round(tp / pos, 3) if pos else 0.0,
        "false_positive_rate": round(fp / neg, 3) if neg else 0.0,
        "false_positives": fp, "true_positives": tp, "n": len(labels),
    }


def evaluate(cases: list[Case], dataset_name: str = "synthetic") -> dict:
    labels = [c.label for c in cases]

    baseline_preds = [baseline_verdict(c) for c in cases]
    # The benchmark pins the deterministic provider regardless of
    # MODEL_PROVIDER: the score measures the verification ARCHITECTURE (stats /
    # graph / retrieval / challenge / audit), which is computation, and pinning
    # keeps the number reproducible — and a 200-case run fast and free — even
    # when the deployed app investigates with live models.
    from ..models.client import ModelClient
    orch = Orchestrator(model=ModelClient(provider="mock"))
    aegis_preds = [orch.investigate(c).verdict for c in cases]

    base_m = _metrics(labels, baseline_preds)
    aegis_m = _metrics(labels, aegis_preds)

    fp_reduction = 0.0
    if base_m["false_positives"]:
        fp_reduction = round(
            (base_m["false_positives"] - aegis_m["false_positives"])
            / base_m["false_positives"] * 100, 1)

    return {
        "dataset": dataset_name,
        "baseline": base_m,
        "aegis": aegis_m,
        "false_positive_reduction_pct": fp_reduction,
        "catch_rate_delta": round(aegis_m["recall_catch_rate"]
                                  - base_m["recall_catch_rate"], 3),
    }


def _load(limit: int) -> tuple[list[Case], str]:
    from ..config import settings
    from ..data.public_loader import load_public
    kind = settings.public_dataset_kind if settings.public_dataset_path else "ibm-aml-sample"
    return load_public(limit=limit), f"public:{kind}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    cases, name = _load(args.limit)
    print(json.dumps(evaluate(cases, dataset_name=name), indent=2))


if __name__ == "__main__":
    main()
