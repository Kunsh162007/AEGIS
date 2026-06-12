"""The LLM-driven Challenger (AI/ML API reasoning tier) must: propose an innocent
explanation when a real model is configured, clear a soft profile anomaly with
it, NEVER clear structural laundering evidence, and stay completely inert in mock
mode (so the offline path is unchanged)."""
from __future__ import annotations

from datetime import datetime

from src.agents.challenger import ChallengerAgent
from src.agents.verifier import VerifierAgent
from src.band import LocalMesh
from src.band.interface import Credential
from src.data.schema import Case, Evidence, Party, Transaction, Verdict
from src.models.client import ModelClient


class FakeReasoner:
    """Stand-in for a real AI/ML API model — no network/key needed."""
    provider = "aimlapi"

    def __init__(self, explanation: str):
        self.explanation = explanation

    def complete(self, prompt, *, tier="specialist", agent="?", system="", max_tokens=512):
        if "LEGITIMATE explanation" in prompt:
            return self.explanation
        return "innocent-case narrative"


def _room():
    return LocalMesh().open_room("C1", Credential(officer_id="o", scopes={"*"}))


def _case():
    return Case(case_id="C1", alert_type="profile_anomaly", focus_account="ACC1",
                parties=[Party(account="ACC1", name="x", expected_monthly_volume=5000)],
                transactions=[Transaction(txn_id="T1", timestamp=datetime(2026, 1, 1),
                                          src_account="ACC2", dst_account="ACC1",
                                          amount=40000.0, note="wire credit")])


def test_real_model_proposes_innocent_explanation():
    ch = ChallengerAgent(FakeReasoner("The credit is the customer's documented property-sale completion."))
    res = ch.challenge(_case(), [], _room())
    llm = [r for r in res["rebuttals"] if r["source"] == "llm:reasoning"]
    assert llm and llm[0]["targets"] == ["kyc:profile"]


def test_model_replies_none_means_no_rebuttal():
    ch = ChallengerAgent(FakeReasoner("NONE"))
    res = ch.challenge(_case(), [], _room())
    assert not any(r["source"] == "llm:reasoning" for r in res["rebuttals"])


def test_mock_mode_adds_no_llm_rebuttal():
    ch = ChallengerAgent(ModelClient(provider="mock"))
    res = ch.challenge(_case(), [], _room())
    assert not any(r["source"] == "llm:reasoning" for r in res["rebuttals"])


def test_mock_fallback_text_is_not_treated_as_an_explanation():
    # auto-mode-without-keys degrades to mock narration ("[challenger] ...");
    # it must NOT be accepted as a real innocent explanation.
    ch = ChallengerAgent(FakeReasoner("[challenger] Transaction notes: wire credit"))
    res = ch.challenge(_case(), [], _room())
    assert not any(r["source"] == "llm:reasoning" for r in res["rebuttals"])


def test_llm_clears_profile_flag_but_not_structural_evidence():
    ch = ChallengerAgent(FakeReasoner("Salary income from the customer's employer."))

    case = _case()
    profile = [Evidence(agent="identity_kyc", claim="off profile",
                        source="kyc:profile(ACC1)", weight=0.55, supports=Verdict.SUSPICIOUS)]
    VerifierAgent().verify(case, profile, ch.challenge(case, profile, _room()), _room())
    assert profile[0].verified is False  # innocent explanation clears the soft flag

    case2 = _case()
    hub = [Evidence(agent="network_graph", claim="mule hub",
                    source="graph:hub(ACC1)", weight=0.8, supports=Verdict.SUSPICIOUS)]
    VerifierAgent().verify(case2, hub, ch.challenge(case2, hub, _room()), _room())
    assert hub[0].verified is True  # structural laundering evidence survives
