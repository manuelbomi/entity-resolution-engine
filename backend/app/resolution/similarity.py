"""
Scoring how likely two source records describe the same real-world host.

Each field gets its own similarity function because "similar" means
different things for a hostname (typos matter) than for a timestamp (how
many hours apart) than for an IP address (exact match or nothing). We then
combine the per-field scores into one composite score using weights, because
some fields are much stronger evidence than others - a matching IP address
means a lot more than a matching environment tag like "prod" (lots of hosts
are tagged "prod").
"""

from __future__ import annotations

from rapidfuzz import fuzz

from .models import SourceRecord

# How much each field contributes to the final score. These were picked by
# reasoning about which fields are the strongest identity signal, not
# learned from data - a real system would tune these from labeled review
# decisions over time (see README).
FIELD_WEIGHTS = {
    "hostname": 0.40,
    "ip_address": 0.30,
    "owner": 0.10,
    "environment": 0.05,
    "last_seen": 0.15,
}


def hostname_similarity(a: str, b: str) -> float:
    a_norm = a.strip().lower().replace("_", "-")
    b_norm = b.strip().lower().replace("_", "-")
    if a_norm == b_norm:
        return 1.0
    # token_sort_ratio handles "db-prod-02" vs "prod-db-02" (reordered
    # tokens) and ordinary typos reasonably well. rapidfuzz returns 0-100.
    return fuzz.token_sort_ratio(a_norm, b_norm) / 100.0


def ip_similarity(a: str | None, b: str | None) -> float | None:
    # Missing data is not the same thing as conflicting data. If one source
    # just didn't capture an IP for this record, that tells us nothing about
    # whether it matches - so we return None and composite_score() leaves
    # this field out of the average entirely, instead of treating "unknown"
    # as "definitely different".
    if not a or not b:
        return None
    if a == b:
        return 1.0
    # Partial credit for being on the same /24 subnet - common when a host
    # got re-IP'd within the same rack/subnet, which happens a lot in
    # practice and shouldn't fully disqualify an otherwise strong match.
    a_parts, b_parts = a.split("."), b.split(".")
    if len(a_parts) == 4 and len(b_parts) == 4 and a_parts[:3] == b_parts[:3]:
        return 0.5
    return 0.0


def text_similarity(a: str | None, b: str | None) -> float | None:
    # Same reasoning as ip_similarity: a blank field on one side means we
    # have no opinion, not that the fields disagree.
    if not a or not b:
        return None
    if a.strip().lower() == b.strip().lower():
        return 1.0
    return fuzz.ratio(a.strip().lower(), b.strip().lower()) / 100.0


def recency_similarity(a, b) -> float:
    """
    Two records about the same host that were last updated hours apart are
    still probably the same host (different sources poll at different
    rates). Records updated weeks apart are weaker evidence, but we don't
    want this field to veto an otherwise strong match - it's a tiebreaker,
    not a disqualifier - which is why its weight above is modest.
    """
    delta_hours = abs((a - b).total_seconds()) / 3600.0
    if delta_hours <= 6:
        return 1.0
    if delta_hours >= 24 * 14:
        return 0.0
    # Linear falloff between 6 hours and 14 days.
    return max(0.0, 1.0 - (delta_hours - 6) / (24 * 14 - 6))


def score_pair(a: SourceRecord, b: SourceRecord) -> dict[str, float | None]:
    """
    Returns the per-field similarity scores for a pair of records (0.0-1.0
    each), or None for a field where at least one side has no value for it.
    """
    return {
        "hostname": hostname_similarity(a.hostname, b.hostname),
        "ip_address": ip_similarity(a.ip_address, b.ip_address),
        "owner": text_similarity(a.owner, b.owner),
        "environment": text_similarity(a.environment, b.environment),
        "last_seen": recency_similarity(a.last_seen, b.last_seen),
    }


def composite_score(field_scores: dict[str, float | None]) -> float:
    """
    Weighted average over only the fields that were actually comparable on
    both sides. A pair where neither source happened to record an owner
    isn't weaker evidence of a match than one where they did - it's just
    silent on that one field - so fields with a None score are left out of
    both the numerator and the denominator instead of counting as a 0.
    """
    available = {field: score for field, score in field_scores.items() if score is not None}
    if not available:
        return 0.0
    available_weight = sum(FIELD_WEIGHTS[field] for field in available)
    weighted_sum = sum(FIELD_WEIGHTS[field] * score for field, score in available.items())
    return round(weighted_sum / available_weight, 4)
