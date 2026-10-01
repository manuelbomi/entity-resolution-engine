"""
Data shapes used everywhere in the resolution engine.

We use plain dataclasses instead of a database ORM on purpose. There is no
database in this project (see store.py) and dataclasses are cheap to reason
about and cheap to test. If this were wired up to Postgres later, these
would become the ORM models (or stay as DTOs around them).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any
from uuid import uuid4


class MatchStatus(str, Enum):
    AUTO_MERGED = "auto_merged"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NO_MATCH = "no_match"


@dataclass
class SourceRecord:
    """
    One row as it came out of one source system, untouched.

    `source_name` is which system it came from (e.g. "cmdb"). `source_id` is
    whatever that system calls it internally. The two together are the only
    thing guaranteed to be unique - the fields below (hostname, ip, etc.) are
    exactly the messy, inconsistent values we're trying to reconcile, so they
    are NOT assumed to be clean or unique.
    """

    source_name: str
    source_id: str
    hostname: str
    ip_address: str | None
    owner: str | None
    environment: str | None
    os: str | None
    last_seen: datetime

    @property
    def record_key(self) -> str:
        return f"{self.source_name}:{self.source_id}"


@dataclass
class FieldProvenance:
    """Tracks which source contributed the value we ultimately kept for a field."""

    value: Any
    source_name: str
    source_id: str


@dataclass
class AuditEvent:
    timestamp: datetime
    action: str
    detail: str


@dataclass
class ResolvedEntity:
    """
    The "golden record" - one row per real-world host, built out of however
    many source records we decided belong to it.
    """

    entity_id: str = field(default_factory=lambda: str(uuid4()))
    member_keys: set[str] = field(default_factory=set)
    fields: dict[str, FieldProvenance] = field(default_factory=dict)
    audit_log: list[AuditEvent] = field(default_factory=list)

    def add_audit(self, action: str, detail: str) -> None:
        self.audit_log.append(AuditEvent(timestamp=datetime.now(UTC), action=action, detail=detail))


@dataclass
class CandidateMatch:
    """
    A pair of records that scored in the "probably the same thing, but not
    confident enough to auto-merge" band. A human has to look at this.
    """

    record_a_key: str
    record_b_key: str
    field_scores: dict[str, float]
    composite_score: float
    candidate_id: str = field(default_factory=lambda: str(uuid4()))
    status: MatchStatus = MatchStatus.PENDING_REVIEW
    decided_at: datetime | None = None
