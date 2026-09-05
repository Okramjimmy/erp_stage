-- =================================================================
-- Migration 002: Project-scoped roles + FormType category permissions
-- =================================================================
-- Replaces the global `user_roles` (one row per user, JSONB role_ids
-- array) with `user_project_roles`: one row per (user, project/stage,
-- role), so a user can belong to multiple projects and hold multiple
-- roles per project. `stage_id IS NULL` means the role is granted
-- globally (used for true system-wide roles like 'superadmin').
--
-- Also adds `category_permissions`, a permission tier scoped to a
-- project (stage) + FormType.group category, sitting between
-- stage_permissions and form_type_permissions in the resolution chain.
-- =================================================================

BEGIN;

-- =================================================================
-- 1. USER_PROJECT_ROLES — replaces user_roles
-- =================================================================
CREATE TABLE user_project_roles (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    stage_id VARCHAR(50) REFERENCES stages(stage_id) ON DELETE CASCADE,  -- NULL = global grant
    role_id INTEGER NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,

    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(100)
);

CREATE INDEX idx_upr_user ON user_project_roles(user_id);
CREATE INDEX idx_upr_stage ON user_project_roles(stage_id);
CREATE INDEX idx_upr_role ON user_project_roles(role_id);

-- One row per (user, stage, role); one row per (user, role) when global
CREATE UNIQUE INDEX uq_upr_scoped ON user_project_roles (user_id, stage_id, role_id)
    WHERE stage_id IS NOT NULL;
CREATE UNIQUE INDEX uq_upr_global ON user_project_roles (user_id, role_id)
    WHERE stage_id IS NULL;

-- =================================================================
-- 2. CATEGORY_PERMISSIONS — project + FormType.group tier
-- =================================================================
CREATE TABLE category_permissions (
    permission_id BIGSERIAL PRIMARY KEY,
    stage_id VARCHAR(50) NOT NULL REFERENCES stages(stage_id) ON DELETE CASCADE,
    category VARCHAR(100) NOT NULL,       -- matches form_types."group" (free string, no FK)
    role_name VARCHAR(100) NOT NULL,

    location_id VARCHAR(36) REFERENCES locations(location_id) ON DELETE CASCADE,
    department_id VARCHAR(36) REFERENCES departments(department_id) ON DELETE CASCADE,

    can_view BOOLEAN NOT NULL DEFAULT FALSE,
    can_create_records BOOLEAN NOT NULL DEFAULT FALSE,
    can_edit BOOLEAN NOT NULL DEFAULT FALSE,
    can_delete BOOLEAN NOT NULL DEFAULT FALSE,
    can_edit_records BOOLEAN NOT NULL DEFAULT FALSE,
    can_delete_records BOOLEAN NOT NULL DEFAULT FALSE,
    can_submit BOOLEAN NOT NULL DEFAULT FALSE,
    can_verify BOOLEAN NOT NULL DEFAULT FALSE,
    can_cancel BOOLEAN NOT NULL DEFAULT FALSE,
    can_amend BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage_permissions BOOLEAN NOT NULL DEFAULT FALSE,

    granted_by VARCHAR(100),
    granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_category_permissions_stage ON category_permissions(stage_id);
CREATE INDEX idx_category_permissions_category ON category_permissions(category);
CREATE INDEX idx_category_permissions_role ON category_permissions(role_name);
CREATE INDEX idx_category_permissions_location_id ON category_permissions(location_id);
CREATE INDEX idx_category_permissions_department_id ON category_permissions(department_id);

-- Partial unique indexes, same pattern as stage_permissions / form_type_permissions
CREATE UNIQUE INDEX uq_category_role_global ON category_permissions (stage_id, category, role_name)
    WHERE location_id IS NULL AND department_id IS NULL;

CREATE UNIQUE INDEX uq_category_role_location ON category_permissions (stage_id, category, role_name, location_id)
    WHERE department_id IS NULL;

CREATE UNIQUE INDEX uq_category_role_department ON category_permissions (stage_id, category, role_name, department_id)
    WHERE location_id IS NULL;

CREATE UNIQUE INDEX uq_category_role_location_dept ON category_permissions (stage_id, category, role_name, location_id, department_id)
    WHERE location_id IS NOT NULL AND department_id IS NOT NULL;

-- =================================================================
-- 3. BACKFILL — preserve existing global semantics exactly
-- =================================================================
INSERT INTO user_project_roles (user_id, stage_id, role_id, assigned_at, assigned_by)
SELECT ur.user_id, NULL, (rid.value)::int, ur.assigned_at, ur.assigned_by
FROM user_roles ur, jsonb_array_elements_text(ur.role_ids) AS rid(value);

-- =================================================================
-- 4. DROP superseded objects
-- =================================================================
-- has_subtree_permission() referenced user_roles and is not called from
-- any application code (dead SQL helper) — drop rather than maintain.
DROP FUNCTION IF EXISTS has_subtree_permission(VARCHAR, VARCHAR, VARCHAR);

DROP TABLE user_roles CASCADE;

COMMIT;
