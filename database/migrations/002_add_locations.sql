-- =================================================================
-- Migration 002: Add Location Table & Scoped Permissions
-- =================================================================

BEGIN;

-- 1. Create locations table
CREATE TABLE locations (
    location_id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_locations_name ON locations(name);

-- Trigger for updated_at
CREATE TRIGGER t_locations_update_timestamp
BEFORE UPDATE ON locations
FOR EACH ROW
EXECUTE FUNCTION trg_update_timestamp();

-- 2. Link users table to locations
ALTER TABLE users ADD COLUMN location_id VARCHAR(36) REFERENCES locations(location_id);
CREATE INDEX idx_users_location_id ON users(location_id);

-- 3. Extend stage_permissions table
ALTER TABLE stage_permissions ADD COLUMN location_id VARCHAR(36) REFERENCES locations(location_id) ON DELETE CASCADE;
ALTER TABLE stage_permissions ADD COLUMN department_id VARCHAR(36) REFERENCES departments(department_id) ON DELETE CASCADE;

CREATE INDEX idx_stage_permissions_location_id ON stage_permissions(location_id);
CREATE INDEX idx_stage_permissions_department_id ON stage_permissions(department_id);

ALTER TABLE stage_permissions DROP CONSTRAINT uq_stage_role;

-- Partial unique indexes to handle NULL values in location_id and department_id
CREATE UNIQUE INDEX uq_stage_role_global ON stage_permissions (stage_id, role_name)
WHERE location_id IS NULL AND department_id IS NULL;

CREATE UNIQUE INDEX uq_stage_role_location ON stage_permissions (stage_id, role_name, location_id)
WHERE department_id IS NULL;

CREATE UNIQUE INDEX uq_stage_role_department ON stage_permissions (stage_id, role_name, department_id)
WHERE location_id IS NULL;

CREATE UNIQUE INDEX uq_stage_role_location_dept ON stage_permissions (stage_id, role_name, location_id, department_id)
WHERE location_id IS NOT NULL AND department_id IS NOT NULL;

-- 4. Extend form_type_permissions table
ALTER TABLE form_type_permissions ADD COLUMN location_id VARCHAR(36) REFERENCES locations(location_id) ON DELETE CASCADE;
ALTER TABLE form_type_permissions ADD COLUMN department_id VARCHAR(36) REFERENCES departments(department_id) ON DELETE CASCADE;

CREATE INDEX idx_form_type_permissions_location_id ON form_type_permissions(location_id);
CREATE INDEX idx_form_type_permissions_department_id ON form_type_permissions(department_id);

ALTER TABLE form_type_permissions DROP CONSTRAINT uq_form_type_role;

-- Partial unique indexes to handle NULL values in location_id and department_id
CREATE UNIQUE INDEX uq_form_type_role_global ON form_type_permissions (form_type_id, role_name)
WHERE location_id IS NULL AND department_id IS NULL;

CREATE UNIQUE INDEX uq_form_type_role_location ON form_type_permissions (form_type_id, role_name, location_id)
WHERE department_id IS NULL;

CREATE UNIQUE INDEX uq_form_type_role_department ON form_type_permissions (form_type_id, role_name, department_id)
WHERE location_id IS NULL;

CREATE UNIQUE INDEX uq_form_type_role_location_dept ON form_type_permissions (form_type_id, role_name, location_id, department_id)
WHERE location_id IS NOT NULL AND department_id IS NOT NULL;

COMMIT;
