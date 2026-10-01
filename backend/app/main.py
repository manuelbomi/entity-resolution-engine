"""
FastAPI app wiring together the data generator and the resolution engine.

State lives in one module-level `EntityResolutionEngine` instance, built
once at startup. There's no database - this is explained in the README. The
important part for this project is the resolution logic in app/resolution/,
not the storage layer.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .data_gen import generate_source_records
from .resolution.models import MatchStatus
from .resolution.resolver import EntityResolutionEngine

app = FastAPI(title="Entity Resolution Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine: EntityResolutionEngine


def _build_engine() -> EntityResolutionEngine:
    records = generate_source_records()
    new_engine = EntityResolutionEngine(records)
    new_engine.run_initial_resolution()
    return new_engine


@app.on_event("startup")
def startup() -> None:
    global engine
    engine = _build_engine()


class ReviewDecision(BaseModel):
    approve: bool


def _entity_to_dict(entity) -> dict:
    return {
        "entity_id": entity.entity_id,
        "member_keys": sorted(entity.member_keys),
        "source_count": len(entity.member_keys),
        "fields": {
            name: {"value": prov.value, "source_name": prov.source_name, "source_id": prov.source_id}
            for name, prov in entity.fields.items()
        },
    }


def _entity_detail_to_dict(entity) -> dict:
    base = _entity_to_dict(entity)
    base["audit_log"] = [
        {"timestamp": e.timestamp.isoformat(), "action": e.action, "detail": e.detail} for e in entity.audit_log
    ]
    return base


def _candidate_to_dict(candidate) -> dict:
    record_a = engine.records_by_key[candidate.record_a_key]
    record_b = engine.records_by_key[candidate.record_b_key]
    return {
        "candidate_id": candidate.candidate_id,
        "status": candidate.status.value,
        "composite_score": candidate.composite_score,
        "field_scores": candidate.field_scores,
        "record_a": {
            "record_key": record_a.record_key,
            "source_name": record_a.source_name,
            "hostname": record_a.hostname,
            "ip_address": record_a.ip_address,
            "owner": record_a.owner,
            "environment": record_a.environment,
            "os": record_a.os,
            "last_seen": record_a.last_seen.isoformat(),
        },
        "record_b": {
            "record_key": record_b.record_key,
            "source_name": record_b.source_name,
            "hostname": record_b.hostname,
            "ip_address": record_b.ip_address,
            "owner": record_b.owner,
            "environment": record_b.environment,
            "os": record_b.os,
            "last_seen": record_b.last_seen.isoformat(),
        },
    }


@app.get("/api/sources")
def list_sources() -> list[dict]:
    counts: dict[str, int] = {}
    for record in engine.records_by_key.values():
        counts[record.source_name] = counts.get(record.source_name, 0) + 1
    return [{"source_name": name, "record_count": count} for name, count in sorted(counts.items())]


@app.get("/api/entities")
def list_entities(page: int = 1, page_size: int = 25, search: str | None = None) -> dict:
    entities = engine.build_entities()
    if search:
        search_lower = search.lower()
        entities = [
            e for e in entities if search_lower in str(e.fields.get("hostname", "")).lower()
        ]
    entities.sort(key=lambda e: e.fields.get("hostname").value if e.fields.get("hostname") else "")
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "total": len(entities),
        "page": page,
        "page_size": page_size,
        "items": [_entity_to_dict(e) for e in entities[start:end]],
    }


@app.get("/api/entities/{entity_id}")
def get_entity(entity_id: str) -> dict:
    entities = engine.build_entities()
    for entity in entities:
        if entity.entity_id == entity_id:
            return _entity_detail_to_dict(entity)
    raise HTTPException(status_code=404, detail="entity not found")


@app.get("/api/review-queue")
def get_review_queue() -> list[dict]:
    return [_candidate_to_dict(c) for c in engine.review_queue()]


@app.post("/api/review-queue/{candidate_id}/decision")
def decide(candidate_id: str, decision: ReviewDecision) -> dict:
    if candidate_id not in engine.candidates:
        raise HTTPException(status_code=404, detail="candidate not found")
    candidate = engine.decide_candidate(candidate_id, decision.approve)
    return {
        "candidate_id": candidate.candidate_id,
        "status": candidate.status.value,
    }


@app.get("/api/metrics")
def get_metrics() -> dict:
    return engine.metrics()


@app.post("/api/reset")
def reset() -> dict:
    """Regenerates the synthetic dataset and re-runs resolution from scratch."""
    global engine
    engine = _build_engine()
    return {"status": "reset"}
