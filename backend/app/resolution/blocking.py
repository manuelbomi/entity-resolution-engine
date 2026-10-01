"""
Blocking: cutting down the number of pairs we have to compare.

If we have N records and we compared every record to every other record,
that's N*(N-1)/2 comparisons. With 1,000 records that's ~500,000 pairs. With
100,000 records it's ~5 billion. That does not scale, and almost all of
those comparisons would be between two records that obviously have nothing
to do with each other (a server in one source and a totally different server
in another source).

Blocking fixes this by first grouping records into small buckets using a
cheap, rough key, and then only comparing records that landed in the same
bucket. We use two different keys and take the union of both groupings,
because a single key is never good enough on its own - if a key is based on
the hostname and the hostname has a typo, two records that should match
might land in different buckets. Using a second key (based on the IP
address) gives those records a second chance to end up in the same block.

This is a classic technique in record linkage. The cost of using a bad or
too-strict blocking key is that you silently miss true matches (lower
recall). The cost of too loose a key is you don't save much comparison time.
We picked keys that are cheap to compute and tolerant of small typos.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from .models import SourceRecord


def _normalize_hostname(hostname: str) -> str:
    return hostname.strip().lower().replace("_", "-")


def _hostname_prefix_key(record: SourceRecord) -> str | None:
    """
    The normalized hostname with its last character dropped. Dropping just
    one character (instead of the whole numeric suffix) is enough to still
    catch a single-digit typo or a transposed pair of digits, while keeping
    the key specific enough that two genuinely different hosts which simply
    share a role and region (e.g. "web-use1-0231" and "web-use1-0847") don't
    get lumped into the same block. A looser key here would mean comparing
    every "web" server in a region against every other one, which doesn't
    scale and mostly produces noise.
    """
    name = _normalize_hostname(record.hostname)
    if len(name) < 4:
        return None
    return f"host:{name[:-1]}"


def _ip_subnet_key(record: SourceRecord) -> str | None:
    """First three octets of the IP. Hosts on the same subnet are good candidates."""
    if not record.ip_address:
        return None
    parts = record.ip_address.split(".")
    if len(parts) != 4:
        return None
    return f"ip:{'.'.join(parts[:3])}"


# All the blocking key functions we use. Adding a new one just means adding
# another cheap-to-compute function here - nothing else needs to change.
BLOCKING_KEY_FUNCS = [_hostname_prefix_key, _ip_subnet_key]


def build_blocks(records: list[SourceRecord]) -> dict[str, list[SourceRecord]]:
    """Groups records by every blocking key they produce. A record can land in multiple blocks."""
    blocks: dict[str, list[SourceRecord]] = defaultdict(list)
    for record in records:
        for key_func in BLOCKING_KEY_FUNCS:
            key = key_func(record)
            if key is not None:
                blocks[key].append(record)
    return blocks


def generate_candidate_pairs(records: list[SourceRecord]) -> set[tuple[str, str]]:
    """
    Returns the deduplicated set of record-key pairs worth scoring, instead
    of every possible pair. Pairs are always returned with the
    lexicographically smaller record_key first, so the same pair never shows
    up twice even if it was found via two different blocks.
    """
    blocks = build_blocks(records)
    pairs: set[tuple[str, str]] = set()

    for block_records in blocks.values():
        if len(block_records) < 2:
            continue
        # Cap block size so one pathological block (e.g. every record missing
        # an IP falling into the same "unknown" bucket) can't blow up runtime.
        # In production this would instead log a warning and sample the block.
        capped = block_records[:200]
        for a, b in combinations(capped, 2):
            if a.record_key == b.record_key:
                continue
            key_pair = tuple(sorted((a.record_key, b.record_key)))
            pairs.add(key_pair)  # type: ignore[arg-type]

    return pairs
