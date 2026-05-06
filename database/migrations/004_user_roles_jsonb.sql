-- =============================================================
-- Migration 004: Alter user_roles to use JSONB roles column
--
-- Old schema: (user_id, role_name) composite PK — one row per role.
-- New schema: (user_id) PK — one row per user, roles stored as
--             a JSONB array of role-name strings.
-- =============================================================

BEGIN;

-- Step 1: Aggregate existing role assignments into a temp table
CREATE TEMP TABLE _user_roles_agg AS
SELECT
    user_id,
    jsonb_agg(DISTINCT role_name ORDER BY role_name) AS roles
FROM user_roles
WHERE user_id NOT LIKE '_role:%'   -- exclude internal role-tracker sentinels
GROUP BY user_id;

-- Step 2: Drop the old table (cascade drops indexes + FK ref from user model)
DROP TABLE user_roles;

-- Step 3: Create new table with JSONB roles column
CREATE TABLE user_roles (
    user_id     VARCHAR(100) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    roles       JSONB        NOT NULL DEFAULT '[]'::jsonb,
    assigned_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(100)
);

-- GIN index for fast containment queries  (@>, ?, etc.)
CREATE INDEX idx_user_roles_roles_gin ON user_roles USING gin(roles);

-- Step 4: Restore aggregated data
INSERT INTO user_roles (user_id, roles, assigned_at)
SELECT user_id, roles, NOW()
FROM _user_roles_agg
ON CONFLICT (user_id) DO UPDATE SET roles = EXCLUDED.roles;

DROP TABLE _user_roles_agg;

COMMIT;
