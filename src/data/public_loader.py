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

import random
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from ..config import settings
from .schema import Case, Party, Transaction, Verdict

# A small, balanced, externally-labelled slice of a public benchmark ships with
# the repo so the deployed app can show a real (not synthetic) number without a
# 500MB download. See src/data/benchmarks/README.md for provenance.
_BENCHMARKS_DIR = Path(__file__).resolve().parent / "benchmarks"


def bundled_sample_path(kind: str = "paysim") -> str | None:
    """Path to the committed benchmark sample for `kind`, or None if absent."""
    p = _BENCHMARKS_DIR / f"{kind}_sample.csv"
    return str(p) if p.exists() else None

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
    elif kind == "generic":
        # Pre-normalised money-flow CSV: src,dst,amount,isFraud[,step,channel].
        # This is the format the bundled benchmark sample ships in, so the app
        # never parses a dataset-specific schema at request time.
        for i, r in df.iterrows():
            edges.append({
                "src": str(r["src"]), "dst": str(r["dst"]),
                "amount": float(r["amount"]),
                "step": int(r["step"]) if "step" in df.columns else i,
                "fraud": bool(int(r["isFraud"])),
                "channel": str(r["channel"]) if "channel" in df.columns else "transfer",
            })
    else:
        raise ValueError(f"unknown dataset kind '{kind}'")
    return edges


def _derive_alert_type(account: str, ins: list[dict], outs: list[dict]) -> str:
    """Pick the alert type from transaction STRUCTURE (never the label) — this is
    what a real upstream alerting rule would route on."""
    # Card inflows are retail receipts (a merchant taking payments), never mule
    # gather legs — only transfer/cash/wire inflows count toward fan-in.
    gather = [e for e in ins if e["channel"] != "card"]
    feeders = {e["src"] for e in gather if e["src"] != account}
    near_cash = [e for e in ins
                 if e["channel"] == "cash" and 0.85 * _CTR_THRESHOLD <= e["amount"] < _CTR_THRESHOLD]
    # A fan-in concentration is a mule/gather signal whether or not the onward
    # leg is in view — route it to the network-graph agent either way.
    if len(feeders) >= 3:
        return "mule_network"
    if len(near_cash) >= 3:
        return "structuring"
    # In-and-out is only a pass-through signal when most of what came in went
    # straight out again — a household spending part of its salary is not.
    in_amt = sum(e["amount"] for e in gather)
    out_amt = sum(e["amount"] for e in outs)
    if gather and outs and in_amt > 0 and out_amt >= 0.6 * in_amt:
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
        # No full dataset configured — fall back to the externally-labelled
        # IBM AML slice bundled with the repo so the benchmark always works.
        path, kind = bundled_sample_path("ibm"), "generic"
    if not path:
        raise FileNotFoundError(
            "No PUBLIC_DATASET_PATH set and no bundled benchmark sample found. "
            "Download IBM-AML/PaySim/Elliptic from Kaggle and point .env at the CSV.")

    # Read enough rows that focus accounts have several transactions each, but
    # bound it with `nrows` so a multi-hundred-MB full dataset never loads
    # entirely into memory (the bundled sample is small, so this reads all of it).
    df = pd.read_csv(path, nrows=max(limit * 50, 20_000))
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

    # Balanced evaluation set:
    #  * positives = laundering accounts ranked by activity (transaction count) —
    #    the structurally-active accounts a first-line rule would alert and route
    #    to AEGIS to investigate;
    #  * negatives = a REPRESENTATIVE RANDOM sample of benign accounts (seeded for
    #    reproducibility), not cherry-picked.
    # The question the number answers: among alerted laundering accounts and
    # ordinary benign accounts, can AEGIS confirm the laundering while NOT
    # over-flagging the benign ones the way a size-only baseline does?
    def _degree(a: str) -> int:
        return len(inbound.get(a, [])) + len(outbound.get(a, []))

    positives = sorted((a for a in accounts if a in fraud_accounts), key=_degree, reverse=True)
    benign = sorted(a for a in accounts if a not in fraud_accounts)
    random.Random(7).shuffle(benign)

    half = max(limit // 2, 1)
    selected = positives[:half] + benign[:half]
    return [_build_case(kind, a, inbound.get(a, []), outbound.get(a, []), fraud_accounts)
            for a in selected]
