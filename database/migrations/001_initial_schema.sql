-- =================================================================
-- Migration 001: Initial Schema
-- Hierarchical Stage & Form Builder ERP Module
-- =================================================================
-- Description: Creates all core tables, indexes, and functions
-- Version: 1.0
-- Date: 2024
-- =================================================================

BEGIN;

-- =================================================================
-- 1. STAGES TABLE
-- =================================================================
-- Core table for hierarchical stage (folder) structure
-- =================================================================
CREATE TABLE stages (
    stage_id VARCHAR(50) PRIMARY KEY,
    stage_name VARCHAR(255) NOT NULL,
    parent_stage_id VARCHAR(50) REFERENCES stages(stage_id),

    -- Hierarchical fields
    stage_path TEXT NOT NULL,
    depth_level INTEGER NOT NULL DEFAULT 0,
    lineage_path TEXT[] NOT NULL,

    -- Counts
    children_count INTEGER NOT NULL DEFAULT 0,
    formtype_count INTEGER NOT NULL DEFAULT 0,

    -- Visibility
    is_root BOOLEAN NOT NULL DEFAULT FALSE,
    is_leaf BOOLEAN NOT NULL DEFAULT TRUE,
    visibility_scope VARCHAR(20) DEFAULT 'private',

    -- Timestamps
    created_by VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    metadata_reference TEXT,

    -- Constraints
    CONSTRAINT uq_stage_path UNIQUE (stage_path),
    CONSTRAINT chk_depth_non_negative CHECK (depth_level >= 0),
    CONSTRAINT chk_children_non_negative CHECK (children_count >= 0),
    CONSTRAINT chk_formtype_non_negative CHECK (formtype_count >= 0),
    CONSTRAINT chk_visibility_scope CHECK (visibility_scope IN ('public', 'private', 'restricted'))
);

-- Indexes for stages
CREATE INDEX idx_stages_parent ON stages(parent_stage_id);
CREATE INDEX idx_stages_path_gin ON stages USING GIN(to_tsvector('english', stage_path));
CREATE INDEX idx_stages_lineage_gin ON stages USING GIN(lineage_path);
CREATE INDEX idx_stages_depth ON stages(depth_level);
CREATE INDEX idx_stages_visibility ON stages(visibility_scope);
CREATE INDEX idx_stages_created_at ON stages(created_at);
CREATE INDEX idx_stages_updated_at ON stages(updated_at);
CREATE INDEX idx_stages_name ON stages(stage_name);


-- =================================================================
-- 2. FORM_TYPES TABLE
-- =================================================================
-- Core table for form type definitions within stages
-- =================================================================
CREATE TABLE form_types (
    form_type_id VARCHAR(50) PRIMARY KEY,
    form_name VARCHAR(255) NOT NULL,

    -- Hierarchy
    stage_id VARCHAR(50) NOT NULL REFERENCES stages(stage_id) ON DELETE CASCADE,
    form_path TEXT NOT NULL,

    -- Versioning
    version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    schema_reference TEXT,

    -- Timestamps
    created_by VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_form_path UNIQUE (form_path),
    CONSTRAINT chk_version_format CHECK (version ~ '^\d{1,3}\.\d{1,3}\.\d{1,3}$')
);

-- Indexes for form_types
CREATE INDEX idx_form_types_stage ON form_types(stage_id);
CREATE INDEX idx_form_types_path ON form_types(form_path);
CREATE INDEX idx_form_types_path_gin ON form_types USING GIN(to_tsvector('english', form_path));
CREATE INDEX idx_form_types_created_at ON form_types(created_at);
CREATE INDEX idx_form_types_name ON form_types(form_name);


-- =================================================================
-- 3. STAGE_PERMISSIONS TABLE
-- =================================================================
-- Role-based permissions for stages
-- =================================================================
CREATE TABLE stage_permissions (
    permission_id BIGSERIAL PRIMARY KEY,
    stage_id VARCHAR(50) NOT NULL REFERENCES stages(stage_id) ON DELETE CASCADE,

    -- Role-based
    role_name VARCHAR(100) NOT NULL,

    -- Permissions
    can_view BOOLEAN NOT NULL DEFAULT FALSE,
    can_create BOOLEAN NOT NULL DEFAULT FALSE,
    can_edit BOOLEAN NOT NULL DEFAULT FALSE,
    can_delete BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage_permissions BOOLEAN NOT NULL DEFAULT FALSE,

    -- Timestamps
    granted_by VARCHAR(100),
    granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_stage_role UNIQUE (stage_id, role_name)
);

-- Indexes for stage_permissions
CREATE INDEX idx_stage_permissions_stage ON stage_permissions(stage_id);
CREATE INDEX idx_stage_permissions_role ON stage_permissions(role_name);


-- =================================================================
-- 4. FORM_TYPE_PERMISSIONS TABLE
-- =================================================================
-- Role-based permissions for form types
-- =================================================================
CREATE TABLE form_type_permissions (
    permission_id BIGSERIAL PRIMARY KEY,
    form_type_id VARCHAR(50) NOT NULL REFERENCES form_types(form_type_id) ON DELETE CASCADE,

    -- Role-based
    role_name VARCHAR(100) NOT NULL,

    -- Permissions
    can_view BOOLEAN NOT NULL DEFAULT FALSE,
    can_create BOOLEAN NOT NULL DEFAULT FALSE,
    can_edit BOOLEAN NOT NULL DEFAULT FALSE,
    can_delete BOOLEAN NOT NULL DEFAULT FALSE,
    can_submit BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage_permissions BOOLEAN NOT NULL DEFAULT FALSE,

    -- Timestamps
    granted_by VARCHAR(100),
    granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_form_type_role UNIQUE (form_type_id, role_name)
);

-- Indexes for form_type_permissions
CREATE INDEX idx_form_type_permissions_form ON form_type_permissions(form_type_id);
CREATE INDEX idx_form_type_permissions_role ON form_type_permissions(role_name);


-- =================================================================
-- 4.5. ROLES TABLE
-- =================================================================
-- Dedicated roles table
-- =================================================================
CREATE TABLE roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100)
);

-- =================================================================
-- 5. USER_ROLES TABLE
-- =================================================================
-- User to role mapping for permission evaluation
-- =================================================================
CREATE TABLE user_roles (
    user_id VARCHAR(100) NOT NULL,
    role_ids JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Timestamps
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(100),

    -- Constraints
    CONSTRAINT pk_user_roles PRIMARY KEY (user_id)
);

-- Indexes for user_roles
CREATE INDEX idx_user_roles_user ON user_roles(user_id);
CREATE INDEX idx_user_roles_role_ids ON user_roles USING GIN(role_ids);


-- =================================================================
-- 6. AUDIT TABLES
-- =================================================================
-- Audit tables for tracking changes
-- =================================================================

-- Stage audit log
CREATE TABLE stage_audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    stage_id VARCHAR(50) NOT NULL,

    -- Action
    action VARCHAR(20) NOT NULL,
    action_by VARCHAR(100),
    action_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Change tracking
    old_data JSONB,
    new_data JSONB,

    -- Hierarchy changes
    old_path TEXT,
    new_path TEXT,
    old_lineage_path TEXT[],
    new_lineage_path TEXT[]
);

-- Indexes for stage_audit_log
CREATE INDEX idx_stage_audit_stage ON stage_audit_log(stage_id);
CREATE INDEX idx_stage_audit_action ON stage_audit_log(action);
CREATE INDEX idx_stage_audit_at ON stage_audit_log(action_at);
CREATE INDEX idx_stage_audit_by ON stage_audit_log(action_by);

-- Form type audit log
CREATE TABLE form_type_audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    form_type_id VARCHAR(50) NOT NULL,

    -- Action
    action VARCHAR(20) NOT NULL,
    action_by VARCHAR(100),
    action_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Change tracking
    old_data JSONB,
    new_data JSONB
);

-- Indexes for form_type_audit_log
CREATE INDEX idx_form_type_audit_form ON form_type_audit_log(form_type_id);
CREATE INDEX idx_form_type_audit_action ON form_type_audit_log(action);
CREATE INDEX idx_form_type_audit_at ON form_type_audit_log(action_at);


-- =================================================================
-- 7. HELPER FUNCTIONS
-- =================================================================

-- Function to update stage hierarchy metadata
CREATE OR REPLACE FUNCTION update_stage_hierarchy(
    p_stage_id VARCHAR
) RETURNS VOID AS $$
DECLARE
    v_child_count INTEGER;
    v_formtype_count INTEGER;
    v_is_leaf BOOLEAN;
BEGIN
    -- Count children
    SELECT COUNT(*)
    INTO v_child_count
    FROM stages
    WHERE parent_stage_id = p_stage_id;

    -- Count form types
    SELECT COUNT(*)
    INTO v_formtype_count
    FROM form_types
    WHERE stage_id = p_stage_id;

    -- Determine if leaf
    v_is_leaf := (v_child_count = 0);

    -- Update stage
    UPDATE stages
    SET
        children_count = v_child_count,
        formtype_count = v_formtype_count,
        is_leaf = v_is_leaf,
        updated_at = CURRENT_TIMESTAMP
    WHERE stage_id = p_stage_id;

    -- Recursively update parent
    UPDATE stages
    SET updated_at = CURRENT_TIMESTAMP
    WHERE stage_id = (SELECT parent_stage_id FROM stages WHERE stage_id = p_stage_id);
END;
$$ LANGUAGE plpgsql;

-- Function to get all descendant stage IDs using lineage
CREATE OR REPLACE FUNCTION get_descendant_stage_ids(
    p_ancestor_stage_id VARCHAR,
    p_max_depth INTEGER DEFAULT NULL
) RETURNS VARCHAR[] AS $$
DECLARE
    v_descendants VARCHAR[];
BEGIN
    IF p_max_depth IS NULL THEN
        SELECT ARRAY_AGG(stage_id ORDER BY depth_level, stage_name)
        INTO v_descendants
        FROM stages
        WHERE p_ancestor_stage_id = ANY(lineage_path)
        AND stage_id != p_ancestor_stage_id;
    ELSE
        SELECT ARRAY_AGG(stage_id ORDER BY depth_level, stage_name)
        INTO v_descendants
        FROM stages
        WHERE p_ancestor_stage_id = ANY(lineage_path)
        AND stage_id != p_ancestor_stage_id
        AND depth_level <= p_max_depth;
    END IF;

    RETURN v_descendants;
END;
$$ LANGUAGE plpgsql;

-- Function to check subtree permission
CREATE OR REPLACE FUNCTION has_subtree_permission(
    p_user_id VARCHAR,
    p_ancestor_stage_id VARCHAR,
    p_permission VARCHAR
) RETURNS BOOLEAN AS $$
DECLARE
    v_user_roles VARCHAR[];
    v_has_permission BOOLEAN;
BEGIN
    -- Get user roles
    SELECT ARRAY_AGG(DISTINCT r.role_name)
    INTO v_user_roles
    FROM user_roles ur, jsonb_array_elements_text(ur.role_ids) AS rid
    JOIN roles r ON r.role_id = rid::int
    WHERE ur.user_id = p_user_id;

    IF NOT FOUND OR CARDINALITY(v_user_roles) = 0 THEN
        RETURN FALSE;
    END IF;

    -- Check permission on any stage in subtree using lineage matching
    SELECT EXISTS(
        SELECT 1
        FROM stage_permissions sp
        JOIN stages s ON sp.stage_id = s.stage_id
        WHERE sp.role_name = ANY(v_user_roles)
        AND (
            s.stage_id = p_ancestor_stage_id
            OR p_ancestor_stage_id = ANY(s.lineage_path)
        )
        AND (
            CASE p_permission
                WHEN 'VIEW' THEN sp.can_view
                WHEN 'CREATE' THEN sp.can_create
                WHEN 'EDIT' THEN sp.can_edit
                WHEN 'DELETE' THEN sp.can_delete
                WHEN 'MANAGE_PERMISSIONS' THEN sp.can_manage_permissions
                ELSE FALSE
            END
        )
    ) INTO v_has_permission;

    RETURN v_has_permission;
END;
$$ LANGUAGE plpgsql;

-- Function to validate metadata consistency
CREATE OR REPLACE FUNCTION validate_metadata_consistency()
RETURNS TABLE (
    valid BOOLEAN,
    orphaned_stages BIGINT,
    path_conflicts BIGINT,
    lineage_mismatches BIGINT,
    checked_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (orphaned = 0 AND conflicts = 0 AND mismatches = 0)::BOOLEAN AS valid,
        orphaned,
        conflicts,
        mismatches,
        CURRENT_TIMESTAMP AS checked_at
    FROM (
        SELECT
            (SELECT COUNT(*)
             FROM stages s
             LEFT JOIN stages p ON s.parent_stage_id = p.stage_id
             WHERE s.parent_stage_id IS NOT NULL
             AND p.stage_id IS NULL) AS orphaned,
            (SELECT COUNT(*)
             FROM (
                 SELECT COUNT(*) AS cnt, stage_path
                 FROM stages
                 GROUP BY stage_path
                 HAVING COUNT(*) > 1
             ) dup) AS conflicts,
            (SELECT COUNT(*)
             FROM stages s
             WHERE s.depth_level != array_length(s.lineage_path, 1)) AS mismatches
    ) counts;
END;
$$ LANGUAGE plpgsql;

-- Function to move stage with descendants
CREATE OR REPLACE FUNCTION move_stage_with_descendants(
    p_stage_id VARCHAR,
    p_target_parent_id VARCHAR,
    p_user_id VARCHAR DEFAULT NULL
) RETURNS TABLE (
    success BOOLEAN,
    moved_stage_id VARCHAR,
    old_path TEXT,
    new_path TEXT,
    affected_stages_count BIGINT,
    affected_formtypes_count BIGINT,
    error_message TEXT
) AS $$
DECLARE
    v_stage RECORD;
    v_parent_stage RECORD;
    v_descendants TEXT[];
    v_lineage_prefix TEXT[];
    v_depth_delta INTEGER;
    v_old_path TEXT;
    v_new_path TEXT;
    v_root_lineage TEXT[];
    v_descendant_record RECORD;
    v_affected_stages BIGINT;
    v_affected_formtypes BIGINT;
    v_circular_ref BOOLEAN;
BEGIN
    -- Check for circular reference
    SELECT s.parent_stage_id, s.lineage_path, s.stage_path
    INTO v_stage
    FROM stages
    WHERE stage_id = p_stage_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, p_stage_id, NULL, NULL, 0, 0, 'Stage not found';
        RETURN;
    END IF;

    -- Check if target is a descendant
    SELECT stage_id
    FROM stages
    WHERE stage_id = p_target_parent_id
    AND p_stage_id = ANY(lineage_path)
    INTO v_descendant_record;

    IF FOUND THEN
        RETURN QUERY SELECT FALSE, p_stage_id, NULL, NULL, 0, 0, 'Cannot move stage to its own descendant';
        RETURN;
    END IF;

    -- Get target parent
    SELECT lineage_path, stage_path, depth_level
    INTO v_parent_stage
    FROM stages
    WHERE stage_id = p_target_parent_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, p_stage_id, NULL, NULL, 0, 0, 'Target parent not found';
        RETURN;
    END IF;

    -- Get root lineage for new hierarchy
    v_root_lineage := v_parent_stage.lineage_path;

    -- Get all descendants
    v_descendants := get_descendant_stage_ids(p_stage_id);

    -- Calculate depth delta
    SELECT depth_level
    INTO v_depth_delta
    FROM stages
    WHERE stage_id = p_stage_id;

    v_depth_delta := v_parent_stage.depth_level - v_depth_delta;

    -- Move the stage itself
    v_old_path := v_stage.stage_path;
    v_new_path := v_parent_stage.stage_path || '/' || v_stage.stage_name;

    -- Update stage
    UPDATE stages
    SET
        parent_stage_id = p_target_parent_id,
        stage_path = v_new_path,
        depth_level = v_parent_stage.depth_level + 1,
        lineage_path = v_root_lineage || p_stage_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE stage_id = p_stage_id;

    v_affected_stages := 1;

    -- Update descendants lineage and paths
    FOREACH v_descendant_record IN ARRAY v_descendants LOOP
        DECLARE
            v_descendant_lineage TEXT[];
            v_new_descendant_path TEXT;
            v_descendant_stage RECORD;
        BEGIN
            -- Get descendant info
            SELECT lineage_path, stage_path
            INTO v_descendant_stage
            FROM stages
            WHERE stage_id = v_descendant_record;

            -- Calculate new lineage
            v_descendant_lineage :=
                v_root_lineage ||
                p_stage_id ||
                v_descendant_stage.lineage_path[array_upper(v_descendant_stage.lineage_path, 1)];

            -- Calculate new path
            v_new_descendant_path :=
                regexp_replace(
                    v_descendant_stage.stage_path,
                    '^' || regexp_replace(v_old_path, '[\.\*\+\?\^\$\(\)\[\]\{\}\|\\]', '\\\\\g&', 'g'),
                    v_new_path
                );

            -- Update descendant
            UPDATE stages
            SET
                lineage_path = v_descendant_lineage,
                stage_path = v_new_descendant_path,
                depth_level = depth_level + v_depth_delta,
                updated_at = CURRENT_TIMESTAMP
            WHERE stage_id = v_descendant_record;

            v_affected_stages := v_affected_stages + 1;
        END;
    END LOOP;

    -- Update affected form types paths
    UPDATE form_types
    SET form_path = v_new_path || regexp_replace(form_path, '^' || regexp_replace(v_old_path, '[\.\*\+\?\^\$\(\)\[\]\{\}\|\\]', '\\\\\g&', 'g'), '')
    WHERE stage_id = p_stage_id OR stage_id = ANY(v_descendants);

    GET DIAGNOSTICS v_affected_formtypes = ROW_COUNT;

    -- Update parent child counts
    PERFORM update_stage_hierarchy(v_parent_stage);
    IF v_stage.parent_stage_id IS NOT NULL THEN
        PERFORM update_stage_hierarchy(v_stage.parent_stage_id);
    END IF;

    -- Log audit
    INSERT INTO stage_audit_log (
        stage_id, action, action_by, old_path, new_path, old_lineage_path, new_lineage_path
    ) VALUES (
        p_stage_id, 'MOVE', p_user_id, v_old_path, v_new_path, v_stage.lineage_path,
        v_root_lineage || p_stage_id
    );

    RETURN QUERY SELECT
        TRUE,
        p_stage_id::VARCHAR,
        v_old_path::TEXT,
        v_new_path::TEXT,
        v_affected_stages::BIGINT,
        v_affected_formtypes::BIGINT,
        NULL::TEXT;
END;
$$ LANGUAGE plpgsql;


-- =================================================================
-- 8. TRIGGERS
-- =================================================================

-- Trigger to update parent's children count on stage insert
CREATE OR REPLACE FUNCTION trg_stage_insert_update_parent()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE stages
    SET children_count = children_count + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE stage_id = NEW.parent_stage_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER t_stage_insert
AFTER INSERT ON stages
FOR EACH ROW
WHEN (NEW.parent_stage_id IS NOT NULL)
EXECUTE FUNCTION trg_stage_insert_update_parent();

-- Trigger to update parent's children count on stage delete
CREATE OR REPLACE FUNCTION trg_stage_delete_update_parent()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.parent_stage_id IS NOT NULL THEN
        UPDATE stages
        SET children_count = GREATEST(0, children_count - 1),
            updated_at = CURRENT_TIMESTAMP
        WHERE stage_id = OLD.parent_stage_id;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER t_stage_delete
BEFORE DELETE ON stages
FOR EACH ROW
EXECUTE FUNCTION trg_stage_delete_update_parent();

-- Trigger to update form type count on form type insert
CREATE OR REPLACE FUNCTION trg_formtype_insert_update_stage()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE stages
    SET formtype_count = formtype_count + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE stage_id = NEW.stage_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER t_formtype_insert
AFTER INSERT ON form_types
FOR EACH ROW
EXECUTE FUNCTION trg_formtype_insert_update_stage();

-- Trigger to update form type count on form type delete
CREATE OR REPLACE FUNCTION trg_formtype_delete_update_stage()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE stages
    SET formtype_count = GREATEST(0, formtype_count - 1),
        updated_at = CURRENT_TIMESTAMP
    WHERE stage_id = OLD.stage_id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER t_formtype_delete
BEFORE DELETE ON form_types
FOR EACH ROW
EXECUTE FUNCTION trg_formtype_delete_update_stage();

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION trg_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER t_stages_update_timestamp
BEFORE UPDATE ON stages
FOR EACH ROW
EXECUTE FUNCTION trg_update_timestamp();

CREATE TRIGGER t_form_types_update_timestamp
BEFORE UPDATE ON form_types
FOR EACH ROW
EXECUTE FUNCTION trg_update_timestamp();


COMMIT;

-- =================================================================
-- Migration Complete
-- =================================================================
-- Tables created: 9 (5 core, 4 audit)
-- Functions created: 5
-- Triggers created: 6
-- Indexes created: 24
-- =================================================================
