"""evaluate() — runs the baseline and full AEGIS over a labeled dataset and
computes the headline numbers: false-positive reduction and true-positive catch
rate (§9). Point it at a public benchmark for the credible number; the synthetic
set is a quick offline sanity check.

    python -m src.eval.harness                 # synthetic sanity check
    python -m src.eval.harness --public        # public benchmark (needs PUBLIC_DATASET_PATH)
"""
from __future__ import annotations

import argparse
import json

from ..data.schema import Case, Verdict
from ..data.synthetic import labeled_dataset
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
    orch = Orchestrator()
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


def _load(public: bool, limit: int) -> tuple[list[Case], str]:
    if public:
        from ..config import settings
        from ..data.public_loader import load_public
        return load_public(limit=limit), f"public:{settings.public_dataset_kind}"
    return labeled_dataset(n=limit), "synthetic"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public", action="store_true", help="use the public benchmark")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()
    cases, name = _load(args.public, args.limit)
    print(json.dumps(evaluate(cases, dataset_name=name), indent=2))


if __name__ == "__main__":
    main()
