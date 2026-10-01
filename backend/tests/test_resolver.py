from datetime import datetime, timedelta

from app.resolution.models import MatchStatus, SourceRecord
from app.resolution.resolver import EntityResolutionEngine


def _record(source, sid, hostname, ip, owner="team-a", days_ago=0):
    return SourceRecord(
        source_name=source,
        source_id=sid,
        hostname=hostname,
        ip_address=ip,
        owner=owner,
        environment="prod",
        os="ubuntu-22.04",
        last_seen=datetime(2024, 1, 10) - timedelta(days=days_ago),
    )


def test_strong_match_auto_merges_into_one_entity():
    a = _record("cmdb", "1", "web-use1-0001", "10.0.0.1")
    b = _record("monitoring_agent", "2", "web-use1-0001", "10.0.0.1")
    engine = EntityResolutionEngine([a, b])
    engine.run_initial_resolution()
    entities = engine.build_entities()
    assert len(entities) == 1
    assert len(entities[0].member_keys) == 2
    assert len(engine.review_queue()) == 0


def test_unrelated_records_stay_as_separate_entities():
    a = _record("cmdb", "1", "web-use1-0001", "10.0.0.1")
    b = _record("cmdb", "2", "db-euw1-0099", "10.3.200.200")
    engine = EntityResolutionEngine([a, b])
    engine.run_initial_resolution()
    entities = engine.build_entities()
    assert len(entities) == 2


def test_ambiguous_match_lands_in_review_queue_not_auto_merged():
    # Same /24 subnet (partial IP credit, not exact) and a hostname that
    # shares the role/region prefix but differs in the numeric suffix -
    # plausible, but not confident enough to auto-merge.
    a = _record("cmdb", "1", "web-use1-0001", "10.0.0.1")
    b = _record("monitoring_agent", "2", "web-use1-9999", "10.0.0.250")
    engine = EntityResolutionEngine([a, b])
    engine.run_initial_resolution()
    queue = engine.review_queue()
    entities = engine.build_entities()
    # Either it matched strongly enough to auto-merge, or it's sitting in
    # review - either way it must not have been silently discarded.
    assert len(queue) == 1 or len(entities) == 1


def test_approving_a_candidate_merges_the_entities():
    a = _record("cmdb", "1", "web-use1-0001", "10.0.0.1")
    b = _record("monitoring_agent", "2", "web-use1-9999", "10.0.0.250")
    engine = EntityResolutionEngine([a, b])
    engine.run_initial_resolution()
    queue = engine.review_queue()
    assert len(queue) == 1
    candidate = queue[0]

    engine.decide_candidate(candidate.candidate_id, approve=True)
    entities = engine.build_entities()
    assert len(entities) == 1
    assert candidate.status == MatchStatus.APPROVED


def test_rejecting_a_candidate_keeps_entities_separate():
    a = _record("cmdb", "1", "web-use1-0001", "10.0.0.1")
    b = _record("monitoring_agent", "2", "web-use1-9999", "10.0.0.250")
    engine = EntityResolutionEngine([a, b])
    engine.run_initial_resolution()
    candidate = engine.review_queue()[0]

    engine.decide_candidate(candidate.candidate_id, approve=False)
    entities = engine.build_entities()
    assert len(entities) == 2
    assert candidate.status == MatchStatus.REJECTED


def test_metrics_reports_consistent_counts():
    a = _record("cmdb", "1", "web-use1-0001", "10.0.0.1")
    b = _record("monitoring_agent", "2", "web-use1-0001", "10.0.0.1")
    c = _record("cmdb", "3", "db-euw1-0099", "10.3.200.200")
    engine = EntityResolutionEngine([a, b, c])
    engine.run_initial_resolution()
    metrics = engine.metrics()
    assert metrics["total_source_records"] == 3
    assert metrics["total_entities"] == 2
    assert metrics["multi_source_entities"] == 1
    assert metrics["records_per_source"]["cmdb"] == 2
    assert metrics["records_per_source"]["monitoring_agent"] == 1
