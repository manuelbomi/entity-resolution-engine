# Entity Resolution Engine

This project takes messy data about the same hosts from three different systems and figures out which records actually describe the same real machine. Once it knows that, it builds one clean "golden record" per machine, keeps track of exactly where every value came from, and asks a human when it isn't sure enough to decide on its own.

## The problem this solves

If you've worked anywhere with more than one tool tracking infrastructure, you already know this pain: your CMDB says one thing, your cloud provider's inventory says something slightly different, and your monitoring agent reports something else again. Same machine, three different stories. Nobody wants to manually cross-reference three spreadsheets every time someone asks "what's actually running on this host and who owns it?"

That's the job of **entity resolution**: given records from multiple sources that don't agree with each other, decide which ones are about the same thing, and reconcile their differences into one trustworthy answer.

This matters a lot more once something is making automated decisions based on that data (an alerting system, an auto-remediation bot, a capacity planner). If the underlying data is a mess of duplicates and conflicting values, anything built on top of it is standing on sand.

## How it works, in order

```
 three messy sources           blocking              scoring              decision
┌─────────────┐          ┌──────────────────┐   ┌────────────────┐   ┌───────────────────┐
│ cmdb        │          │ group records    │   │ compare each   │   │ >= 0.90: auto-merge│
│ cloud_inv.  │ ───────► │ into small       │──►│ pair field by  │──►│ 0.65-0.90: human   │
│ monitoring  │          │ "blocks" so we   │   │ field, combine │   │           review   │
└─────────────┘          │ don't compare    │   │ into one score │   │ < 0.65: not a match│
                          │ everything to    │   └────────────────┘   └───────────────────┘
                          │ everything       │
                          └──────────────────┘
                                                                              │
                                                                              ▼
                                                                    ┌───────────────────┐
                                                                    │ golden record with │
                                                                    │ provenance + audit │
                                                                    │ log per field      │
                                                                    └───────────────────┘
```

**1. Blocking.** With a few thousand records, comparing every record to every other record is too slow, and almost all of those comparisons are a waste of time anyway (a server in Europe has nothing to do with an unrelated server in the US). So first, records get grouped into small "blocks" using cheap keys - a normalized hostname prefix, and the first three parts of the IP address. Only records that land in the same block get compared to each other. See `backend/app/resolution/blocking.py` for the full reasoning.

**2. Scoring.** For every pair of records that made it through blocking, we compare them field by field: how similar are the hostnames (typo-tolerant), is the IP address the same or at least on the same subnet, is the owner the same, are the timestamps close together. Each field gets its own similarity score from 0 to 1, and they're combined into one overall "composite score" using weights (hostname and IP matter a lot more than, say, the environment tag). One important detail: if a field is just *missing* on one side (a source that doesn't track "owner," for example), that's treated as "no opinion," not as a mismatch - a blank field shouldn't count against a match. See `backend/app/resolution/similarity.py`.

**3. Deciding.** Based on the composite score:
   - **0.90 and above** - confident enough to merge automatically.
   - **0.65 to 0.90** - plausible, but not confident enough to decide alone. This goes into a review queue for a human to approve or reject.
   - **Below 0.65** - not treated as a match at all.

**4. Building the golden record.** Once we know which records belong together, we still need to pick one final value per field when sources disagree. That's handled by **survivorship rules** - different rules for different fields. For example: the owner field trusts the CMDB over the other two sources (because people actually maintain that field by hand there), while the IP address and OS trust whichever source checked in most recently (because those reflect the live state of the machine). See `backend/app/resolution/survivorship.py`. Every decision - which records got merged, which source won each field, every approve/reject - is written to an audit log attached to the entity.

### A concrete example

Say these two records show up:

| field | cmdb record | monitoring_agent record |
|---|---|---|
| hostname | `web-use1-0412` | `web-use1-0412` |
| ip_address | `10.1.23.10` | `10.1.23.10` |
| owner | `platform-team` | *(not tracked)* |
| environment | `prod` | *(not tracked)* |
| last_seen | 3 days ago | 12 minutes ago |

Hostname and IP match exactly, the missing owner/environment fields are skipped rather than penalized, and the timestamps are both recent - the composite score comes out well above 0.90, so this pair gets merged automatically. The resulting golden record keeps `owner: platform-team` (from cmdb, since cmdb always wins ties on ownership fields) and `ip_address` / `last_seen` from whichever source reported most recently - with both decisions recorded in that entity's audit log.

## Project layout

```
backend/
  app/
    main.py              - FastAPI routes
    data_gen.py           - builds the synthetic multi-source dataset
    resolution/
      models.py           - SourceRecord, ResolvedEntity, CandidateMatch, etc.
      blocking.py          - candidate pair generation
      similarity.py         - per-field and composite scoring
      survivorship.py        - conflict resolution rules per field
      resolver.py              - ties it all together (union-find + registry)
  tests/                 - pytest unit tests for each piece above
frontend/
  src/
    api/                 - typed API client
    components/          - Entities table, Review queue, Metrics charts
```

## Running it locally

You'll need Python 3.11+ and Node 18+.

**Backend:**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API comes up on `http://localhost:8000`. On startup it generates a synthetic dataset (about 1,200 records simulating ~450 real hosts spread across three sources) and runs the resolver once, so there's data to look at immediately. You can call `POST /api/reset` any time to regenerate it from scratch.

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. It proxies `/api` calls to the backend, so make sure the backend is running first.

### Running the tests

```bash
cd backend
pytest
```

These tests cover blocking correctness, every similarity function's edge cases (including the "missing field shouldn't count against you" rule), survivorship conflict resolution, and end-to-end resolution scenarios (auto-merge, review queue, approve, reject).

## What you'll see in the dashboard

- **Entities** - the resolved golden records in a searchable table. Expand any row to see exactly which source contributed each field, plus the audit trail for that entity.
- **Review queue** - every pending candidate match, with a side-by-side field comparison and per-field similarity scores, so a reviewer can see *why* the system flagged it before approving or rejecting.
- **Metrics** - how many records came from each source, how many entities got auto-resolved, the size of the review queue, and the confidence spread of everything currently pending.

## What's deliberately simplified here (and what a bigger deployment would add)

- **In-memory state.** Everything lives in memory and resets when the process restarts. A real deployment would put the entity registry and audit log in Postgres, with the resolver's blocking/scoring logic staying exactly the same - only the storage layer would change. The code already separates "decide what matches" from "where results are stored" so that swap wouldn't touch the resolution logic itself.
- **Fixed similarity weights.** The weight each field carries in the composite score (hostname 40%, IP 30%, and so on) was set by reasoning about which fields are strong identity signals, not learned from data. A mature system would tune these weights from the history of human approve/reject decisions in the review queue - that feedback loop isn't built here, but the review queue already captures exactly the labeled data you'd need to build it.
- **Synthetic data.** The three "sources" are generated from a fixed random seed to simulate realistic messiness (typos, missing fields, stale timestamps, partial overlap) - they aren't real inventory data. The resolution engine itself doesn't know or care that the data is synthetic; pointing it at real source systems is a matter of writing an adapter that produces `SourceRecord` objects, not changing any matching logic.
- **Single-pass batch resolution.** Resolution runs once at startup and then incrementally as review decisions come in. A live system would re-run resolution continuously as new records stream in from each source.

## License

MIT - see `LICENSE`.
