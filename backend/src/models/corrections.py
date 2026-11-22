from fastapi import HTTPException


def get_correction(db, correction_id):
    row = db.execute("SELECT * FROM corrections WHERE id = %s", (correction_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "找不到该更正单")
    return row


def list_corrections(db, lot_id):
    return db.execute("""
        SELECT c.id, c.ticket, c.sample_code, c.location, c.dry_g, c.impurity_g, c.status,
               c.submitted_at, c.resolved_at, s.display_name AS submitter, r.display_name AS resolver
        FROM corrections c JOIN accounts s ON s.id = c.submitted_by
        LEFT JOIN accounts r ON r.id = c.resolved_by
        WHERE c.lot_id = %s ORDER BY c.id DESC
    """, (lot_id,)).fetchall()
