"""USE_FRAMEWORKS=true must run the SAME logic through the frameworks and reach
the SAME verdicts as the agnostic path — the adapters move control flow, not
decisions. The LangGraph checks skip if langgraph isn't installed."""
from __future__ import annotations

import pytest

from src.agents.frameworks import langgraph_verification
from src.band import LocalMesh
from src.data.schema import Verdict
from fixtures import (case_mule_network, case_property_sale,
                                case_salary_spike, case_structuring)
from src.orchestrator import Orchestrator

pytestmark = pytest.mark.skipif(
    not langgraph_verification.frameworks_available(),
    reason="langgraph not installed — framework path falls back to agnostic")


@pytest.mark.parametrize("builder", [case_structuring, case_mule_network,
                                     case_salary_spike, case_property_sale])
def test_langgraph_path_matches_agnostic(builder):
    agnostic = Orchestrator(use_frameworks=False).investigate(builder())
    framework = Orchestrator(use_frameworks=True).investigate(builder())
    assert framework.verdict == agnostic.verdict
    assert framework.decision == agnostic.decision


def test_consortium_still_works_under_frameworks():
    peer = LocalMesh(tenant_id="bank-beta")
    peer.publish_pattern({"typology": "fan-in-then-burst", "txn_window_h": 72,
                          "legs": 5, "passthrough": True})
    res = Orchestrator(use_frameworks=True).investigate(
        case_mule_network(), peers=["bank-beta"])
    assert res.verdict == Verdict.SUSPICIOUS
    assert res.consortium_confirmation is not None
