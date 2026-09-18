-- Migration 005: Denormalized project_stage_id on form_records
--
-- Link fields need to be able to answer "does this candidate record belong
-- to the same project as the record I'm editing?" without walking the stage
-- tree on every query. This adds project_stage_id to form_records, mirroring
-- the same "owning depth-1 Stage" rule already used by
-- StageService.resolve_project_stage_id() / the project rosters feature in
-- migration 004: lineage_path[1] (SQL: lineage_path[2], since Postgres
-- arrays are 1-indexed and lineage_path[1] is always the hidden root
-- 'stage_system') is the project for anything below depth 1; a depth-1
-- stage is its own project.
--
-- Purely additive: existing rows are backfilled, nothing is removed, and
-- nothing changes for the application until the code that reads/writes
-- project_stage_id ships alongside this migration.

BEGIN;

ALTER TABLE form_records
    ADD COLUMN project_stage_id VARCHAR(50) REFERENCES stages(stage_id);

CREATE INDEX idx_form_records_project ON form_records(project_stage_id);

-- Backfill existing rows from their stage's lineage.
UPDATE form_records fr
SET project_stage_id = CASE
    WHEN s.depth_level = 1 THEN s.stage_id
    WHEN s.depth_level > 1 AND array_length(s.lineage_path, 1) > 1 THEN s.lineage_path[2]
    ELSE NULL
END
FROM stages s
WHERE fr.stage_id = s.stage_id;

COMMIT;
