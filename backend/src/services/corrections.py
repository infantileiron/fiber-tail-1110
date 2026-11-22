from fastapi import HTTPException

from src.config.runtime import connect
from src.constants.domain import CorrectionStatus
from src.models.corrections import get_correction
from src.models.ledger import get_lot, write_event
from src.services.inspections import stage_run, wake_worker

REPLAY_FIELDS = ("sample_code", "location", "dry_g", "impurity_g")


def file_correction(lot_id, payload, actor, response):
    """File a weighing correction ticket.

    Conflicting tickets for the same sample are all kept as pending. Retrying a
    ticket number with identical content returns the filed row instead of
    booking a duplicate; the same number with different content is rejected.
    """
    with connect() as db:
        get_lot(db, lot_id, lock=True)
        sample = db.execute(
            "SELECT 1 FROM samples WHERE lot_id = %s AND code = %s", (lot_id, payload.sample_code)
        ).fetchone()
        if not sample:
            raise HTTPException(404, "找不到要更正的干样")
        row = db.execute("""
            INSERT INTO corrections (lot_id, ticket, sample_code, location, dry_g, impurity_g, submitted_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (lot_id, ticket) DO NOTHING
            RETURNING *
        """, (lot_id, payload.ticket, payload.sample_code, payload.location,
              payload.dry_g, payload.impurity_g, actor)).fetchone()
        if row is None:
            row = db.execute(
                "SELECT * FROM corrections WHERE lot_id = %s AND ticket = %s", (lot_id, payload.ticket)
            ).fetchone()
            if any(row[field] != getattr(payload, field) for field in REPLAY_FIELDS):
                raise HTTPException(409, "该更正单号已入账，内容不一致时请换用新单号")
            response.status_code = 200
            return row | {"duplicate": True}
        write_event(db, lot_id, actor, "correction_submitted", f"{row['ticket']}·{row['sample_code']}")
        return row | {"duplicate": False}


def adjudicate(correction_id, payload, actor):
    """Rule on a pending correction.

    Adopting a ticket applies its weighing to the ledger, dismisses the other
    pending tickets for the same sample, and re-queues the lot with the latest
    version's parameters so the batch is recomputed on the effective weighing.
    """
    with connect() as db:
        row = get_correction(db, correction_id)
        get_lot(db, row["lot_id"], lock=True)
        row = get_correction(db, correction_id)
        if row["status"] != CorrectionStatus.PENDING:
            raise HTTPException(409, "该更正单已裁定，不能重复处理")
        run = None
        if payload.verdict == CorrectionStatus.ADOPTED:
            db.execute("""
                UPDATE corrections SET status = 'adopted', resolved_by = %s, resolved_at = now() WHERE id = %s
            """, (actor, correction_id))
            siblings = db.execute("""
                UPDATE corrections SET status = 'rejected', resolved_by = %s, resolved_at = now()
                WHERE lot_id = %s AND sample_code = %s AND status = 'pending' AND id <> %s
                RETURNING ticket
            """, (actor, row["lot_id"], row["sample_code"], correction_id)).fetchall()
            db.execute("""
                UPDATE samples SET location = %s, dry_g = %s, impurity_g = %s
                WHERE lot_id = %s AND code = %s
            """, (row["location"], row["dry_g"], row["impurity_g"], row["lot_id"], row["sample_code"]))
            write_event(db, row["lot_id"], actor, "correction_adopted", f"{row['ticket']}·{row['sample_code']}")
            for sibling in siblings:
                write_event(db, row["lot_id"], actor, "correction_rejected", f"{sibling['ticket']}·{row['sample_code']}")
            last = db.execute("""
                SELECT parameters FROM inspections WHERE lot_id = %s ORDER BY version DESC LIMIT 1
            """, (row["lot_id"],)).fetchone()
            if last:
                run = stage_run(db, row["lot_id"], last["parameters"], actor, correction_id)
        else:
            db.execute("""
                UPDATE corrections SET status = 'rejected', resolved_by = %s, resolved_at = now() WHERE id = %s
            """, (actor, correction_id))
            write_event(db, row["lot_id"], actor, "correction_rejected", f"{row['ticket']}·{row['sample_code']}")
    if run:
        wake_worker(run["id"])
    return {
        "correction_id": correction_id,
        "verdict": payload.verdict,
        "recompute_version": run["version"] if run else None,
    }
