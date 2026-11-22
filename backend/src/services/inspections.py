import logging

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from redis.exceptions import RedisError

from src.config.runtime import WAKE_KEY, connect, queue
from src.constants.domain import CorrectionStatus, RunStatus
from src.models.inspections import get_inspection
from src.models.ledger import get_lot, sample_snapshot, write_event
from src.services.weighted_tail import InsufficientSamples, analyze, sample_changes, tail_diff
from src.utils.snapshot import checksum

log = logging.getLogger(__name__)


def stage_run(db, lot_id, parameters, actor, correction_id=None):
    """Lock the current weighing snapshot into a new queued version."""
    snapshot = sample_snapshot(db, lot_id)
    version = db.execute("""
        SELECT COALESCE(max(version), 0) + 1 AS next FROM inspections WHERE lot_id = %s
    """, (lot_id,)).fetchone()["next"]
    row = db.execute("""
        INSERT INTO inspections (lot_id, version, parameters, snapshot, checksum, status, requested_by, correction_id)
        VALUES (%s, %s, %s, %s, %s, 'queued', %s, %s) RETURNING id, version, status
    """, (lot_id, version, Jsonb(parameters), Jsonb(snapshot), checksum(snapshot), actor, correction_id)).fetchone()
    write_event(db, lot_id, actor, "inspection_queued", f"V{version:02}")
    return row


def wake_worker(run_id):
    try:
        with queue.pipeline() as pipeline:
            pipeline.lpush(WAKE_KEY, run_id).ltrim(WAKE_KEY, 0, 0).execute()
    except RedisError:
        log.warning("Redis wake signal unavailable; worker will poll the durable queue")


def enqueue(lot_id, parameters, actor):
    with connect() as db:
        get_lot(db, lot_id, lock=True)
        row = stage_run(db, lot_id, parameters.model_dump(mode="json"), actor)
    wake_worker(row["id"])
    return row


def _comparison(db, job, result):
    previous = db.execute("""
        SELECT version, checksum, parameters, snapshot, result FROM inspections
        WHERE lot_id = %s AND version < %s AND status = 'succeeded'
        ORDER BY version DESC LIMIT 1
    """, (job["lot_id"], job["version"])).fetchone()
    if not previous:
        return None
    comparison = {
        "previous_version": previous["version"],
        "same_samples": previous["checksum"] == job["checksum"],
        "previous_parameters": previous["parameters"],
        "exceed_delta_pp": result["exceed_share_pct"] - previous["result"]["exceed_share_pct"],
        "tail_delta_pp": result["tail_mean_pct"] - previous["result"]["tail_mean_pct"],
    }
    diff = tail_diff(
        previous["snapshot"], previous["parameters"]["tail_pct"],
        job["snapshot"], job["parameters"]["tail_pct"],
    )
    if diff["entries"]:
        comparison["tail_diff"] = diff
    if not comparison["same_samples"]:
        comparison["sample_changes"] = sample_changes(previous["snapshot"], job["snapshot"])
    return comparison


def process_next(db):
    job = db.execute("""
        SELECT * FROM inspections WHERE status = 'queued' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED
    """).fetchone()
    if not job:
        return False
    try:
        result = analyze(job["snapshot"], job["parameters"])
        result["comparison"] = _comparison(db, job, result)
    except InsufficientSamples as exc:
        db.execute("""
            UPDATE inspections SET status = 'failed', error = %s, completed_at = now() WHERE id = %s
        """, (str(exc), job["id"]))
        action = "inspection_failed"
    else:
        db.execute("""
            UPDATE inspections SET status = 'succeeded', result = %s, completed_at = now() WHERE id = %s
        """, (Jsonb(result), job["id"]))
        action = "inspection_completed"
    write_event(db, job["lot_id"], None, action, f"V{job['version']:02}")
    return True


def publish_context(db, lot_id):
    latest = db.execute(
        "SELECT max(version) AS version FROM inspections WHERE lot_id = %s", (lot_id,)
    ).fetchone()["version"]
    current = checksum(sample_snapshot(db, lot_id))
    pending = db.execute(
        "SELECT 1 FROM corrections WHERE lot_id = %s AND status = %s LIMIT 1",
        (lot_id, CorrectionStatus.PENDING),
    ).fetchone() is not None
    return {"latest": latest, "checksum": current, "has_pending": pending}


def resolve_publish_state(row, context):
    if row["outcome"]:
        return "published"
    if row["status"] == RunStatus.QUEUED:
        return "queued"
    if row["status"] == RunStatus.FAILED:
        return "failed"
    if row["version"] != context["latest"]:
        return "superseded"
    if row["checksum"] != context["checksum"]:
        return "stale"
    if context["has_pending"]:
        return "draft"
    return "publishable"


def attach_publish_state(db, lot_id, runs):
    context = publish_context(db, lot_id)
    for run in runs:
        run["publish_state"] = resolve_publish_state(run, context)


def publish(run_id, payload, actor):
    with connect() as db:
        row = get_inspection(db, run_id)
        get_lot(db, row["lot_id"], lock=True)
        row = get_inspection(db, run_id)
        latest = db.execute("SELECT max(version) AS version FROM inspections WHERE lot_id = %s", (row["lot_id"],)).fetchone()
        if row["outcome"] or row["status"] != RunStatus.SUCCEEDED or row["version"] != latest["version"]:
            raise HTTPException(409, "仅最新且已算完的待复核版本可发布")
        if row["checksum"] != checksum(sample_snapshot(db, row["lot_id"])):
            raise HTTPException(409, "干样台账已有新增，请重新诊断后发布")
        if db.execute(
            "SELECT 1 FROM corrections WHERE lot_id = %s AND status = %s LIMIT 1",
            (row["lot_id"], CorrectionStatus.PENDING),
        ).fetchone():
            raise HTTPException(409, "存在待裁定的称重更正，请先裁定并按有效称重重算")
        db.execute("""
            INSERT INTO decisions (inspection_id, outcome, rationale, reviewer_id) VALUES (%s, %s, %s, %s)
        """, (run_id, payload.outcome, payload.rationale, actor))
        write_event(db, row["lot_id"], actor, "decision_published", f"V{row['version']:02}")
        return get_inspection(db, run_id)
