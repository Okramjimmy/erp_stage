-- Migration 004: Project-level Roles and Members rosters
--
-- A project (depth-1 Stage) can now maintain its own roster of allowed
-- roles and allowed members. Every stage below a project — at any depth —
-- is restricted to these rosters when assigning a UserProjectRole. An
-- empty roster (the default for every project) means "unrestricted",
-- identical in spirit to how a stage with no governing RoleSet is
-- unrestricted. This is purely additive: nothing changes for any project
-- until an admin populates its Roles/Members rosters deliberately.
--
-- The RoleSets bucket introduced alongside this in the UI needs no new
-- table — it's a live filter over the existing role_sets/role_set_roles.

BEGIN;

CREATE TABLE project_roles (
    stage_id VARCHAR(50) NOT NULL REFERENCES stages(stage_id) ON DELETE CASCADE,
    role_id  INTEGER     NOT NULL REFERENCES roles(role_id)   ON DELETE CASCADE,
    PRIMARY KEY (stage_id, role_id)
);
CREATE INDEX idx_project_roles_role ON project_roles(role_id);

CREATE TABLE project_members (
    stage_id VARCHAR(50) NOT NULL REFERENCES stages(stage_id) ON DELETE CASCADE,
    user_id  VARCHAR(36) NOT NULL REFERENCES users(user_id)   ON DELETE CASCADE,
    PRIMARY KEY (stage_id, user_id)
);
CREATE INDEX idx_project_members_user ON project_members(user_id);

COMMIT;
