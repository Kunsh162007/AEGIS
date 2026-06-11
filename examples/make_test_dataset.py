"""Generate a realistic test dataset for the upload feature.

Hides three known laundering patterns among ordinary household/business
activity, so a correct AEGIS run should flag MULE-ALPHA, SMURF-CASH-1 and
CYCLE-A while clearing the benign accounts.

    python examples/make_test_dataset.py   ->  examples/test_dataset.csv / .xlsx
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)
HERE = Path(__file__).parent
t0 = datetime(2026, 5, 1, 8, 0)
rows: list[dict] = []


def add(src: str, dst: str, amount: float, ts: datetime, kind: str = "TRANSFER"):
    rows.append({"from": src, "to": dst, "amount": round(amount, 2),
                 "date": ts.strftime("%Y-%m-%d %H:%M"), "type": kind})


# ── Pattern 1: mule fan-in -> rapid offshore burst (MULE-ALPHA) ─────────────
for i in range(8):
    add(f"victim-{i+1:02d}", "MULE-ALPHA", random.uniform(7000, 9800),
        t0 + timedelta(hours=i * 3))
add("MULE-ALPHA", "OFFSHORE-EXCH", 64000, t0 + timedelta(hours=30))

# ── Pattern 2: cash structuring just under $10k (SMURF-CASH-1) ──────────────
for i in range(6):
    add("SHELL-TRADING-LLC", "SMURF-CASH-1", random.uniform(9000, 9900),
        t0 + timedelta(days=1, hours=i * 5), "CASH_IN")
add("SMURF-CASH-1", "CASINO-PAYOUT", 41000, t0 + timedelta(days=3))

# ── Pattern 3: round-trip layering cycle (CYCLE-A -> B -> C -> A) ───────────
for lap in range(3):
    base = t0 + timedelta(days=4 + lap)
    add("CYCLE-A", "CYCLE-B", 15000 - lap * 120, base)
    add("CYCLE-B", "CYCLE-C", 14800 - lap * 120, base + timedelta(hours=2))
    add("CYCLE-C", "CYCLE-A", 14650 - lap * 120, base + timedelta(hours=5))

# ── Benign: salaries, rent, groceries, a one-off property sale ──────────────
people = ["alice", "bob", "carol", "dave", "erin"]
for w, p in enumerate(people):
    for month in range(2):
        pay = t0 + timedelta(days=30 * month + w)
        add("ACME-PAYROLL", p, 4200 + w * 350, pay)
        add(p, "CITY-RENTALS", 1500 + w * 90, pay + timedelta(days=2))
        for d in range(6):
            add(p, random.choice(["GROCER-MART", "FUEL-STOP", "NETSTREAM"]),
                random.uniform(15, 220), pay + timedelta(days=3 + d * 4), "CARD")
add("HOMEBUYER-ESCROW", "carol", 310000, t0 + timedelta(days=20))  # property sale

random.shuffle(rows)
df = pd.DataFrame(rows)
df.to_csv(HERE / "test_dataset.csv", index=False)
df.to_excel(HERE / "test_dataset.xlsx", index=False)
print(f"wrote {len(df)} transactions ->",
      HERE / "test_dataset.csv", "and .xlsx")
print("expect SUSPICIOUS: MULE-ALPHA, SMURF-CASH-1, CYCLE accounts")
print("expect CLEARED   : alice/bob/carol/dave/erin")
