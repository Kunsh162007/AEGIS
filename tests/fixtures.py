"""Test-only labeled case fixtures. Lives in tests/ on purpose: the product
ships NO sample-data generation — it analyzes uploaded data (user_upload.py)
and the headline accuracy comes from the public benchmark (public_loader.py).
Ground-truth labels are attached for scoring; agents never read them.
NO REAL PII, EVER — names are obviously fake.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from src.data.schema import Case, Party, Transaction, Verdict

FAKE_NAMES = [
    "Ava Stone", "Ben Carter", "Cara Diaz", "Dan Ng", "Ella Roy", "Finn Park",
    "Gia Lee", "Hugo Sax", "Ivy Tran", "Jon Vale", "Kit Moss", "Lia Wren",
]
_CTR_THRESHOLD = 10_000  # the classic "structuring stays under $10k" reporting line


def _acct(i: int) -> str:
    return f"ACC{i:04d}"


def _mk_party(i: int, **kw) -> Party:
    kw.setdefault("name", FAKE_NAMES[i % len(FAKE_NAMES)])
    return Party(account=_acct(i), **kw)


def case_structuring(case_id: str = "TEST-STRUCTURING", rng: random.Random | None = None) -> Case:
    """SUSPICIOUS: many sub-$10k deposits in a tight window (smurfing)."""
    rng = rng or random.Random(1)
    t0 = datetime(2026, 5, 1, 9, 0)
    focus = _mk_party(0, expected_monthly_volume=8_000)
    parties = [focus] + [_mk_party(i) for i in range(1, 6)]
    txns = []
    for k in range(9):
        amt = rng.randint(8_700, 9_900)
        txns.append(Transaction(
            txn_id=f"T{k:04d}", timestamp=t0 + timedelta(hours=6 * k),
            src_account=parties[1 + k % 5].account, dst_account=focus.account,
            amount=float(amt), channel="cash", note="deposit"))
    return Case(case_id=case_id, alert_type="structuring", focus_account=focus.account,
                parties=parties, transactions=txns, label=Verdict.SUSPICIOUS)


def case_mule_network(case_id: str = "TEST-MULE", rng: random.Random | None = None) -> Case:
    """SUSPICIOUS: fan-in to one account then a fast burst out (mule ring)."""
    rng = rng or random.Random(2)
    t0 = datetime(2026, 5, 3, 8, 0)
    hub = _mk_party(7, expected_monthly_volume=5_000)
    feeders = [_mk_party(i) for i in range(8, 12)]
    sink = _mk_party(6, account_type="business", country="CY")
    parties = [hub, sink] + feeders
    txns = []
    for k, f in enumerate(feeders):
        txns.append(Transaction(txn_id=f"T1{k:03d}", timestamp=t0 + timedelta(minutes=20 * k),
                                src_account=f.account, dst_account=hub.account,
                                amount=float(rng.randint(4_000, 6_000)), note="transfer"))
    txns.append(Transaction(txn_id="T1900", timestamp=t0 + timedelta(hours=2),
                            src_account=hub.account, dst_account=sink.account,
                            amount=20_000.0, channel="wire", note="invoice payment"))
    return Case(case_id=case_id, alert_type="mule_network", focus_account=hub.account,
                parties=parties, transactions=txns, label=Verdict.SUSPICIOUS)


def case_salary_spike(case_id: str = "TEST-SALARY", rng: random.Random | None = None) -> Case:
    """BENIGN-but-flagged: a one-off large credit that is actually a bonus."""
    rng = rng or random.Random(3)
    t0 = datetime(2026, 5, 5, 10, 0)
    emp = _mk_party(3, account_type="personal", expected_monthly_volume=6_000)
    employer = _mk_party(2, account_type="business")
    amount = float(rng.choice([14_500, 16_000, 18_000, 21_000, 24_000]))
    note = rng.choice(["annual bonus payroll", "payroll salary credit",
                       "year-end bonus payroll"])
    txns = [Transaction(txn_id="T2000", timestamp=t0, src_account=employer.account,
                        dst_account=emp.account, amount=amount, channel="wire", note=note)]
    return Case(case_id=case_id, alert_type="profile_anomaly", focus_account=emp.account,
                parties=[emp, employer], transactions=txns, label=Verdict.BENIGN)


def case_property_sale(case_id: str = "TEST-PROPERTY", rng: random.Random | None = None) -> Case:
    """BENIGN-but-flagged: a single very large credit from a known conveyancer."""
    rng = rng or random.Random(4)
    t0 = datetime(2026, 5, 6, 11, 0)
    seller = _mk_party(4, expected_monthly_volume=7_000)
    conveyancer = _mk_party(5, account_type="business", name="Acme Conveyancing LLP")
    amount = float(rng.randint(180_000, 320_000))
    note = rng.choice(["property completion funds", "conveyancing completion",
                       "house sale completion"])
    txns = [Transaction(txn_id="T3000", timestamp=t0, src_account=conveyancer.account,
                        dst_account=seller.account, amount=amount, channel="wire", note=note)]
    return Case(case_id=case_id, alert_type="profile_anomaly", focus_account=seller.account,
                parties=[seller, conveyancer], transactions=txns, label=Verdict.BENIGN)


def case_subtle_mule(case_id: str = "TEST-SUBTLE", rng: random.Random | None = None) -> Case:
    """HARD SUSPICIOUS (honest miss): an early-stage mule — only two feeders and
    no onward burst yet, so it stays below every detector's floor. Both the
    baseline AND AEGIS miss it. Keeps the eval's recall honestly below 100%."""
    rng = rng or random.Random(5)
    t0 = datetime(2026, 5, 7, 9, 0)
    hub = _mk_party(9, expected_monthly_volume=5_000)
    feeders = [_mk_party(10), _mk_party(11)]
    txns = [Transaction(txn_id=f"T4{k:03d}", timestamp=t0 + timedelta(hours=2 * k),
                        src_account=f.account, dst_account=hub.account,
                        amount=float(rng.randint(3_800, 4_700)), note="transfer")
            for k, f in enumerate(feeders)]
    return Case(case_id=case_id, alert_type="profile_anomaly", focus_account=hub.account,
                parties=[hub] + feeders, transactions=txns, label=Verdict.SUSPICIOUS)


def case_legit_business(case_id: str = "TEST-BIZ", rng: random.Random | None = None) -> Case:
    """HARD BENIGN (honest false positive): a legitimate small business — many
    customer payments in, one supplier payment out. It is structurally identical
    to a mule (fan-in + pass-through), so AEGIS flags it too. A realistic FP that
    keeps the false-positive-reduction number believable (not a perfect 100%)."""
    rng = rng or random.Random(6)
    t0 = datetime(2026, 5, 8, 8, 0)
    biz = _mk_party(2, account_type="business", name="Bright Cafe Ltd",
                    expected_monthly_volume=8_000)
    customers = [_mk_party(i) for i in range(7, 11)]
    supplier = _mk_party(5, account_type="business", name="Wholesale Foods LLP")
    txns = [Transaction(txn_id=f"T5{k:03d}", timestamp=t0 + timedelta(hours=3 * k),
                        src_account=c.account, dst_account=biz.account,
                        amount=float(rng.randint(5_000, 7_000)), note="customer payment")
            for k, c in enumerate(customers)]
    txns.append(Transaction(txn_id="T5900", timestamp=t0 + timedelta(hours=14),
                            src_account=biz.account, dst_account=supplier.account,
                            amount=22_000.0, channel="wire", note="supplier invoice"))
    return Case(case_id=case_id, alert_type="mule_network", focus_account=biz.account,
                parties=[biz, supplier] + customers, transactions=txns, label=Verdict.BENIGN)


def labeled_dataset(n: int = 40, seed: int = 7) -> list[Case]:
    """A small reproducible labeled set for a quick offline eval sanity check.
    Deliberately includes hard cases (a missed early-stage mule, a legitimate
    business that looks like one) so the numbers are believable, not a suspicious
    100%. The *headline* accuracy number should still use a public benchmark
    (§9, public_loader)."""
    rng = random.Random(seed)
    builders = [case_structuring, case_mule_network, case_salary_spike,
                case_property_sale, case_subtle_mule, case_legit_business]
    return [builders[i % len(builders)](case_id=f"SYN-{i:03d}", rng=rng) for i in range(n)]
