from datetime import datetime, timedelta

from app.resolution.similarity import (
    composite_score,
    hostname_similarity,
    ip_similarity,
    recency_similarity,
    score_pair,
    text_similarity,
)
from app.resolution.models import SourceRecord


def test_hostname_similarity_exact_match():
    assert hostname_similarity("web-use1-0001", "web-use1-0001") == 1.0


def test_hostname_similarity_underscore_vs_dash_is_high():
    assert hostname_similarity("web-use1-0001", "web_use1_0001") > 0.9


def test_hostname_similarity_typo_is_moderate_to_high():
    score = hostname_similarity("web-use1-0001", "web-use1-0010")
    assert 0.6 < score < 1.0


def test_hostname_similarity_different_names_is_low():
    assert hostname_similarity("web-use1-0001", "db-euw1-0099") < 0.6


def test_ip_similarity_exact():
    assert ip_similarity("10.0.0.1", "10.0.0.1") == 1.0


def test_ip_similarity_same_subnet_partial_credit():
    assert ip_similarity("10.0.0.1", "10.0.0.250") == 0.5


def test_ip_similarity_different_subnet_zero():
    assert ip_similarity("10.0.0.1", "10.5.5.5") == 0.0


def test_ip_similarity_missing_value_is_excluded_not_penalized():
    assert ip_similarity(None, "10.0.0.1") is None


def test_text_similarity_missing_value_is_excluded_not_penalized():
    assert text_similarity(None, "platform-team") is None


def test_composite_score_ignores_fields_with_missing_data():
    # Owner and environment are None (missing on one side) - they should be
    # left out of the average entirely, not dragged down to 0.
    partial = {"hostname": 1.0, "ip_address": 1.0, "owner": None, "environment": None, "last_seen": 1.0}
    assert composite_score(partial) == 1.0


def test_recency_similarity_close_in_time_is_one():
    a = datetime(2024, 1, 1, 12, 0, 0)
    b = a + timedelta(hours=2)
    assert recency_similarity(a, b) == 1.0


def test_recency_similarity_far_apart_is_zero():
    a = datetime(2024, 1, 1, 12, 0, 0)
    b = a + timedelta(days=30)
    assert recency_similarity(a, b) == 0.0


def test_composite_score_weights_hostname_and_ip_more_than_owner():
    all_good = {"hostname": 1.0, "ip_address": 1.0, "owner": 1.0, "environment": 1.0, "last_seen": 1.0}
    only_owner = {"hostname": 0.0, "ip_address": 0.0, "owner": 1.0, "environment": 0.0, "last_seen": 0.0}
    assert composite_score(all_good) == 1.0
    assert composite_score(only_owner) < 0.2


def test_score_pair_returns_all_fields():
    now = datetime(2024, 1, 1, 12, 0, 0)
    a = SourceRecord("cmdb", "1", "web-use1-0001", "10.0.0.1", "team-a", "prod", "ubuntu-22.04", now)
    b = SourceRecord("monitoring_agent", "2", "web-use1-0001", "10.0.0.1", None, None, None, now)
    scores = score_pair(a, b)
    assert set(scores.keys()) == {"hostname", "ip_address", "owner", "environment", "last_seen"}
    assert scores["hostname"] == 1.0
    assert scores["ip_address"] == 1.0
