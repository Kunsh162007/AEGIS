"""The shared case schema — the single structured context that flows through
the Band room and every agent. Synthetic data and public-dataset rows both
normalise into these types.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    SUSPICIOUS = "suspicious"
    BENIGN = "benign"
    UNCERTAIN = "uncertain"


class Decision(str, Enum):
    AUTO_CLEAR = "auto_clear"
    ESCALATE = "escalate"


class Transaction(BaseModel):
    txn_id: str
    timestamp: datetime
    src_account: str
    dst_account: str
    amount: float
    currency: str = "USD"
    channel: str = "wire"  # wire | card | cash | transfer
    note: str = ""


class Party(BaseModel):
    account: str
    name: str               # SYNTHETIC ONLY — never real PII
    account_type: str = "personal"   # personal | business
    country: str = "US"
    opened: Optional[datetime] = None
    expected_monthly_volume: float = 0.0
    is_pep: bool = False
    on_sanctions_list: bool = False


class Evidence(BaseModel):
    """A single claim made by an agent, carrying its source. The Verifier
    rejects any claim whose `source` is empty (§Evidence is mandatory)."""
    agent: str
    claim: str
    source: str = ""                 # e.g. "txn:T0007", "graph:ring(A,B,C)", "kb:typology/structuring"
    weight: float = 0.5              # 0..1 how strongly this points to suspicion
    supports: Verdict = Verdict.SUSPICIOUS
    verified: Optional[bool] = None  # set by the Verifier
    confidence: Optional[float] = None


class Case(BaseModel):
    case_id: str
    alert_type: str                  # structuring | mule_network | layering | profile_anomaly | adverse_media
    opened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tenant_id: str = "bank-alpha"
    parties: list[Party] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)
    focus_account: str = ""          # the account the alert fired on
    # Ground truth for the eval harness only — agents must NEVER read this.
    label: Optional[Verdict] = None

    def party(self, account: str) -> Optional[Party]:
        return next((p for p in self.parties if p.account == account), None)


class CaseResult(BaseModel):
    case_id: str
    verdict: Verdict = Verdict.UNCERTAIN
    confidence: float = 0.0
    decision: Decision = Decision.ESCALATE
    rationale: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    challenger_argument: str = ""
    rejected_claims: list[str] = Field(default_factory=list)
    consortium_confirmation: Optional[str] = None
    report: str = ""

    def verified_evidence(self) -> list[Evidence]:
        return [e for e in self.evidence if e.verified]
