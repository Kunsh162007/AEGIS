"""Org personalisation + pattern memory: the company's own rules change the
verdict inputs, and officer decisions become institutional memory that the
next structurally-identical case cites as evidence."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agents.org_policy import OrgPolicyAgent
from src.agents.pattern_memory import PatternMemoryAgent
from src.band import LocalMesh
from src.band.interface import Credential
from src.casework import Department
from src.casework.org import baselines_from_edges, normalize_profile
from src.casework.patterns import looks_novel, signature
from src.casework.store import CaseStore
from src.data.schema import Case, Party, Transaction, Verdict
from fixtures import case_structuring


def _room(case):
    return LocalMesh().open_room(case.case_id,
                                 Credential(officer_id="o", scopes={"*"}))


def _passthrough_case(account="ODD-1", alert_type="profile_anomaly") -> Case:
    """Funds fan in and immediately leave — laundering-shaped structure."""
    t0 = datetime(2026, 3, 1, tzinfo=UTC)
    txns = [Transaction(txn_id=f"t{i}", timestamp=t0 + timedelta(hours=i),
                        src_account=f"f{i}", dst_account=account, amount=5_000,
                        channel="transfer") for i in range(5)]
    txns.append(Transaction(txn_id="t-out", timestamp=t0 + timedelta(hours=6),
                            src_account=account, dst_account="OFF-1",
                            amount=24_000, channel="transfer"))
    parties = [Party(account=a, name=a) for a in
               {account, "OFF-1", *(f"f{i}" for i in range(5))}]
    return Case(case_id=f"CASE-{account}", alert_type=alert_type,
                focus_account=account, parties=parties, transactions=txns)


# ── org profile ──────────────────────────────────────────────────────────────

def test_normalize_profile_coerces_shapes():
    p = normalize_profile({"name": " Acme Bank ", "ctr_threshold": "5000",
                           "watchlist": "X1, X2 , X1", "policy_notes": ["r1"]})
    assert p["name"] == "Acme Bank"
    assert p["ctr_threshold"] == 5000.0
    assert p["watchlist"] == ["X1", "X2"]
    assert p["trusted_counterparties"] == []


def test_baselines_built_from_history():
    t0 = datetime(2026, 1, 1)
    edges = [{"src": "EMPLOYER", "dst": "alice", "amount": 5_000,
              "ts": t0 + timedelta(days=30 * i), "step": i, "channel": "transfer"}
             for i in range(3)]
    rows = baselines_from_edges(edges)
    alice = next(r for r in rows if r["account"] == "alice")
    assert alice["monthly_in"] > 0
    assert alice["top_counterparties"] == ["EMPLOYER"]


def test_org_policy_agent_applies_company_context():
    case = _passthrough_case()
    store = CaseStore(":memory:")
    store.save_baselines([{"account": "ODD-1", "monthly_in": 2_000.0,
                           "monthly_out": 1_000.0, "txn_count": 10,
                           "top_counterparties": ["EMPLOYER"], "channels": ["transfer"]}])
    org = normalize_profile({"watchlist": "OFF-1", "trusted_counterparties": "f0"})

    ev = OrgPolicyAgent(org=org, store=store).investigate(case, _room(case))

    srcs = [e.source for e in ev]
    assert any(s == "org:watchlist(OFF-1)" for s in srcs)          # watchlist hit
    assert any(s == "org:trusted(f0)" for s in srcs)               # vetted partner
    baseline_ev = next(e for e in ev if "baseline" in e.source)
    assert baseline_ev.supports == Verdict.SUSPICIOUS              # 25k vs 2k history


def test_org_evidence_survives_the_verifier():
    """The new org:/memory: sources must be accepted as cited evidence."""
    dept = Department(db_path=":memory:")
    dept.store.save_org_profile(normalize_profile({"watchlist": "OFF-1"}))
    case = _passthrough_case()
    result = dept.orchestrator().investigate(case)
    org_claims = [e for e in result.verified_evidence()
                  if e.source.startswith("org:")]
    assert org_claims, "org policy evidence was rejected by the verifier"


# ── pattern memory: the system improves with each analysis ──────────────────

def test_officer_confirmation_becomes_memory_for_the_next_case():
    dept = Department(db_path=":memory:")
    first = case_structuring()
    row = dept.record_case(first, dept.orchestrator().investigate(first), "a.csv")
    dept.decide(row["uid"], "confirm")

    second = case_structuring()  # structurally identical
    result = dept.orchestrator().investigate(second)
    memory = [e for e in result.verified_evidence()
              if e.source.startswith("memory:")]
    assert memory, "no institutional-memory evidence on the repeat case"
    assert any(e.supports == Verdict.SUSPICIOUS for e in memory)


def test_dismissal_becomes_innocent_precedent():
    dept = Department(db_path=":memory:")
    first = _passthrough_case(account="P-1")
    row = dept.record_case(first, dept.orchestrator().investigate(first), "a.csv")
    dept.decide(row["uid"], "dismiss")

    second = _passthrough_case(account="P-2")  # same signature, new subject
    ev = PatternMemoryAgent(store=dept.store).investigate(second, _room(second))
    assert any(e.supports == Verdict.BENIGN and "DISMISSED" in e.claim
               for e in ev)


def test_novel_pattern_is_flagged():
    case = _passthrough_case()           # suspicious structure...
    sig = signature(case)
    assert sig["typology"] == "profile_anomaly"   # ...matching no library typology
    assert looks_novel(sig)
    ev = PatternMemoryAgent(store=CaseStore(":memory:")).investigate(case, _room(case))
    assert any(e.source == "memory:novel" for e in ev)


def test_known_typology_is_not_novel():
    assert not looks_novel(signature(case_structuring()))
