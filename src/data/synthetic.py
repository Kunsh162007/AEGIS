"""Synthetic, labeled case generator — for the *narrated demo storylines* only
(§9). Ground-truth labels are attached for the eval harness; agents never read
them. NO REAL PII, EVER — names are obviously fake.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .schema import Case, Party, Transaction, Verdict

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


def case_structuring(case_id: str = "DEMO-STRUCTURING", rng: random.Random | None = None) -> Case:
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


def case_mule_network(case_id: str = "DEMO-MULE", rng: random.Random | None = None) -> Case:
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


def case_salary_spike(case_id: str = "DEMO-SALARY") -> Case:
    """BENIGN-but-flagged: a one-off large credit that is actually a bonus."""
    t0 = datetime(2026, 5, 5, 10, 0)
    emp = _mk_party(3, account_type="personal", expected_monthly_volume=6_000)
    employer = _mk_party(2, account_type="business")
    txns = [Transaction(txn_id="T2000", timestamp=t0, src_account=employer.account,
                        dst_account=emp.account, amount=18_000.0, channel="wire",
                        note="annual bonus payroll")]
    return Case(case_id=case_id, alert_type="profile_anomaly", focus_account=emp.account,
                parties=[emp, employer], transactions=txns, label=Verdict.BENIGN)


def case_property_sale(case_id: str = "DEMO-PROPERTY") -> Case:
    """BENIGN-but-flagged: a single very large credit from a known conveyancer."""
    t0 = datetime(2026, 5, 6, 11, 0)
    seller = _mk_party(4, expected_monthly_volume=7_000)
    conveyancer = _mk_party(5, account_type="business", name="Acme Conveyancing LLP")
    txns = [Transaction(txn_id="T3000", timestamp=t0, src_account=conveyancer.account,
                        dst_account=seller.account, amount=240_000.0, channel="wire",
                        note="property completion funds")]
    return Case(case_id=case_id, alert_type="profile_anomaly", focus_account=seller.account,
                parties=[seller, conveyancer], transactions=txns, label=Verdict.BENIGN)


DEMO_FIXTURES = {
    "structuring": case_structuring,
    "mule": case_mule_network,
    "salary": case_salary_spike,
    "property": case_property_sale,
}


def labeled_dataset(n: int = 40, seed: int = 7) -> list[Case]:
    """A small reproducible labeled set for a quick offline eval sanity check.
    The *headline* accuracy number should use a public benchmark (§9, public_loader)."""
    rng = random.Random(seed)
    cases: list[Case] = []
    builders = [case_structuring, case_mule_network, case_salary_spike, case_property_sale]
    for i in range(n):
        b = builders[i % len(builders)]
        cases.append(b(case_id=f"SYN-{i:03d}", rng=rng) if "rng" in b.__code__.co_varnames
                     else b(case_id=f"SYN-{i:03d}"))
    return cases


def get_fixture(name: str) -> Case:
    if name not in DEMO_FIXTURES:
        raise KeyError(f"unknown fixture '{name}'. Options: {list(DEMO_FIXTURES)}")
    return DEMO_FIXTURES[name]()
