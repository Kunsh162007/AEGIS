"""Org personalisation — a company registers its OWN compliance context and
history, and every subsequent investigation reads it:

  * profile: custom reporting threshold, watchlist, trusted counterparties,
    free-text policy notes (surfaced to the chat analyst and reports),
  * behavioural baselines: built from the org's PREVIOUS transaction data, so
    "unusual" means unusual *for this account's own history*, not in the
    abstract.

Both persist in the casebook store; nothing here is required — without a
profile AEGIS behaves exactly as before.
"""
from __future__ import annotations

from collections import Counter, defaultdict

DEFAULT_PROFILE = {
    "name": "",
    "ctr_threshold": 10_000.0,        # the org's own reporting threshold
    "watchlist": [],                  # accounts the org already distrusts
    "trusted_counterparties": [],     # vetted accounts (payroll, suppliers…)
    "policy_notes": [],               # free-text internal rules
}


def normalize_profile(raw: dict) -> dict:
    """Coerce a user-supplied profile into the canonical shape; unknown keys
    are dropped, list entries are de-duplicated strings."""
    out = dict(DEFAULT_PROFILE)
    out["name"] = str(raw.get("name", "")).strip()
    try:
        out["ctr_threshold"] = max(0.0, float(raw.get("ctr_threshold", 10_000.0)))
    except (TypeError, ValueError):
        out["ctr_threshold"] = 10_000.0
    for key in ("watchlist", "trusted_counterparties", "policy_notes"):
        vals = raw.get(key, [])
        if isinstance(vals, str):
            vals = [v.strip() for v in vals.split(",")]
        out[key] = sorted({str(v).strip() for v in vals if str(v).strip()})
    return out


def baselines_from_edges(edges: list[dict]) -> list[dict]:
    """Historical money-flow edges -> one behavioural baseline per account:
    typical monthly in/out volume, usual counterparties, usual channels."""
    inbound: dict[str, list[dict]] = defaultdict(list)
    outbound: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        inbound[e["dst"]].append(e)
        outbound[e["src"]].append(e)

    timestamps = [e["ts"] for e in edges if e.get("ts")]
    months = 1.0
    if len(timestamps) >= 2:
        span_days = (max(timestamps) - min(timestamps)).total_seconds() / 86_400
        months = max(1.0, span_days / 30.0)

    rows = []
    for account in set(inbound) | set(outbound):
        ins, outs = inbound.get(account, []), outbound.get(account, [])
        partners = Counter(
            [e["src"] for e in ins] + [e["dst"] for e in outs])
        partners.pop(account, None)
        rows.append({
            "account": account,
            "monthly_in": round(sum(e["amount"] for e in ins) / months, 2),
            "monthly_out": round(sum(e["amount"] for e in outs) / months, 2),
            "txn_count": len(ins) + len(outs),
            "top_counterparties": [p for p, _ in partners.most_common(5)],
            "channels": sorted({e["channel"] for e in ins + outs}),
        })
    return rows
