"""
Survivorship rules: once we've decided two or more records are the same
host, which record's value do we actually keep for each field?

Different sources disagree all the time - the CMDB says the owner is
"platform-team" and the cloud inventory says "unassigned" because nobody
updated it after a reorg. There is no single rule that's right for every
field, so each field gets its own rule:

- `environment` and `owner`: trust ranking. The CMDB is the system humans
  actually maintain by hand for these fields, so it wins ties.
- `ip_address` and `os`: most recent write wins, because these reflect the
  *current* state of the machine and change over time; whichever source
  checked in most recently is more likely to be right.
- `hostname`: most recent write wins too, with a tie-break towards the
  longest/most complete-looking value (guards against a source that
  truncates names).

This file is deliberately small and declarative so that changing a
survivorship rule for one field doesn't risk touching the others.
"""

from __future__ import annotations

from .models import FieldProvenance, SourceRecord

# Lower index = more trusted, used for the "trusted source wins" rule.
SOURCE_TRUST_RANK = ["cmdb", "cloud_inventory", "monitoring_agent"]


def _trust_rank(source_name: str) -> int:
    try:
        return SOURCE_TRUST_RANK.index(source_name)
    except ValueError:
        return len(SOURCE_TRUST_RANK)


def _most_trusted_wins(records: list[SourceRecord], field: str) -> FieldProvenance | None:
    candidates = [r for r in records if getattr(r, field)]
    if not candidates:
        return None
    best = min(candidates, key=lambda r: _trust_rank(r.source_name))
    return FieldProvenance(value=getattr(best, field), source_name=best.source_name, source_id=best.source_id)


def _most_recent_wins(records: list[SourceRecord], field: str) -> FieldProvenance | None:
    candidates = [r for r in records if getattr(r, field)]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: r.last_seen)
    return FieldProvenance(value=getattr(best, field), source_name=best.source_name, source_id=best.source_id)


# Maps field name -> which rule function resolves conflicts for it.
SURVIVORSHIP_RULES = {
    "hostname": _most_recent_wins,
    "ip_address": _most_recent_wins,
    "owner": _most_trusted_wins,
    "environment": _most_trusted_wins,
    "os": _most_recent_wins,
}

RESOLVED_FIELDS = ["hostname", "ip_address", "owner", "environment", "os"]


def resolve_fields(records: list[SourceRecord]) -> dict[str, FieldProvenance]:
    """Applies each field's survivorship rule across all member records of a cluster."""
    resolved: dict[str, FieldProvenance] = {}
    for field in RESOLVED_FIELDS:
        rule = SURVIVORSHIP_RULES[field]
        provenance = rule(records, field)
        if provenance is not None:
            resolved[field] = provenance
    return resolved
