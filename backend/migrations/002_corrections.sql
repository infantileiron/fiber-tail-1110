CREATE TABLE IF NOT EXISTS corrections (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lot_id bigint NOT NULL REFERENCES lots(id),
    ticket text NOT NULL,
    sample_code text NOT NULL,
    location text NOT NULL,
    dry_g integer NOT NULL CHECK (dry_g > 0),
    impurity_g integer NOT NULL CHECK (impurity_g BETWEEN 0 AND dry_g),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'adopted', 'rejected')),
    submitted_by bigint NOT NULL REFERENCES accounts(id),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    resolved_by bigint REFERENCES accounts(id),
    resolved_at timestamptz,
    UNIQUE (lot_id, ticket)
);
CREATE INDEX IF NOT EXISTS corrections_pending ON corrections (lot_id) WHERE status = 'pending';

ALTER TABLE inspections ADD COLUMN IF NOT EXISTS correction_id bigint REFERENCES corrections(id);
