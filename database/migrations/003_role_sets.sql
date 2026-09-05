-- =================================================================
-- Migration 003: RoleSets — per-stage governing role bundles
-- =================================================================
-- Introduces a reusable, named RoleSet entity: an unordered bundle of
-- roles that are valid to assign at a stage. `stages.role_set_id`
-- (nullable) points a stage at its own RoleSet; NULL means "inherit
-- from the nearest ancestor stage that has one", falling back to
-- unrestricted (today's behavior) if none do. RoleSets carry NO
-- ordering/workflow-escalation semantics — WorkflowAssignment / form
-- routing is untouched by this migration.
-- =================================================================

BEGIN;

-- =================================================================
-- 1. ROLE_SETS — reusable named bundles of roles
-- =================================================================
CREATE TABLE role_sets (
    role_set_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =================================================================
-- 2. ROLE_SET_ROLES — membership join table
-- =================================================================
CREATE TABLE role_set_roles (
    role_set_id VARCHAR(50) NOT NULL REFERENCES role_sets(role_set_id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    PRIMARY KEY (role_set_id, role_id)
);

CREATE INDEX idx_role_set_roles_role ON role_set_roles(role_id);

-- =================================================================
-- 3. STAGES.ROLE_SET_ID — a stage's own (optional) governing RoleSet
-- =================================================================
ALTER TABLE stages
    ADD COLUMN role_set_id VARCHAR(50) REFERENCES role_sets(role_set_id) ON DELETE SET NULL;

CREATE INDEX idx_stages_role_set_id ON stages(role_set_id);

-- No backfill: every existing stage gets role_set_id = NULL, which
-- resolves to "inherit from ancestor, else unrestricted" — this is
-- exactly today's behavior, so no existing UserProjectRole assignment
-- is retroactively affected by this migration.

COMMIT;
