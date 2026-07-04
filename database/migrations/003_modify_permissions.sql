-- =================================================================
-- Migration 003: Split Form Type vs Form Record permissions
-- =================================================================

BEGIN;

-- 1. Rename can_create to can_create_records
ALTER TABLE form_type_permissions RENAME COLUMN can_create TO can_create_records;

-- 2. Add can_edit_records and can_delete_records
ALTER TABLE form_type_permissions ADD COLUMN can_edit_records BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE form_type_permissions ADD COLUMN can_delete_records BOOLEAN NOT NULL DEFAULT FALSE;

-- 3. Copy existing values for backward compatibility
UPDATE form_type_permissions SET 
    can_edit_records = can_edit, 
    can_delete_records = can_delete;

COMMIT;
