"""Abstract pattern signatures — how AEGIS remembers what it has seen.

A signature quantises a case's STRUCTURE (never its identities or amounts in
the raw) into a small dict. Two cases with the same signature are "the same
kind of activity", so an officer's decision on one becomes institutional
memory for the next. The same descriptors are what the consortium may share —
abstract by construction (§7).
"""
from __future__ import annotations

from ..data.schema import Case

_CTR = 10_000.0


def _bucket(n: int, low: int, high: int) -> str:
    return "low" if n < low else ("med" if n < high else "high")


def signature(case: Case) -> dict:
    ins = [t for t in case.transactions if t.dst_account == case.focus_account]
    outs = [t for t in case.transactions if t.src_account == case.focus_account]

    feeders = {t.src_account for t in ins if t.channel != "card"} - {case.focus_account}
    near_ctr = sum(1 for t in ins
                   if t.channel == "cash" and 0.85 * _CTR <= t.amount < _CTR)
    tin = sum(t.amount for t in ins)
    tout = sum(t.amount for t in outs)
    passthrough = bool(ins and outs and tin > 0 and tout / tin >= 0.8)

    burst = False
    if len(ins) >= 4:
        span_h = (max(t.timestamp for t in ins)
                  - min(t.timestamp for t in ins)).total_seconds() / 3600
        burst = span_h <= 24

    return {
        "typology": case.alert_type,
        "fan_in": _bucket(len(feeders), 3, 6),
        "near_ctr": _bucket(near_ctr, 1, 3),
        "passthrough": passthrough,
        "burst": burst,
    }


# Typologies the knowledge library already describes. A SUSPICIOUS structure
# whose signature falls outside this set is a candidate NOVEL pattern.
KNOWN_TYPOLOGIES = {"structuring", "mule_network", "layering", "round_tripping"}


def is_structurally_suspicious(sig: dict) -> bool:
    """Does the signature carry laundering-shaped structure at all?"""
    return (sig["passthrough"] or sig["burst"]
            or sig["fan_in"] != "low" or sig["near_ctr"] != "low")


def looks_novel(sig: dict) -> bool:
    """Suspicious structure that matches no library typology — worth flagging
    as a potentially NEW pattern."""
    return sig["typology"] not in KNOWN_TYPOLOGIES and is_structurally_suspicious(sig)
