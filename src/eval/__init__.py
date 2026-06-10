"""Baseline-vs-AEGIS accuracy harness (§9)."""
from .harness import evaluate
from .baseline import baseline_verdict

__all__ = ["evaluate", "baseline_verdict"]
