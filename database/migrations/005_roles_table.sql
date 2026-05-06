-- =================================================================
-- Migration 005: Introduce a dedicated `roles` table and keep
--               `user_roles` as a single row per user with a
--               JSONB array of role_id integers.
--
-- Before: user_roles(user_id PK, roles JSONB)   ← role name strings
-- After:  roles(role_id PK, role_name UNIQUE, …)
--         user_roles(user_id PK, role_ids JSONB) ← role_id integers
-- =================================================================

BEGIN;

-- ----------------------------------------------------------------
-- 1. Create the roles table
-- ----------------------------------------------------------------
CREATE TABLE roles (
    role_id     BIGSERIAL    PRIMARY KEY,
    role_name   VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(100)
);

CREATE INDEX idx_roles_name ON roles(role_name);

-- ----------------------------------------------------------------
-- 2. Seed roles from existing stage / form-type permission tables
--    plus any roles already in user_roles JSONB name arrays.
-- ----------------------------------------------------------------
INSERT INTO roles (role_name, created_at)
SELECT DISTINCT role_name, NOW()
FROM (
    SELECT role_name FROM stage_permissions
    UNION
    SELECT role_name FROM form_type_permissions
) combined
ON CONFLICT (role_name) DO NOTHING;

INSERT INTO roles (role_name, created_at)
SELECT DISTINCT jsonb_array_elements_text(roles), NOW()
FROM user_roles
ON CONFLICT (role_name) DO NOTHING;

-- ----------------------------------------------------------------
-- 3. Capture existing user → role_id mappings before we alter
--    the user_roles table.
-- ----------------------------------------------------------------
CREATE TEMP TABLE _user_role_ids AS
SELECT
    ur.user_id,
    jsonb_agg(r.role_id ORDER BY r.role_id) AS role_ids
FROM user_roles ur
CROSS JOIN LATERAL jsonb_array_elements_text(ur.roles) AS rn(role_name)
JOIN roles r ON r.role_name = rn.role_name
GROUP BY ur.user_id;

-- ----------------------------------------------------------------
-- 4. Drop the old JSONB (role name strings) user_roles table
--    and replace with one row per user storing role_id integers.
-- ----------------------------------------------------------------
DROP TABLE user_roles;

CREATE TABLE user_roles (
    user_id     VARCHAR(100) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    role_ids    JSONB        NOT NULL DEFAULT '[]'::jsonb,
    assigned_at TIMESTAMP    NOT NULL DEFAULT NOW(),
    assigned_by VARCHAR(100)
);

-- GIN index for fast containment queries (@>)
CREATE INDEX idx_user_roles_role_ids_gin ON user_roles USING gin(role_ids);

-- ----------------------------------------------------------------
-- 5. Restore user → role assignments as integer arrays
-- ----------------------------------------------------------------
INSERT INTO user_roles (user_id, role_ids, assigned_at)
SELECT user_id, COALESCE(role_ids, '[]'::jsonb), NOW()
FROM _user_role_ids
ON CONFLICT DO NOTHING;

DROP TABLE _user_role_ids;

COMMIT;
