from datetime import datetime

from app.resolution.blocking import generate_candidate_pairs
from app.resolution.models import SourceRecord


def _record(source, sid, hostname, ip):
    return SourceRecord(
        source_name=source,
        source_id=sid,
        hostname=hostname,
        ip_address=ip,
        owner="team-a",
        environment="prod",
        os="ubuntu-22.04",
        last_seen=datetime(2024, 1, 1, 12, 0, 0),
    )


def test_pairs_with_matching_hostname_prefix_are_candidates():
    a = _record("cmdb", "1", "web-use1-0001", "10.0.0.1")
    b = _record("monitoring_agent", "2", "web-use1-0001", "10.0.0.1")
    pairs = generate_candidate_pairs([a, b])
    assert (a.record_key, b.record_key) in pairs or (b.record_key, a.record_key) in pairs


def test_completely_unrelated_records_are_not_candidates():
    a = _record("cmdb", "1", "web-use1-0001", "10.0.0.1")
    b = _record("cmdb", "2", "db-euw1-0099", "10.3.200.200")
    pairs = generate_candidate_pairs([a, b])
    assert len(pairs) == 0


def test_same_subnet_different_hostname_still_candidate_via_ip_block():
    a = _record("cmdb", "1", "web-use1-0001", "10.0.0.1")
    b = _record("cloud_inventory", "2", "totally-different-name", "10.0.0.250")
    pairs = generate_candidate_pairs([a, b])
    assert len(pairs) == 1


def test_no_self_pairs():
    a = _record("cmdb", "1", "web-use1-0001", "10.0.0.1")
    pairs = generate_candidate_pairs([a])
    assert len(pairs) == 0
