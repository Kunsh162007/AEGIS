"""End-to-end checks that run fully offline (MODEL_PROVIDER=mock)."""
from __future__ import annotations

from src.band import LocalMesh
from src.data.schema import Decision, Verdict
from src.data.synthetic import (case_mule_network, case_property_sale,
                                case_salary_spike, case_structuring, labeled_dataset)
from src.eval.harness import evaluate
from src.orchestrator import Orchestrator


def test_structuring_is_suspicious_and_escalates():
    res = Orchestrator().investigate(case_structuring())
    assert res.verdict == Verdict.SUSPICIOUS
    assert res.decision == Decision.ESCALATE
    assert res.report  # escalated cases get a drafted SAR
    assert all(e.source for e in res.verified_evidence())  # every claim is cited


def test_mule_network_detected_by_graph():
    res = Orchestrator().investigate(case_mule_network())
    assert res.verdict == Verdict.SUSPICIOUS
    assert any("hub" in e.source for e in res.verified_evidence())


def test_benign_salary_is_cleared_or_not_suspicious():
    res = Orchestrator().investigate(case_salary_spike())
    assert res.verdict != Verdict.SUSPICIOUS


def test_benign_property_is_cleared_or_not_suspicious():
    res = Orchestrator().investigate(case_property_sale())
    assert res.verdict != Verdict.SUSPICIOUS


def test_verifier_rejects_uncited_claim():
    # Forge an uncited claim and confirm the verifier rejects it.
    from src.agents.verifier import VerifierAgent
    from src.data.schema import Evidence
    case = case_structuring()
    mesh = LocalMesh()
    from src.band.interface import Credential
    room = mesh.open_room(case.case_id, Credential(officer_id="o", scopes={"*"}))
    bad = Evidence(agent="x", claim="I just feel it's suspicious", source="", weight=0.9)
    _, rejected = VerifierAgent().verify(case, [bad], {"rebuttals": []}, room)
    assert rejected and bad.verified is False


def test_verifier_rejects_hallucinated_references():
    # A citation pointing at records that don't exist in the case must be
    # rejected — including digit-free fabricated ids (review item #7).
    from src.agents.verifier import VerifierAgent
    from src.band.interface import Credential
    from src.data.schema import Evidence
    case = case_structuring()
    room = LocalMesh().open_room(case.case_id, Credential(officer_id="o", scopes={"*"}))
    fake_wordy = Evidence(agent="x", claim="cluster found", source="txn:[the-big-transfer]",
                          weight=0.9)
    fake_numeric = Evidence(agent="x", claim="hub found", source="graph:hub(ACCT-99999)",
                            weight=0.9)
    real_id = case.transactions[0].txn_id
    mixed = Evidence(agent="x", claim="burst found", source=f"txn:[{real_id},tx-fake-1]",
                     weight=0.9)
    genuine = Evidence(agent="x", claim="inbound spike", source=f"txn:[{real_id}]",
                       weight=0.9)
    _, rejected = VerifierAgent().verify(
        case, [fake_wordy, fake_numeric, mixed, genuine], {"rebuttals": []}, room)
    assert fake_wordy.verified is False
    assert fake_numeric.verified is False
    assert mixed.verified is False
    assert genuine.verified is True
    assert len(rejected) == 3


def test_consortium_strengthens_via_peer():
    peer = LocalMesh(tenant_id="bank-beta")
    peer.publish_pattern({"typology": "fan-in-then-burst", "txn_window_h": 72,
                          "legs": 5, "passthrough": True})
    res = Orchestrator().investigate(case_mule_network(), peers=["bank-beta"])
    assert res.consortium_confirmation is not None


def test_eval_shows_fp_reduction():
    report = evaluate(labeled_dataset(n=24), "synthetic")
    # AEGIS should not have MORE false positives than the naive baseline.
    assert report["aegis"]["false_positives"] <= report["baseline"]["false_positives"]
    assert report["aegis"]["recall_catch_rate"] >= 0.5
