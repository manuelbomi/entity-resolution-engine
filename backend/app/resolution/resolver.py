"""
The orchestrator: blocking -> scoring -> thresholds -> golden records.

High level flow:
1. Generate candidate pairs via blocking (so we don't score every pair).
2. Score every candidate pair on every field, get one composite score.
3. Split pairs into three bands:
   - >= AUTO_MERGE_THRESHOLD: confident enough to merge automatically.
   - >= REVIEW_THRESHOLD: plausible, but a human should confirm.
   - below that: not a match, ignored.
4. Auto-merge pairs get unioned together using a union-find structure, so
   that if A matches B and B matches C, all three end up in one cluster even
   if A and C were never directly compared.
5. Each cluster of unioned records becomes one ResolvedEntity, with its
   fields picked via the survivorship rules in survivorship.py and full
   provenance of which source contributed each field.
6. Records that didn't auto-merge with anything become their own
   single-source entity.
7. Human review decisions (approve/reject) from the review queue feed back
   into the union-find structure and entities get rebuilt.

This whole thing runs in memory on top of a small `UnionFind` + registry
object (EntityResolutionEngine below). There's no persistence - restarting
the process starts over from the synthetic source data. See store.py and
the README for how this would change with a real database behind it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, UTC

from .blocking import generate_candidate_pairs
from .models import AuditEvent, CandidateMatch, FieldProvenance, MatchStatus, ResolvedEntity, SourceRecord
from .similarity import composite_score, score_pair
from .survivorship import resolve_fields

AUTO_MERGE_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.65


class UnionFind:
    """Standard disjoint-set structure so transitively-linked records end up in one cluster."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, key: str) -> None:
        self._parent.setdefault(key, key)

    def find(self, key: str) -> str:
        self.add(key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        # path compression
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_a] = root_b

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for key in self._parent:
            out[self.find(key)].append(key)
        return out


class EntityResolutionEngine:
    """Owns all in-memory state: source records, the union-find clusters, candidates, and audit log."""

    def __init__(self, records: list[SourceRecord]) -> None:
        self.records_by_key: dict[str, SourceRecord] = {r.record_key: r for r in records}
        self.union_find = UnionFind()
        self.candidates: dict[str, CandidateMatch] = {}
        self.global_audit_log: list[AuditEvent] = []
        self._pair_scores: dict[tuple[str, str], dict[str, float]] = {}
        for key in self.records_by_key:
            self.union_find.add(key)

    def run_initial_resolution(self) -> None:
        """Scores every blocked candidate pair once and applies the threshold bands."""
        pairs = generate_candidate_pairs(list(self.records_by_key.values()))
        for key_a, key_b in pairs:
            record_a, record_b = self.records_by_key[key_a], self.records_by_key[key_b]
            field_scores = score_pair(record_a, record_b)
            score = composite_score(field_scores)
            self._pair_scores[(key_a, key_b)] = field_scores

            if score >= AUTO_MERGE_THRESHOLD:
                self.union_find.union(key_a, key_b)
                self.global_audit_log.append(
                    AuditEvent(
                        timestamp=datetime.now(UTC),
                        action="auto_merge",
                        detail=f"{key_a} <-> {key_b} (score={score})",
                    )
                )
            elif score >= REVIEW_THRESHOLD:
                candidate = CandidateMatch(
                    record_a_key=key_a,
                    record_b_key=key_b,
                    field_scores=field_scores,
                    composite_score=score,
                    status=MatchStatus.PENDING_REVIEW,
                )
                self.candidates[candidate.candidate_id] = candidate
            # else: below REVIEW_THRESHOLD, not worth surfacing at all.

    def decide_candidate(self, candidate_id: str, approve: bool) -> CandidateMatch:
        candidate = self.candidates[candidate_id]
        candidate.status = MatchStatus.APPROVED if approve else MatchStatus.REJECTED
        candidate.decided_at = datetime.now(UTC)
        if approve:
            self.union_find.union(candidate.record_a_key, candidate.record_b_key)
        self.global_audit_log.append(
            AuditEvent(
                timestamp=datetime.now(UTC),
                action="review_decision",
                detail=f"{candidate.record_a_key} <-> {candidate.record_b_key} -> {candidate.status.value}",
            )
        )
        return candidate

    def build_entities(self) -> list[ResolvedEntity]:
        """
        Rebuilds golden records from the current union-find state. Cheap
        enough to recompute on every read given our in-memory dataset sizes;
        a production version would cache this and invalidate incrementally.
        """
        entities: list[ResolvedEntity] = []
        for member_keys in self.union_find.groups().values():
            member_records = [self.records_by_key[k] for k in member_keys]
            entity = ResolvedEntity(member_keys=set(member_keys))
            entity.fields = resolve_fields(member_records)
            entity.add_audit(
                "resolved",
                f"built from {len(member_records)} source record(s): {', '.join(sorted(member_keys))}",
            )
            entities.append(entity)
        return entities

    def review_queue(self) -> list[CandidateMatch]:
        return [c for c in self.candidates.values() if c.status == MatchStatus.PENDING_REVIEW]

    def metrics(self) -> dict:
        entities = self.build_entities()
        multi_source = [e for e in entities if len(e.member_keys) > 1]
        # Candidates are, by definition, everything that scored between
        # REVIEW_THRESHOLD and AUTO_MERGE_THRESHOLD (0.65-0.90 by default) -
        # auto-merged pairs never become candidates, so these buckets only
        # need to cover that band.
        confidence_buckets = {"0.65-0.72": 0, "0.72-0.79": 0, "0.79-0.85": 0, "0.85-0.90": 0}
        for candidate in self.candidates.values():
            score = candidate.composite_score
            if score < 0.72:
                confidence_buckets["0.65-0.72"] += 1
            elif score < 0.79:
                confidence_buckets["0.72-0.79"] += 1
            elif score < 0.85:
                confidence_buckets["0.79-0.85"] += 1
            else:
                confidence_buckets["0.85-0.90"] += 1

        per_source_counts: dict[str, int] = defaultdict(int)
        for record in self.records_by_key.values():
            per_source_counts[record.source_name] += 1

        return {
            "total_source_records": len(self.records_by_key),
            "total_entities": len(entities),
            "multi_source_entities": len(multi_source),
            "match_rate": round(len(multi_source) / len(entities), 4) if entities else 0.0,
            "pending_review_count": len(self.review_queue()),
            "confidence_distribution": confidence_buckets,
            "records_per_source": dict(per_source_counts),
        }
