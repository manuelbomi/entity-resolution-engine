from datetime import datetime, timedelta

from app.resolution.models import SourceRecord
from app.resolution.survivorship import resolve_fields


def _record(source, owner=None, environment=None, ip=None, os=None, days_ago=0):
    return SourceRecord(
        source_name=source,
        source_id=f"{source}-1",
        hostname="web-use1-0001",
        ip_address=ip,
        owner=owner,
        environment=environment,
        os=os,
        last_seen=datetime(2024, 1, 10) - timedelta(days=days_ago),
    )


def test_owner_prefers_cmdb_over_cloud_inventory():
    cmdb = _record("cmdb", owner="platform-team", days_ago=5)
    cloud = _record("cloud_inventory", owner="unassigned", days_ago=0)
    resolved = resolve_fields([cmdb, cloud])
    assert resolved["owner"].value == "platform-team"
    assert resolved["owner"].source_name == "cmdb"


def test_ip_prefers_most_recent_source():
    cmdb = _record("cmdb", ip="10.0.0.1", days_ago=10)
    monitoring = _record("monitoring_agent", ip="10.0.0.9", days_ago=0)
    resolved = resolve_fields([cmdb, monitoring])
    assert resolved["ip_address"].value == "10.0.0.9"
    assert resolved["ip_address"].source_name == "monitoring_agent"


def test_missing_field_across_all_sources_is_omitted():
    cmdb = _record("cmdb", owner=None)
    resolved = resolve_fields([cmdb])
    assert "owner" not in resolved


def test_single_source_contributes_all_available_fields():
    cmdb = _record("cmdb", owner="data-team", environment="staging", ip="10.0.0.1", os="rhel-9")
    resolved = resolve_fields([cmdb])
    assert resolved["owner"].value == "data-team"
    assert resolved["environment"].value == "staging"
    assert resolved["ip_address"].value == "10.0.0.1"
    assert resolved["os"].value == "rhel-9"
