"""
Builds a synthetic dataset that looks like three real IT systems describing
the same underlying fleet of hosts, each in its own messy way:

- "cmdb": a configuration-management database export. Clean-ish, but stale -
  owners and environments are often out of date because nobody updates them
  after a reorg.
- "cloud_inventory": a dump from a cloud provider's inventory API. Accurate
  on IP/OS, but hostnames are sometimes auto-generated or truncated, and it
  doesn't always know who owns something.
- "monitoring_agent": heartbeat pings from an agent on each box. Very fresh
  timestamps, but hostnames sometimes have typos (whoever typed the install
  script fat-fingered it) and it has no idea who owns the box.

This is entirely made up data, generated from a fixed random seed so the
results are reproducible - it is NOT a real inventory. The point is to
create a realistic-shaped mess: duplicate and near-duplicate records for the
same real host spread unevenly across the three sources, with some hosts
only showing up in one or two of them.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from .resolution.models import SourceRecord

SEED = 20240214
RANDOM = random.Random(SEED)

REGIONS = ["use1", "usw2", "euw1", "apse1"]
ROLES = ["web", "api", "db", "cache", "worker", "lb"]
OWNERS = ["platform-team", "data-team", "payments-team", "search-team", "unassigned"]
ENVIRONMENTS = ["prod", "staging", "dev"]
OPERATING_SYSTEMS = ["ubuntu-22.04", "ubuntu-20.04", "rhel-9", "amazon-linux-2023"]


def _typo(name: str) -> str:
    """Randomly mangles a hostname a little, simulating a fat-fingered entry."""
    if len(name) < 4 or RANDOM.random() > 0.15:
        return name
    i = RANDOM.randrange(1, len(name) - 1)
    chars = list(name)
    chars[i], chars[i - 1] = chars[i - 1], chars[i]
    return "".join(chars)


def _assigned_ip(index: int) -> str:
    """
    Gives each true host its own /24 subnet, assigned deterministically from
    its index instead of drawing a random address. If we picked addresses
    randomly from a small space, unrelated hosts would land on the same /24
    purely by chance, and the IP-subnet blocking key would lump them
    together - flooding the review queue with coincidental matches that have
    nothing to do with real data-quality problems. Giving every host its own
    subnet means the only records that ever share a block are the ones that
    are actually supposed to, plus the intentional bad readings injected
    below - which is what we want to test the resolver against.
    """
    second_octet = index // 256
    third_octet = index % 256
    return f"10.{second_octet}.{third_octet}.10"


def _wrong_ip(entity_count: int, exclude_index: int) -> str:
    """Occasionally a monitoring agent reports a stale/incorrect IP - picked from some other real host."""
    other = RANDOM.randrange(entity_count)
    if other == exclude_index:
        other = (other + 1) % entity_count
    return _assigned_ip(other)


def _canonical_hostname(index: int, serial: int) -> str:
    role = ROLES[index % len(ROLES)]
    region = REGIONS[(index // len(ROLES)) % len(REGIONS)]
    # The serial number is a shuffled, non-sequential id rather than the
    # loop index. If hosts in the same role/region were numbered
    # sequentially (...-0024, -0048, -0072), their names would look almost
    # identical to each other on top of already sharing a role and region -
    # which would make unrelated hosts score as fuzzy-similar just because
    # of the naming scheme, not because they're actually the same machine.
    return f"{role}-{region}-{serial:04d}"


def generate_source_records(entity_count: int = 450) -> list[SourceRecord]:
    """
    Generates `entity_count` real underlying hosts, then decides, per host,
    which of the three sources see it and how each source represents it.
    Returns the flat list of all source records across all three sources.
    """
    records: list[SourceRecord] = []
    now = datetime(2024, 6, 1, 12, 0, 0)

    # Unique, shuffled serial numbers (not 0, 1, 2, ...) so hosts that share
    # a role and region don't also end up with near-identical numbers.
    serials = list(range(1, entity_count * 4))
    RANDOM.shuffle(serials)

    for i in range(entity_count):
        hostname = _canonical_hostname(i, serials[i])
        true_ip = _assigned_ip(i)
        true_owner = OWNERS[i % len(OWNERS)]
        true_env = ENVIRONMENTS[i % len(ENVIRONMENTS)]
        true_os = OPERATING_SYSTEMS[i % len(OPERATING_SYSTEMS)]

        # Not every host shows up everywhere - about 70% are in all three
        # sources, the rest are missing from one, which is realistic (a host
        # just got decommissioned in one system's view, or hasn't been
        # discovered yet by another).
        present_in_cmdb = True
        present_in_cloud = RANDOM.random() < 0.85
        present_in_monitoring = RANDOM.random() < 0.80

        if present_in_cmdb:
            records.append(
                SourceRecord(
                    source_name="cmdb",
                    source_id=f"CMDB-{i:05d}",
                    hostname=hostname,
                    ip_address=true_ip if RANDOM.random() > 0.2 else None,
                    owner=true_owner if RANDOM.random() > 0.1 else OWNERS[(i + 1) % len(OWNERS)],
                    environment=true_env,
                    os=true_os if RANDOM.random() > 0.3 else None,
                    last_seen=now - timedelta(days=RANDOM.randint(1, 60)),
                )
            )

        if present_in_cloud:
            # Cloud inventory sometimes renders hostnames with underscores
            # instead of dashes, and rarely knows the human owner.
            cloud_hostname = hostname.replace("-", "_") if RANDOM.random() < 0.3 else hostname
            records.append(
                SourceRecord(
                    source_name="cloud_inventory",
                    source_id=f"i-{i:08x}",
                    hostname=cloud_hostname,
                    ip_address=true_ip,
                    owner=true_owner if RANDOM.random() > 0.6 else None,
                    environment=true_env if RANDOM.random() > 0.15 else None,
                    os=true_os,
                    last_seen=now - timedelta(hours=RANDOM.randint(1, 48)),
                )
            )

        if present_in_monitoring:
            records.append(
                SourceRecord(
                    source_name="monitoring_agent",
                    source_id=f"agent-{i}",
                    hostname=_typo(hostname),
                    ip_address=true_ip if RANDOM.random() > 0.1 else _wrong_ip(entity_count, i),
                    owner=None,
                    environment=None,
                    os=None,
                    last_seen=now - timedelta(minutes=RANDOM.randint(1, 180)),
                )
            )

    RANDOM.shuffle(records)
    return records
