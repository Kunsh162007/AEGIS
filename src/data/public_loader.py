"""Load a PUBLIC AML benchmark into the AEGIS case schema (§9).

The headline accuracy number must come from data whose labels you did NOT
author. Supported (download a CSV from Kaggle, set PUBLIC_DATASET_PATH):

  - paysim   : PaySim mobile-money fraud  (cols: step,type,amount,nameOrig,
               nameDest,isFraud,...)
  - ibm_aml  : IBM Transactions for AML   (has an "Is Laundering" column)
  - elliptic : Elliptic Bitcoin (txId, class in {1=illicit,2=licit,unknown})

Each transaction-row becomes a tiny one-transaction Case so the same pipeline
scores it. For richer graph signal, group rows by account before loading
(left as a documented extension).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..config import settings
from .schema import Case, Party, Transaction, Verdict


def _row_case(idx: int, src: str, dst: str, amount: float, fraud: bool,
              kind: str) -> Case:
    t0 = datetime(2026, 1, 1) + timedelta(minutes=idx)
    parties = [Party(account=src, name=f"acct-{src}"),
               Party(account=dst, name=f"acct-{dst}")]
    txn = Transaction(txn_id=f"{kind}-{idx}", timestamp=t0, src_account=src,
                      dst_account=dst, amount=float(amount), note=kind)
    return Case(case_id=f"{kind.upper()}-{idx}", alert_type="layering",
                focus_account=dst, parties=parties, transactions=[txn],
                label=Verdict.SUSPICIOUS if fraud else Verdict.BENIGN)


def load_public(path: str | None = None, kind: str | None = None,
                limit: int = 300) -> list[Case]:
    import pandas as pd

    path = path or settings.public_dataset_path
    kind = (kind or settings.public_dataset_kind or "paysim").lower()
    if not path:
        raise FileNotFoundError(
            "No PUBLIC_DATASET_PATH set. Download PaySim/IBM-AML/Elliptic from "
            "Kaggle and point .env at the CSV, or use synthetic.labeled_dataset().")

    df = pd.read_csv(path).head(limit * 4)  # oversample then balance below
    cases: list[Case] = []

    if kind == "paysim":
        for i, r in df.iterrows():
            cases.append(_row_case(i, str(r["nameOrig"]), str(r["nameDest"]),
                                   r["amount"], bool(r["isFraud"]), "paysim"))
    elif kind == "ibm_aml":
        label_col = next(c for c in df.columns if c.lower().replace(" ", "_") in
                         {"is_laundering", "islaundering", "label"})
        amt_col = next(c for c in df.columns if "amount" in c.lower())
        for i, r in df.iterrows():
            cases.append(_row_case(i, str(r.iloc[0]), str(r.iloc[2]), r[amt_col],
                                   bool(int(r[label_col])), "ibm"))
    elif kind == "elliptic":
        cls = df["class"].astype(str) if "class" in df.columns else df.iloc[:, 1].astype(str)
        for i, r in df.iterrows():
            c = str(r.get("class", r.iloc[1]))
            if c == "unknown":
                continue
            cases.append(_row_case(i, f"src{i}", str(r.iloc[0]), 1.0, c == "1", "elliptic"))
    else:
        raise ValueError(f"unknown dataset kind '{kind}'")

    # Balance the slice so the FP/TP numbers are meaningful, then cap at `limit`.
    pos = [c for c in cases if c.label == Verdict.SUSPICIOUS][: limit // 2]
    neg = [c for c in cases if c.label == Verdict.BENIGN][: limit // 2]
    return pos + neg
