"""Build the committed AML benchmark slice (`ibm_sample.csv`) from the IBM
"Transactions for Anti-Money Laundering" dataset (HI-Small variant).

IBM AML (https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml)
is synthetic — no real PII — and, unlike PaySim, its labelled laundering forms
real STRUCTURE (fan-in hubs, layering cycles) that AEGIS's graph detectors are
built to find. The full file is ~475MB and ~0.06% laundering, so this script
streams a window, picks a balanced set of focus accounts (laundering + benign),
and keeps every transaction touching them (capped per account) so each focus
account's local structure survives. Output is a normalised money-flow CSV
(src,dst,amount,channel,isFraud) read by public_loader's `generic` kind. Labels
are IBM's own — we only choose which accounts to include.

Reproduce:
    python -m src.data.benchmarks.build_ibm_sample <path-to-HI-Small_Trans.csv>
"""
from __future__ import annotations

import collections
import random
import sys
from pathlib import Path

import pandas as pd

_OUT = Path(__file__).resolve().parent / "ibm_sample.csv"
_ROWS = 1_500_000
_N_POS = 150       # laundering focus accounts
_N_NEG = 230       # benign focus accounts (representative, not cherry-picked)
_CAP = 25          # max transactions kept per focus account


def build(src_csv: str, seed: int = 7) -> None:
    df = pd.read_csv(src_csv, nrows=_ROWS)
    df = pd.DataFrame({
        "src": df["From Bank"].astype(str) + "-" + df["Account"].astype(str),
        "dst": df["To Bank"].astype(str) + "-" + df["Account.1"].astype(str),
        "amount": df["Amount Paid"].astype(float),
        "isFraud": df["Is Laundering"].astype(int),
    })
    df["step"] = range(len(df))
    df["channel"] = "transfer"

    laundering = set(df[df.isFraud == 1]["src"]) | set(df[df.isFraud == 1]["dst"])
    all_accts = set(df["src"]) | set(df["dst"])
    rng = random.Random(seed)

    # Degree = how many transactions touch an account. Positives are the
    # high-degree laundering accounts (the structural centres an alerting rule
    # would actually flag and route to AEGIS); negatives are a REPRESENTATIVE
    # random sample of benign accounts (mostly ordinary, low activity).
    deg = collections.Counter()
    for s, d in zip(df["src"], df["dst"]):
        deg[s] += 1
        deg[d] += 1
    pos = sorted(laundering, key=lambda a: deg[a], reverse=True)[:_N_POS]
    benign = sorted(all_accts - laundering); rng.shuffle(benign); neg = benign[:_N_NEG]
    focus = set(pos) | set(neg)

    rel = df[df["src"].isin(focus) | df["dst"].isin(focus)]
    kept, seen = [], collections.Counter()
    for idx, row in rel.iterrows():
        a = row["dst"] if row["dst"] in focus else row["src"]
        if seen[a] < _CAP:
            kept.append(idx)
            seen[a] += 1

    out = (df.loc[kept, ["step", "src", "dst", "amount", "channel", "isFraud"]]
           .sample(frac=1, random_state=seed).reset_index(drop=True))
    out.to_csv(_OUT, index=False)
    print(f"wrote {len(out)} rows | focus: {len(pos)} laundering + {len(neg)} benign "
          f"| laundering rows: {int(out.isFraud.sum())} -> {_OUT}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m src.data.benchmarks.build_ibm_sample <HI-Small_Trans.csv>")
    build(sys.argv[1])
