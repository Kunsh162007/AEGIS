"""The AEGIS investigation pipeline (§6). Framework-agnostic by default; if
USE_FRAMEWORKS=true it routes the SAME agent logic through CrewAI (specialists)
and a real LangGraph StateGraph (verification trio) — see agents/frameworks/.
Both framework paths degrade to the agnostic path if their library is absent, so
the system is always runnable.

    alert -> intake opens room + recruits
          -> specialists post cited evidence
          -> challenger argues innocent
          -> verifier audits (rejects uncited / rebutted claims)
          -> consortium liaison queries peers (optional)
          -> adjudicator: verdict + confidence + autonomy decision
          -> (escalated) report agent drafts the SAR
"""
from __future__ import annotations

from typing import Callable

from .agents.adjudicator import AdjudicatorAgent
from .agents.challenger import ChallengerAgent
from .agents.consortium_liaison import ConsortiumLiaisonAgent
from .agents.external_intel import ExternalIntelAgent
from .agents.frameworks import crew_specialists, langgraph_verification
from .agents.identity_kyc import IdentityKycAgent
from .agents.intake import IntakeAgent
from .agents.network_graph import NetworkGraphAgent
from .agents.quality_auditor import QualityAuditorAgent
from .agents.report_tooling import ReportAgent
from .agents.transaction_pattern import TransactionPatternAgent
from .agents.verifier import VerifierAgent
from .band import LocalMesh, get_mesh
from .band.interface import AuditEvent, Credential
from .config import settings
from .data.schema import Case, CaseResult, Decision
from .knowledge import KnowledgeBase
from .models.client import ModelClient
from .policy.autonomy import AutonomyPolicy

SPECIALISTS = {
    "transaction_pattern": TransactionPatternAgent,
    "identity_kyc": IdentityKycAgent,
    "network_graph": NetworkGraphAgent,
    "external_intel": ExternalIntelAgent,
}

DEFAULT_SCOPES = {"txn:read", "kyc:read", "kb:read"}


class Orchestrator:
    def __init__(self, mesh: LocalMesh | None = None, policy: AutonomyPolicy | None = None,
                 kb: KnowledgeBase | None = None, officer_scopes: set[str] | None = None,
                 use_frameworks: bool | None = None):
        self.model = ModelClient()
        self.mesh = mesh or get_mesh()
        self.kb = kb or KnowledgeBase()
        self.policy = policy or AutonomyPolicy()
        self.scopes = officer_scopes if officer_scopes is not None else set(DEFAULT_SCOPES)
        self.use_frameworks = settings.use_frameworks if use_frameworks is None else use_frameworks

        self.intake = IntakeAgent(self.model)
        self.challenger = ChallengerAgent(self.model)
        self.verifier = VerifierAgent(self.model)
        self.adjudicator = AdjudicatorAgent(self.model, policy=self.policy)
        self.report = ReportAgent(self.model)
        self.liaison = ConsortiumLiaisonAgent(self.model)
        self.qa = QualityAuditorAgent(self.model)

    def _make_specialists(self, roles: list[str]):
        agents = []
        for role in roles:
            cls = SPECIALISTS.get(role)
            if not cls:
                continue
            agents.append(cls(self.model, kb=self.kb) if role == "external_intel"
                          else cls(self.model))
        return agents

    def investigate(self, case: Case, peers: list[str] | None = None,
                    on_event: Callable[[AuditEvent], None] | None = None) -> CaseResult:
        if on_event:
            self.mesh.subscribe(on_event)

        credential = Credential(officer_id="officer:aegis", scopes=set(self.scopes))
        room = self.mesh.open_room(case.case_id, credential)

        # 1) Intake recruits specialists for this alert type.
        roles = self.intake.recruit_for(case, room)
        specialists = self._make_specialists(roles)

        # 2) Specialists post cited evidence (credential traversal enforced).
        #    Optionally as a CrewAI crew; degrades to direct execution.
        if self.use_frameworks:
            evidence = crew_specialists.run_specialist_crew(specialists, case, room)
        else:
            evidence = []
            for agent in specialists:
                evidence.extend(agent.investigate(case, room))

        # 3-6) Challenger -> Verifier -> Consortium -> Adjudicator.
        #      As a real LangGraph StateGraph when enabled+available, else inline.
        if self.use_frameworks and langgraph_verification.frameworks_available():
            result = langgraph_verification.run_verification_graph(
                challenger=self.challenger, verifier=self.verifier, liaison=self.liaison,
                adjudicator=self.adjudicator, case=case, evidence=evidence, room=room,
                mesh=self.mesh, peers=peers or [])
        else:
            challenge = self.challenger.challenge(case, evidence, room)
            evidence, rejected = self.verifier.verify(case, evidence, challenge, room)
            consortium_note = (self.liaison.query_peers(case, self.mesh, peers, room)
                               if peers else None)
            result = self.adjudicator.adjudicate(case, evidence, challenge, rejected, room,
                                                 consortium_note=consortium_note)

        # 7) QA audit — the supervisory control. Audits the process (citations,
        #    challenge, verdict-evidence consistency) and blocks any auto-clear
        #    that fails a critical check.
        result = self.qa.audit(case, result, room)

        # 8) Escalated cases get a drafted, evidence-cited SAR; human gate requested.
        if result.decision == Decision.ESCALATE:
            room.request_human_gate({"case_id": case.case_id,
                                     "verdict": result.verdict.value,
                                     "confidence": result.confidence})
            self.report.draft_report(case, result)
        else:
            room.post("adjudicator", "clear",
                      {"case_id": case.case_id, "rationale": result.rationale})

        return result
