"""Load a PUBLIC AML benchmark into the AEGIS case schema (§9).

The headline accuracy number must come from data whose labels you did NOT
author. Supported (download a CSV from Kaggle, set PUBLIC_DATASET_PATH):

  - paysim   : PaySim mobile-money fraud  (cols: step,type,amount,nameOrig,
               nameDest,isFraud,...)
  - ibm_aml  : IBM Transactions for AML   (has an "Is Laundering" column)
  - elliptic : Elliptic Bitcoin (txId, class in {1=illicit,2=licit,unknown})

Why aggregation matters
-----------------------
AEGIS's specialists detect *structure* — structuring clusters, mule fan-in,
pass-through, velocity, graph hubs/cycles. Those signals only exist across
MULTIPLE transactions. So we do NOT score one row at a time; we group every
transaction that touches a focus **account** into one multi-transaction Case.
A mule's `transfer-in → cash-out` becomes a pass-through signal; a benign
one-off large credit produces no structural signal and is left for the
baseline to over-flag. That contrast is exactly the false-positive-reduction
the eval measures.

The ground-truth label is used ONLY to *select* a balanced set of focus
accounts to evaluate; agents never read it (the alert type is derived from
transaction structure, not from the label).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from ..config import settings
from .schema import Case, Party, Transaction, Verdict

_MAX_TXNS_PER_CASE = 25
_CTR_THRESHOLD = 10_000

# PaySim transaction type -> our channel vocabulary (drives the cash-structuring
# and pass-through heuristics).
_PAYSIM_CHANNEL = {"CASH_IN": "cash", "CASH_OUT": "cash", "TRANSFER": "transfer",
                   "PAYMENT": "card", "DEBIT": "card"}


def _edges_from_df(df, kind: str) -> list[dict]:
    """Normalise a dataset into uniform money-flow edges:
    {src, dst, amount, step, fraud, channel}."""
    edges: list[dict] = []
    if kind == "paysim":
        for i, r in df.iterrows():
            edges.append({
                "src": str(r["nameOrig"]), "dst": str(r["nameDest"]),
                "amount": float(r["amount"]), "step": int(r.get("step", i)),
                "fraud": bool(int(r["isFraud"])),
                "channel": _PAYSIM_CHANNEL.get(str(r.get("type", "")).upper(), "transfer"),
            })
    elif kind == "ibm_aml":
        cols = {c.lower().replace(" ", "_"): c for c in df.columns}
        label_col = next((cols[c] for c in cols
                          if c in {"is_laundering", "islaundering", "label"}), None)
        amt_col = next((cols[c] for c in cols if "amount" in c), None)
        if label_col is None or amt_col is None:
            raise ValueError("ibm_aml CSV missing an amount or laundering-label column")
        # Account columns vary by export; prefer named, else fall back to position.
        from_col = cols.get("from_account") or cols.get("account") or df.columns[0]
        to_col = cols.get("to_account") or cols.get("account.1") or df.columns[2]
        for i, r in df.iterrows():
            edges.append({
                "src": str(r[from_col]), "dst": str(r[to_col]),
                "amount": float(r[amt_col]), "step": i,
                "fraud": bool(int(r[label_col])), "channel": "transfer",
            })
    elif kind == "elliptic":
        # Elliptic is node classification, not a from/dst ledger. Without the
        # edge list we can't build money-flow structure, so each labelled node
        # becomes a minimal one-transaction case (documented limitation — prefer
        # PaySim/IBM for the structural story).
        cls_col = "class" if "class" in df.columns else df.columns[1]
        id_col = "txId" if "txId" in df.columns else df.columns[0]
        for i, r in df.iterrows():
            c = str(r[cls_col])
            if c not in {"1", "2"}:  # skip "unknown"
                continue
            edges.append({
                "src": f"src{i}", "dst": str(r[id_col]), "amount": 1.0,
                "step": i, "fraud": c == "1", "channel": "transfer",
            })
    else:
        raise ValueError(f"unknown dataset kind '{kind}'")
    return edges


def _derive_alert_type(account: str, ins: list[dict], outs: list[dict]) -> str:
    """Pick the alert type from transaction STRUCTURE (never the label) — this is
    what a real upstream alerting rule would route on."""
    feeders = {e["src"] for e in ins if e["src"] != account}
    near_cash = [e for e in ins
                 if e["channel"] == "cash" and 0.85 * _CTR_THRESHOLD <= e["amount"] < _CTR_THRESHOLD]
    if len(feeders) >= 3 and outs:
        return "mule_network"
    if len(near_cash) >= 3:
        return "structuring"
    if ins and outs:               # in-and-out → possible pass-through
        return "mule_network"
    return "profile_anomaly"


def _build_case(kind: str, account: str, ins: list[dict], outs: list[dict],
                fraud_accounts: set[str]) -> Case:
    rel = sorted(ins + outs, key=lambda e: e["step"])[:_MAX_TXNS_PER_CASE]
    t0 = datetime(2026, 1, 1)
    txns = [Transaction(
        txn_id=f"{kind}-{account}-{j}",
        timestamp=t0 + timedelta(hours=float(e["step"]) % 168),
        src_account=e["src"], dst_account=e["dst"], amount=e["amount"],
        channel=e["channel"], note=e["channel"]) for j, e in enumerate(rel)]

    accounts = {account} | {e["src"] for e in rel} | {e["dst"] for e in rel}
    in_amt = sum(e["amount"] for e in ins)
    # Give the focus account a plausible expected volume (~its own inbound) so
    # profile-deviation isn't spuriously huge; counterparties get none.
    parties = [Party(account=a, name=f"acct-{a}",
                     expected_monthly_volume=round(max(in_amt, 1.0)) if a == account else 0.0)
               for a in sorted(accounts)]

    return Case(
        case_id=f"{kind.upper()}-{account}",
        alert_type=_derive_alert_type(account, ins, outs),
        focus_account=account, parties=parties, transactions=txns,
        label=Verdict.SUSPICIOUS if account in fraud_accounts else Verdict.BENIGN)


def load_public(path: str | None = None, kind: str | None = None,
                limit: int = 300) -> list[Case]:
    import pandas as pd

    path = path or settings.public_dataset_path
    kind = (kind or settings.public_dataset_kind or "paysim").lower()
    if not path:
        raise FileNotFoundError(
            "No PUBLIC_DATASET_PATH set. Download PaySim/IBM-AML/Elliptic from "
            "Kaggle and point .env at the CSV, or use synthetic.labeled_dataset().")

    # Read enough rows that focus accounts have several transactions each.
    df = pd.read_csv(path).head(max(limit * 50, 5_000))
    edges = _edges_from_df(df, kind)

    inbound: dict[str, list[dict]] = defaultdict(list)
    outbound: dict[str, list[dict]] = defaultdict(list)
    fraud_accounts: set[str] = set()
    for e in edges:
        inbound[e["dst"]].append(e)
        outbound[e["src"]].append(e)
        if e["fraud"]:
            fraud_accounts.add(e["dst"])
            fraud_accounts.add(e["src"])

    accounts = set(inbound) | set(outbound)
    positives = [a for a in accounts if a in fraud_accounts]
    # Negatives sorted by inbound volume so the baseline is genuinely challenged
    # (big benign accounts are exactly what a size-only scorer false-positives on).
    negatives = sorted((a for a in accounts if a not in fraud_accounts),
                       key=lambda a: sum(e["amount"] for e in inbound.get(a, [])),
                       reverse=True)

    half = max(limit // 2, 1)
    selected = positives[:half] + negatives[:half]
    return [_build_case(kind, a, inbound.get(a, []), outbound.get(a, []), fraud_accounts)
            for a in selected]
