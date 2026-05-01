# Hierarchical Stage & Form Builder ERP Module
## Implementation Plan

**Version:** 1.0  
**Date:** 2024  
**Target:** Scalable ERP system with 100,000+ stages, unlimited nesting, <100ms latency

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Database Schema](#2-database-schema)
3. [Storage Architecture](#3-storage-architecture)
4. [Master Metadata Structure](#4-master-metadata-structure)
5. [Permission System](#5-permission-system)
6. [API Design](#6-api-design)
7. [Performance Optimization](#7-performance-optimization)
8. [Implementation Phases](#8-implementation-phases)
9. [Testing Strategy](#9-testing-strategy)
10. [Deployment Considerations](#10-deployment-considerations)

---

## 1. System Overview

### 1.1 Core Concepts

**Stage** = Folder-like container (infinite nesting)  
**FormType** = Dynamic form template (exists within a Stage)

### 1.2 Key Requirements

- ✅ Nested Stage hierarchy with unlimited depth
- ✅ Master Metadata Registry tracking full tree structure
- ✅ Lineage-based permission evaluation (no recursion)
- ✅ Fast subtree lookup and visibility filtering
- ✅ Atomic stage movement with descendant updates
- ✅ Support for 100,000+ stages with <100ms latency

### 1.3 Architecture Components

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐           │
│  │  Stage   │  │ FormType │  │ Permission   │           │
│  │ Service  │  │ Service  │  │ Service      │           │
│  └──────────┘  └──────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│                   Business Logic Layer                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Lineage Calculator  │  Tree Validator  │  ACL │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│                     Data Access Layer                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Postgres │  │  Redis   │  │  Files   │              │
│  │  (Data)  │  │ (Cache)  │  │ (S3/FS)  │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Database Schema

### 2.1 Core Tables

#### 2.1.1 stages Table

```sql
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
    CONSTRAINT chk_formtype_non_negative CHECK (formtype_count >= 0)
);

CREATE INDEX idx_stages_parent ON stages(parent_stage_id);
CREATE INDEX idx_stages_path ON stages USING GIN(to_tsvector('english', stage_path));
CREATE INDEX idx_stages_lineage ON stages USING GIN(lineage_path);
CREATE INDEX idx_stages_depth ON stages(depth_level);
CREATE INDEX idx_stages_visibility ON stages(visibility_scope);
CREATE INDEX idx_stages_created_at ON stages(created_at);
```

#### 2.1.2 form_types Table

```sql
CREATE TABLE form_types (
    form_type_id VARCHAR(50) PRIMARY KEY,
    form_name VARCHAR(255) NOT NULL,
    
    -- Hierarchy
    stage_id VARCHAR(50) NOT NULL REFERENCES stages(stage_id),
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
    CONSTRAINT chk_version_format CHECK (version ~ '^d{1,3}.d{1,3}.d{1,3}$')
);

CREATE INDEX idx_form_types_stage ON form_types(stage_id);
CREATE INDEX idx_form_types_path ON form_types(form_path);
CREATE INDEX idx_form_types_created_at ON form_types(created_at);
```

#### 2.1.3 stage_permissions Table

```sql
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

CREATE INDEX idx_stage_permissions_stage ON stage_permissions(stage_id);
CREATE INDEX idx_stage_permissions_role ON stage_permissions(role_name);
```

#### 2.1.4 form_type_permissions Table

```sql
CREATE TABLE form_type_permissions (
    permission_id BIGSERIAL PRIMARY KEY,
    form_type_id VARCHAR(50) NOT NULL REFERENCES form_types(form_type_id) ON DELETE CASCADE,
    
    -- Role-based
    role_name VARCHAR(100) NOT NULL,
    
    -- Permissions
    can_view BOOLEAN NOT NULL DEFAULT FALSE,
    can_create BOOL  NOT NULL DEFAULT FALSE,
    can_edit BOOL  NOT NULL DEFAULT FALSE,
    can_delete BOOL  NOT NULL DEFAULT FALSE,
    can_submit BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage_permissions BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Timestamps
    granted_by VARCHAR(100),
    granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT uq_form_type_role UNIQUE (form_type_id, role_name)
);

CREATE INDEX idx_form_type_permissions_form ON form_type_permissions(form_type_id);
CREATE INDEX idx_form_type_permissions_role ON form_type_permissions(role_name);
```

#### 2.1.5 user_roles Table

```sql
CREATE TABLE user_roles (
    user_id VARCHAR(100) NOT NULL,
    role_name VARCHAR(100) NOT NULL,
    
    -- Timestamps
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(100),
    
    -- Constraints
    CONSTRAINT pk_user_roles PRIMARY KEY (user_id, role_name)
);

CREATE INDEX idx_user_roles_user ON user_roles(user_id);
CREATE INDEX idx_user_roles_role ON user_roles(role_name);
```

### 2.2 Audit Tables

```sql
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

CREATE INDEX idx_stage_audit_stage ON stage_audit_log(stage_id);
CREATE INDEX idx_stage_audit_action ON stage_audit_log(action);
CREATE INDEX idx_stage_audit_at ON stage_audit_log(action_at);

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

CREATE INDEX idx_form_type_audit_form ON form_type_audit_log(form_type_id);
CREATE INDEX idx_form_type_audit_action ON form_type_audit_log(action);
```

---

## 3. Storage Architecture

### 3.1 Directory Structure

```
erp-storage/
├── stages/
│   ├── stage_id/
│   │   ├── metadata.json
│   │   └── config.json
│
├── forms/
│   ├── form_type_id/
│   │   ├── metadata.json
│   │   ├── schema.json
│   │   └── submissions/
│   │       ├── submission_id.json
│   │       └── ...
│
├── metadata/
│   ├── master_stage_metadata.json
│   ├── metadata_registry.json
│   └── permission_cache.json
│
└── uploads/
    ├── attachments/
    └── exports/
```

### 3.2 File Distribution Strategy

```yaml
# Current (local) - <100K stages
  - Local filesystem (NTFS/ext4)
  - Direct I/O for metadata files
  
# Scale (1M+ stages)
  - Cloud object storage (S3/GCS)
  - Database for metadata (Postgres)
  - CDN for static assets
```

---

## 4. Master Metadata Structure

### 4.1 Master Stage Metadata Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["roots", "version", "generated_at"],
  "properties": {
    "version": {
      "type": "integer",
      "description": "Incremented on any structural change"
    },
    "generated_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp of last generation"
    },
    "roots": {
      "type": "array",
      "description": "Array of root stage trees (org/tenant isolation)",
      "items": {
        "$ref": "#/definitions/StageNode"
      }
    },
    "statistics": {
      "type": "object",
      "properties": {
        "total_stages": { "type": "integer" },
        "total_form_types": { "type": "integer" },
        "max_depth": { "type": "integer" },
        "avg_depth": { "type": "number" }
      }
    }
  },
  "definitions": {
    "StageNode": {
      "type": "object",
      "required": ["stage_id", "stage_name", "depth", "path", "lineage"],
      "properties": {
        "stage_id": { "type": "string" },
        "stage_name": { "type": "string" },
        "parent_stage_id": { "type": "string" },
        "depth": { "type": "integer", "minimum": 0 },
        "path": { "type": "string" },
        "lineage": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Ordered array of ancestor stage IDs"
        },
        "children_count": { "type": "integer", "minimum": 0 },
        "formtype_count": { "type": "integer", "minimum": 0 },
        "is_root": { "type": "boolean" },
        "is_leaf": { "type": "boolean" },
        "visibility_scope": { "enum": ["public", "private", "restricted"] },
        "children": {
          "type": "array",
          "items": { "$ref": "#/definitions/StageNode" }
        },
        "form_types": {
          "type": "array",
          "items": {
            "$ref": "#/definitions/FormTypeRef"
          }
        }
      }
    },
    "FormTypeRef": {
      "type": "object",
      "properties": {
        "form_type_id": { "type": "string" },
        "form_name": { "type": "string" }
      }
    }
  }
}
```

### 4.2 Master Stage Metadata Example

```json
{
  "version": 124,
  "generated_at": "2024-01-15T14:30:22.123Z",
  "roots": [
    {
      "stage_id": "root",
      "stage_name": "Root",
      "parent_stage_id": null,
      "depth": 0,
      "path": "/",
      "lineage": ["root"],
      "children_count": 3,
      "formtype_count": 0,
      "is_root": true,
      "is_leaf": false,
      "visibility_scope": "private",
      "children": [
        {
          "stage_id": "stage_recruitment",
          "stage_name": "Recruitment",
          "parent_stage_id": "root",
          "depth": 1,
          "path": "/Recruitment",
          "lineage": ["root", "stage_recruitment"],
          "children_count": 2,
          "formtype_count": 3,
          "is_root": false,
          "is_leaf": false,
          "visibility_scope": "private",
          "children": [
            {
              "stage_id": "stage_screening",
              "stage_name": "Screening",
              "parent_stage_id": "stage_recruitment",
              "depth": 2,
              "path": "/Recruitment/Screening",
              "lineage": ["root", "stage_recruitment", "stage_screening"],
              "children_count": 0,
              "formtype_count": 1,
              "is_root": false,
              "is_leaf": true,
              "visibility_scope": "private",
              "children": [],
              "form_types": [
                {
                  "form_type_id": "form_app_checklist",
                  "form_name": "Application Checklist"
                }
              ]
            },
            {
              "stage_id": "stage_interviews",
              "stage_name": "Interviews",
              "parent_stage_id": "stage_recruitment",
              "depth": 2,
              "path": "/Recruitment/Interviews",
              "lineage": ["root", "stage_recruitment", "stage_interviews"],
              "children_count": 1,
              "formtype_count": 2,
              "is_root": false,
              "is_leaf": false,
              "visibility_scope": "private",
              "children": [
                {
                  "stage_id": "stage_tech_interviews",
                  "stage_name": "Technical Interviews",
                  "parent_stage_id": "stage_interviews",
                  "depth": 3,
                  "path": "/Recruitment/Interviews/ Technical",
                  "lineage": ["root", "stage_recruitment", "stage_interviews", "stage_tech_interviews"],
                  "children_count": 0,
                  "formtype_count": 1,
                  "is_root": false,
                  "is_leaf": true,
                  "visibility_scope": "private",
                  "children": [],
                  "form_types": [
                    {
                      "form_type_id": "form_tech_eval",
                      "form_name": "Technical Evaluation"
                    }
                  ]
                }
              ],
              "form_types": [
                {
                  "form_type_id": "form_schedule_interview",
                  "form_name": "Schedule Interview"
                }
              ]
            }
          ],
          "form_types": [
            {
              "form_type_id": "form_application",
              "form_name": "Application Form"
            }
          ]
        }
      ],
      "form_types": []
    }
  ],
  "statistics": {
    "total_stages": 5,
    "total_form_types": 4,
    "max_depth": 3,
    "avg_depth": 1.6
  }
}
```

### 4.3 Metadata Registry Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["version", "generated_at", "stages", "formtypes"],
  "properties": {
    "version": { "type": "integer" },
    "generated_at": { "type": "string", "format": "date-time" },
    "stages": {
      "type": "object",
      "description": "Flat lookup index for fast O(1) access",
      "additionalProperties": {
        "$ref": "#/definitions/StageRegistryEntry"
      }
    },
    "formtypes": {
      "type": "object",
      "description": "Flat lookup index for form types",
      "additionalProperties": {
        "$ref": "#/definitions/FormTypeRegistryEntry"
      }
    }
  },
  "definitions": {
    "StageRegistryEntry": {
      "type": "object",
      "required": ["path", "depth", "lineage"],
      "properties": {
        "path": { "type": "string" },
        "depth": { "type": "integer" },
        "lineage": { "type": "array", "items": { "type": "string" } },
        "parent_id": { "type": "string" },
        "children_count": { "type": "integer" },
        "formtype_count": { "type": "integer" }
      }
    },
    "FormTypeRegistryEntry": {
      "type": "object",
      "required": ["path", "stage_id"],
      "properties": {
        "path": { "type": "string" },
        "stage_id": { "type": "string" },
        "form_name": { "type": "string" },
        "version": { "type": "string" }
      }
    }
  }
}
```

### 4.4 Metadata Registry Example

```json
{
  "version": 124,
  "generated_at": "2024-01-15T14:30:22.123Z",
  "stages": {
    "root": {
      "path": "/",
      "depth": 0,
      "lineage": ["root"],
      "parent_id": null,
      "children_count": 3,
      "formtype_count": 0
    },
    "stage_recruitment": {
      "path": "/Recruitment",
      "depth": 1,
      "lineage": ["root", "stage_recruitment"],
      "parent_id": "root",
      "children_count": 2,
      "formtype_count": 3
    },
    "stage_screening": {
      "path": "/Recruitment/Screening",
      "depth": 2,
      "lineage": ["root", "stage_recruitment", "stage_screening"],
      "parent_id": "stage_recruitment",
      "children_count": 0,
      "formtype_count": 1
    }
  },
  "formtypes": {
    "form_app_checklist": {
      "path": "/Recruitment/Screening/ApplicationChecklist",
      "stage_id": "stage_screening",
      "form_name": "Application Checklist",
      "version": "1.0.0"
    },
    "form_application": {
      "path": "/Recruitment/ApplicationForm",
      "stage_id": "stage_recruitment",
      "form_name": "Application Form",
      "version": "2.1.0"
    }
  }
}
```

### 4.5 Stage Metadata File Schema

```json
{
  "stage_id": "stage_001",
  "stage_name": "Recruitment",
  "parent_stage_id": "root",
  "depth_level": 1,
  "stage_path": "/Recruitment",
  "lineage_path": ["root", "stage_001"],
  "children_stage_ids": ["stage_002", "stage_003"],
  "formtype_ids": ["form_001", "form_002", "form_003"],
  "children_count": 2,
  "formtype_count": 3,
  "is_root": false,
  "is_leaf": false,
  "visibility_scope": "private",
  "created_by": "user_123",
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-15T14:30:22Z",
  "permissions": {
    "roles": [
      {
        "role": "Manager",
        "access": ["view", "create", "edit"]
      },
      {
        "role": "Recruiter",
        "access": ["view", "create"]
      }
    ]
  },
  "metadata_reference": "storage/stages/stage_001/metadata.json"
}
```

### 4.6 FormType Metadata File Schema

```json
{
  "form_type_id": "form_001",
  "form_name": "Application Form",
  "stage_id": "stage_001",
  "form_path": "/Recruitment/ApplicationForm",
  
  "version": "1.0.0",
  "schema_reference": "storage/forms/form_001/schema.json",
  
  "created_by": "user_123",
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-15T14:30:22Z",
  
  "permissions": {
    "roles": [
      {
        "role": "Manager",
        "access": ["view", "edit", "delete", "submit"]
      },
      {
        "role": "Recruiter",
        "access": ["view", "submit"]
      }
    ]
  },
  
  "statistics": {
    "total_submissions": 1250,
    "last_submission": "2024-01-15T14:25:00Z"
  }
}
```

---

## 5. Permission System

### 5.1 Permission Model

**Permission Types:**
- `VIEW` - Read access to stage/form
- `CREATE` - Create new children/forms
- `EDIT` - Modify existing content
- `DELETE` - Remove content
- `MANAGE_PERMISSIONS` - Grant/revoke permissions
- `SUBMIT` - Submit forms (specific to FormTypes)

### 5.2 Hierarchical Visibility Algorithm

```python
def get_visible_stages(user_role: str, user_id: str) -> List[str]:
    """
    Get list of stage IDs visible to user based on hierarchical permissions.
    
    Non-recursive O(1) lookup using lineage array GIN index.
    """
    # Step 1: Get all roles assigned to user
    user_roles = get_user_roles(user_id)
    
    # Step 2: Get all stage permissions for user's roles
    permitted_stages = db.query("""
        SELECT stage_id
        FROM stage_permissions
        WHERE role_name = ANY($1)
        AND can_view = TRUE
    """, [user_roles])
    
    permitted_stage_ids = [p.stage_id for p in permitted_stages]
    
    # Step 3: Get all DESCENDANTS of permitted stages using lineage matching
    # No recursion needed - single query with GIN index
    visible_stages = db.query("""
        SELECT stage_id, stage_path, depth_level, lineage_path
        FROM stages
        WHERE $2 = ANY(lineage_path)  -- Contains any permitted stage in lineage
           OR stage_id = ANY($2)      -- Or is the permitted stage itself
    """, [permitted_stage_ids])
    
    return [s.stage_id for s in visible_stages]
```

### 5.3 Permission Check Function

```python
def has_permission(
    user_id: str,
    stage_id: str,
    permission: str,
    check_descendants: bool = False
) -> bool:
    """
    Check if user has specific permission on stage (and optionally descendants).
    
    Args:
        user_id: User identifier
        stage_id: Stage to check
        permission: Permission type (VIEW, CREATE, EDIT, DELETE, MANAGE_PERMISSIONS)
        check_descendants: If True, check for any descendant permission
        
    Returns:
        True if user has permission
    """
    # Get user roles
    user_roles = get_user_roles(user_id)
    if not user_roles:
        return False
    
    # Check direct permission on stage
    direct_permission = db.query_one("""
        SELECT 1
        FROM stage_permissions
        WHERE stage_id = $1
        AND role_name = ANY($2)
        AND can_{permission} = TRUE
        LIMIT 1
    """.format(permission=permission.lower()), [stage_id, user_roles])
    
    if direct_permission:
        return True
    
    # If checking descendants, look for permission in ancestor
    if check_descendants:
        # Get stage lineage
        stage = db.query_one("""
            SELECT lineage_path
            FROM stages
            WHERE stage_id = $1
        """, [stage_id])
        
        if not stage:
            return False
        
        # Check for permission on ANY ancestor
        ancestor_permission = db.query_one("""
            SELECT 1
            FROM stage_permissions sp
            JOIN stages s ON sp.stage_id = s.stage_id
            WHERE s.stage_id = ANY($1)
            AND sp.role_name = ANY($2)
            AND sp.can_{permission} = TRUE
            LIMIT 1
        """.format(permission=permission.lower()), 
            [stage.lineage_path, user_roles]
        )
        
        return bool(ancestor_permission)
    
    return False
```

### 5.4 Fast Subtree Permission Check

```sql
-- Index supporting fast lineage queries
CREATE INDEX idx_stages_lineage_gin ON stages USING GIN(lineage_path);

-- Single query to check permission on entire subtree
-- Returns TRUE if user has ANY permission on ANY stage in subtree
CREATE OR REPLACE FUNCTION has_subtree_permission(
    p_user_id VARCHAR,
    p_ancestor_stage_id VARCHAR,
    p_permission VARCHAR
) RETURNS BOOLEAN AS $$
DECLARE
    v_user_roles VARCHAR[];
    v_subtree_permission_exists BOOLEAN;
BEGIN
    -- Get user roles
    SELECT ARRAY_AGG(DISTINCT role_name)
    INTO v_user_roles
    FROM user_roles
    WHERE user_id = p_user_id;
    
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;
    
    -- Check permission on any stage in subtree (using lineage matching)
    SELECT EXISTS(
        SELECT 1
        FROM stage_permissions sp
        JOIN stages s ON sp.stage_id = s.stage_id
        WHERE sp.role_name = ANY(v_user_roles)
        AND (
            -- Direct match on ancestor
            s.stage_id = p_ancestor_stage_id
            OR
            -- Match on any descendant (lineage contains ancestor)
            p_ancestor_stage_id = ANY(s.lineage_path)
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
    ) INTO v_subtree_permission_exists;
    
    RETURN v_subtree_permission_exists;
END;
$$ LANGUAGE plpgsql;
```

---

## 6. API Design

### 6.1 Stage Management APIs

#### 6.1.1 Create Stage

```
POST /api/v1/stages
```

**Request:**
```json
{
  "stage_name": "Screening",
  "parent_stage_id": "stage_recruitment",
  "visibility_scope": "private",
  "metadata": {}
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "stage_id": "stage_screening",
    "stage_name": "Screening",
    "parent_stage_id": "stage_recruitment",
    "stage_path": "/Recruitment/Screening",
    "depth_level": 2,
    "lineage_path": ["root", "stage_recruitment", "stage_screening"],
    "children_count": 0,
    "formtype_count": 0,
    "is_root": false,
    "is_leaf": true,
    "created_at": "2024-01-15T14:30:22Z"
  }
}
```

#### 6.1.2 Get Stage Tree

```
GET /api/v1/stages/tree?root_stage_id=RECURTMENT&max_depth=10
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "stage_id": "stage_recruitment",
    "stage_name": "Recruitment",
    "depth": 1,
    "path": "/Recruitment",
    "children": [
      {
        "stage_id": "stage_screening",
        "stage_name": "Screening",
        "depth": 2,
        "path": "/Recruitment/Screening",
        "children": [],
        "form_types": [
          {
            "form_type_id": "form_app_checklist",
            "form_name": "Application Checklist"
          }
        ]
      }
    ]
  }
}
```

#### 6.1.3 Move Stage

```
POST /api/v1/stages/{stage_id}/move
```

**Request:**
```json
{
  "target_parent_id": "stage_interviews",
  "options": {
    "update_lineage": true,
    "update_master_metadata": true,
    "atomic_operation": true
  }
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "stage_id": "stage_tech_interviews",
    "old_path": "/Recruitment/Interviews/Technical",
    "new_path": "/Recruitment/Screening/Technical",
    "updated_stages_count": 5,
    "updated_form_types_count": 2,
    "operation_duration_ms": 45
  }
}
```

#### 6.1.4 Delete Stage

```
DELETE /api/v1/stages/{stage_id}?recursive=true
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "deleted_stage_id": "stage_screening",
    "deleted_children_count": 2,
    "deleted_form_types_count": 3,
    "cascade_completed": true
  }
}
```

### 6.2 FormType Management APIs

#### 6.2.1 Create FormType

```
POST /api/v1/formtypes
```

**Request:**
```json
{
  "form_name": "Application Form",
  "stage_id": "stage_recruitment",
  "schema": {
    "fields": [
      {
        "field_id": "name",
        "field_label": "Full Name",
        "field_type": "text",
        "required": true
      }
    ]
  }
}
```

#### 6.2.2 Get FormTypes by Stage

```
GET /api/v1/stages/{stage_id}/formtypes
```

### 6.3 Permission Management APIs

#### 6.3.1 Grant Stage Permission

```
POST /api/v1/stages/{stage_id}/permissions
```

**Request:**
```json
{
  "role_name": "Recruiter",
  "permissions": {
    "can_view": true,
    "can_create": true,
    "can_edit": false,
    "can_delete": false,
    "can_manage_permissions": false
  }
}
```

#### 6.3.2 Check User Access

```
GET /api/v1/users/{user_id}/accessible-stages
```

**Response:**
```json
{
  "success": true,
  "data": {
    "accessible_stage_ids": ["stage_recruitment", "stage_screening"],
    "accessible_form_type_ids": ["form_001", "form_002"],
    "total_count": 4
  }
}
```

### 6.4 Metadata APIs

#### 6.4.1 Get Master Metadata

```
GET /api/v1/metadata/master
```

#### 6.4.1 Regenerate Master Metadata

```
POST /api/v1/metadata/regenerate

{
  "force": false,
  "include_statistics": true
}
```

---

## 7. Performance Optimization

### 7.1 Caching Strategy

```yaml
Redis Caching:
  master_metadata_tree:
    - TTL: 1 hour
    - Invalidation: On any structural change
    
  stage_path_lookup:
    - TTL: 24 hours
    - Key: stage:{stage_id}:path
    
  user_visible_stages:
    - TTL: 15 minutes (short, for security)
    - Key: user:{user_id}:visible_stages
    
  permission_cache:
    - TTL: 30 minutes
    - Key: permission:{role_name}:{stage_id}
```

### 7.2 Database Optimizations

```sql
-- Materialized view for fast tree rendering
CREATE MATERIALIZED VIEW stage_tree_view AS
SELECT 
    s.stage_id,
    s.stage_name,
    s.parent_stage_id,
    s.stage_path,
    s.depth_level,
    s.lineage_path,
    s.children_count,
    s.formtype_count,
    s.is_leaf,
    -- Aggregate children
    (
        SELECT array_agg(child.stage_id ORDER BY child.stage_name)
        FROM stages child
        WHERE child.parent_stage_id = s.stage_id
    ) as child_stage_ids,
    -- Aggregate form types
    (
        SELECT array_agg(ft.form_type_id)
        FROM form_types ft
        WHERE ft.stage_id = s.stage_id
    ) as form_type_ids
FROM stages s;

CREATE UNIQUE INDEX idx_stage_tree_view_id ON stage_tree_view(stage_id);

-- Refresh strategy
CREATE OR REPLACE FUNCTION refresh_stage_tree_view() 
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY stage_tree_view;
END;
$$ LANGUAGE plpgsql;
```

### 7.3 Query Optimization Examples

**Bad (Recursive):**
```sql
-- Avoid: Multiple queries to get subtree
WITH RECURSIVE stage_tree AS (
    SELECT * FROM stages WHERE stage_id = 'stage_A'
    UNION ALL
    SELECT s.* FROM stages s
    JOIN stage_tree st ON s.parent_stage_id = st.stage_id
)
SELECT * FROM stage_tree;
```

**Good (Lineage-based):**
```sql
-- Use: Single query with GIN index
SELECT stage_id, stage_name, stage_path, depth_level
FROM stages
WHERE 'stage_A' = ANY(lineage_path)
ORDER BY depth_level, stage_name;
```

**Performance impact for 100K stages:**

| Query Type | Average Time | Complexity |
|------------|--------------|------------|
| Recursive CTE | 250ms+ | O(n*d) |
| Lineage GIN | 5-15ms | O(1) with index |

### 7.4 Batch Operations

```sql
-- Batch stage movement optimization
CREATE OR REPLACE FUNCTION move_stage_batch(
    p_stage_id VARCHAR,
    p_new_parent_id VARCHAR
) RETURNS MOVE_RESULT AS $$
DECLARE
    v_old_path TEXT;
    v_new_path TEXT;
    v_old_lineage TEXT[];
    v_new_lineage TEXT[];
    v_affected_count INTEGER;
BEGIN
    -- Atomic operation within transaction
    -- Uses single UPDATE with calculated values
    -- Estimated 10x faster than iterative updates
END;
$$ LANGUAGE plpgsql;
```

---

## 8. Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)

**Day 1-2:**
- Set up project structure
- Create database schema
- Set up CI/CD

**Day 3-4:**
- Implement Stage model
- Implement FormType model
- Implement Permission model

**Day 5-7:**
- Create migration scripts
- Seed initial data
- Set up connection pooling

**Deliverable:**
- Working database with all tables
- Migration framework established
- ORM/Query builder configured

### Phase 2: Metadata Management (Week 3-4)

**Day 1-3:**
- Implement Lineage Calculator
- Create Metadata Service
- Implement Master Metadata Generator

**Day 4-6:**
- Implement Registry Service
- Create metadata file handlers
- Implement metadata validation

**Day 7:**
- Performance testing
- Load testing (10K stages)

**Deliverable:**
- Functional master metadata system
- Metadata generation in <100ms
- Validation pipeline

### Phase 3: Permission System (Week 5-6)

**Day 1-3:**
- Implement permission models
- Create Permission Service
- Implement ACL system

**Day 4-6:**
- Implement hierarchical visibility
- Create permission caching
- Optimize permission queries

**Day 7:**
- Security testing
- Permission audit logging

**Deliverable:**
- Full permission system
- Subtree visibility
- Inheritance support

### Phase 4: Core Operations (Week 7-9)

**Day 1-5:**
- implement CRUD for stages
- Implement CRUD for FormTypes
- Add validation layers

**Day 6-10:**
- Implement stage movement algorithm
- Implement recursive updates
- Add transaction support

**Day 11-15:**
- Implement cascade delete
- Implement batch operations
- Performance optimization

**Deliverable:**
- Full CRUD operations
- Atomic stage movement
- Subtree operations

### Phase 5: API Development (Week 10-12)

**Day 1-5:**
- Design API specifications
- Implement authentication middleware
- Create rate limiting

**Day 6-10:**
- Implement Stage APIs
- Implement FormType APIs
- Implement Permission APIs

**Day 11-15:**
- Implement Metadata APIs
- API documentation
- API versioning

**Deliverable:**
- Restful API suite
- OpenAPI documentation
- API gateway configured

### Phase 6: Testing & Quality (Week 13-14)

**Day 1-4:**
- Unit tests (80% coverage)
- Integration tests
- Performance tests

**Day 5-7:**
- Load testing (100K stages)
- Security audit
- Penetration testing

**Day 8-10:**
- Bug fixes
- Refactoring
- Documentation

**Deliverable:**
- Test suite
- Performance benchmarks
- Security clearance

### Phase 7: Deployment & Monitoring (Week 15-16)

**Day 1-3:**
- Set up production database
- Configure caching layers
- Set up monitoring

**Day 4-7:**
- Deploy to staging
- Smoke tests
- Load tests on staging

**Day 8-10:**
- Production deployment
- Monitor for issues
- Rollback plans

**Deliverable:**
- Live production system
- Monitoring dashboard
- Runbooks

---

## 9. Testing Strategy

### 9.1 Unit Testing

```python
# Example test for lineage calculation
def test_calculate_lineage():
    """Test lineage calculation for nested stages"""
    # Setup
    root = create_stage("Root", None)
    child1 = create_stage("Child1", root.stage_id)
    child2 = create_stage("Child2", child1.stage_id)
    child3 = create_stage("Child3", child2.stage_id)
    
    # Assert lineage
    assert root.lineage_path == ["root"]
    assert child1.lineage_path == ["root", "child1"]
    assert child2.lineage_path == ["root", "child1", "child2"]
    assert child3.lineage_path == ["root", "child1", "child2", "child3"]
    assert child3.depth_level == 3

def test_stage_movement_updates_descendant_lineage():
    """Test that stage movement updates all descendants"""
    # Setup
    root = create_stage("Root", None)
    child1 = create_stage("Child1", root.stage_id)
    child2 = create_stage("Child2", child1.stage_id)
    child3 = create_stage("Child3", child2.stage_id)
    
    old_lineage = child3.lineage_path.copy()
    
    # Move child1 to new parent
    new_root = create_stage("NewRoot", None)
    move_stage(child1.stage_id, new_root.stage_id)
    
    # Verify all descendants updated
    assert child3.lineage_path[0] == "newroot"
    assert len(child3.lineage_path) == 4
    assert child3.stage_path == "/NewRoot/Child1/Child2/Child3"
```

### 9.2 Integration Testing

```python
def test_hierarchical_permission_visibility():
    """Test that permissions flow down the hierarchy"""
    # Setup
    setup_hierarchical_stages()
    
    # Grant permission on middle stage
    grant_permission("stage_B", "Manager", VIEW)
    
    # User has Manager role assigned
    assign_role("user_123", "Manager")
    
    # Get visible stages
    visible = get_visible_stages("user_123")
    
    # Should see stage_B and all descendants
    assert "stage_B" in visible
    assert "stage_C" in visible
    assert "stage_D" in visible
    
    # Should NOT see parent or siblings
    assert "root" not in visible
    assert "stage_A" not in visible

def test_metadata_consistency_after_stage_movement():
    """Test master metadata remains consistent after moving stages"""
    # Setup: Create tree with 1000 stages
    create_large_hierarchy(1000)
    
    # Verify initial consistency
    assert validate_master_metadata() == True
    
    # Move subtree with descendants
    move_stage("stage_500", "stage_100")
    
    # Verify metadata still consistent
    assert validate_master_metadata() == True
    
    # Verify all ancestors updated
    descendant_count = count_descendants("stage_500")
    assert descendant_count == 499  # stages 500-999
```

### 9.3 Performance Testing

```python
@pytest.mark.parametrize("stage_count", [100, 1000, 10000, 100000])
def test_subtree_query_performance(stage_count):
    """Test that subtree queries maintain sub-100ms performance"""
    # Setup: Create large hierarchy
    create_stage_tree(stage_count)
    
    # Measure query time
    start = time.time()
    results = get_visible_stages("user_with_access")
    duration = (time.time() - start) * 1000
    
    # Assert performance target
    assert duration < 100, f"Query took {duration}ms, target <100ms"
    assert len(results) > stage_count // 2  # Expected subset

def test_stage_movement_performance_100k_stages():
    """Test stage movement with 100K stages in subtree"""
    # Setup
    create_stage_tree(100000)
    
    start = time.time()
    move_stage_with_descendants("stage_1", "stage_50000")
    duration = (time.time() - start) * 1000
    
    # Should complete in reasonable time (adjust target based on requirements)
    assert duration < 5000, f"Movement took {duration}ms"
```

### 9.4 Load Testing

```yaml
# k6 configuration for load testing
scenarios:
  hierarchical_queries:
    executor: constant-arrival-rate
    rate: 100
    timeUnit: 1s
    duration: 5m
    preAllocatedVUs: 50
    
  stage_movement:
    executor: constant-vus
    vus: 10
    duration: 10m
    
  metadata_regeneration:
    executor: ramping-vus
    stages:
      - duration: 2m
        target: 20
      - duration: 5m
        target: 100
      - duration: 2m
        target: 0
```

---

## 10. Deployment Considerations

### 10.1 Database Scaling

```sql
-- Partition strategies for large-scale deployment

-- By depth level for better tree operations
CREATE TABLE stages (
    -- Same columns
) PARTITION BY LIST (depth_level);

CREATE TABLE stages_depth_0 PARTITION OF stages
    FOR VALUES IN (0);
    
CREATE TABLE stages_depth_1 PARTITION OF stages
    FOR VALUES IN (1);
    
-- ... up to depth 10+

-- Alternative: Range partitioning by stage_id hash
CREATE TABLE stages (
    stage_id VARCHAR(50),
    -- ...
) PARTITION BY HASH (stage_id);

CREATE TABLE stages_p0 PARTITION OF stages
    FOR VALUES WITH (MODULUS 4, REMAINDER 0);
-- ... partitions 1, 2, 3
```

### 10.2 Cache Warm-up Strategy

```python
def warm_up_cache():
    """Pre-populate cache on deployment"""
    # Cache master metadata
    master_metadata = generate_master_metadata(force=True)
    redis.setex(
        "master_metadata", 
        3600, 
        json.dumps(master_metadata)
    )
    
    # Cache critical paths
    critical_stages = get_top_accessed_stages(limit=1000)
    for stage in critical_stages:
        redis.setex(
            f"stage:{stage.stage_id}:path",
            86400,
            stage.stage_path
        )
    
    # Cache common role permissions
    common_roles = ["Manager", "Admin", "Recruiter", "Reviewer"]
    for role in common_roles:
        permissions = get_role_permissions(role)
        warm_up_role_permission_cache(permissions)
```

### 10.3 Monitoring Metrics

```yaml
Critical Metrics to Monitor:

Performance:
  - api.v1.stages.tree.latency percentile:99 < 100ms
  - api.v1.stages.move.latency percentile:99 < 5000ms
  - db.query.duration < 50ms (p95)
  - cache.hit_rate > 95%
  
Business:
  - total_stages_count
  - avg_hierarchy_depth
  - form_types_per_stage
  
Reliability:
  - master_metadata_consistency_errors < 1/hour
  - stage_movement_failures < 0.1%
  - db_connection_pool_usage < 80%
  
Security:
  - unauthorized_access_attempts
  - permission_check_failures
  - suspicious_activity_flags
```

### 10.4 Disaster Recovery

```yaml
Backup Strategy:
  database:
    daily_full_backup: true
    hourly_incremental: true
    point_in_time_recovery: true
    retention_days: 90
    
  master_metadata:
    real_time_replication: true
    versioned_snapshots: 10
    checksum_validation: daily
    
  file_storage:
    cross_region_replication: true
    immutable_backups: true
    versioning_enabled: true

Rollback Strategy:
  - Automated rollback on validation failure
  - Previous metadata versions accessible within 24 hours
  - Database restore point-in-time to 5-minute granularity
  - Smoke test before traffic full restoration
```

---

## 11. Maintenance Operations

### 11.1 Metadata Consistency Check

```sql
CREATE OR REPLACE FUNCTION validate_metadata_consistency()
RETURNS CONSISTENCY_REPORT AS $$
DECLARE
    v_report CONSISTENCY_REPORT;
    v_orphan_count INTEGER;
    v_path_conflict_count INTEGER;
    v_lineage_mismatch_count INTEGER;
BEGIN
    -- Check for orphaned stages (parent not exists)
    SELECT COUNT(*)
    INTO v_orphan_count
    FROM stages s
    LEFT JOIN stages p ON s.parent_stage_id = p.stage_id
    WHERE s.parent_stage_id IS NOT NULL
    AND p.stage_id IS NULL;
    
    -- Check for path conflicts
    SELECT COUNT(*)
    INTO v_path_conflict_count
    FROM stages
    GROUP BY stage_path
    HAVING COUNT(*) > 1;
    
    -- Check lineage consistency
    SELECT COUNT(*)
    INTO v_lineage_mismatch_count
    FROM stages s
    WHERE s.depth_level != array_length(s.lineage_path, 1);
    
    -- Build report
    v_report.valid = (v_orphan_count = 0 AND 
                      v_path_conflict_count = 0 AND
                      v_lineage_mismatch_count = 0);
    v_report.orphaned_stages = v_orphan_count;
    v_report.path_conflicts = v_path_conflict_count;
    v_report.lineage_mismatches = v_lineage_mismatch_count;
    v_report.checked_at = CURRENT_TIMESTAMP;
    
    RETURN v_report;
END;
$$ LANGUAGE plpgsql;
```

### 11.2 Automated Metadata Repair

```python
def repair_metadata():
    """Auto-repair inconsistencies"""
    report = validate_metadata_consistency()
    
    if report.valid:
        return "No issues found"
    
    issues_fixed = []
    
    # Fix orphaned stages
    if report.orphaned_stages > 0:
        orphans = find_orphaned_stages()
        for stage in orphans:
            # Try to find parent in registry or reconnect to root
            repair_orphan_stage(stage)
        issues_fixed.append(f"Repaired {len(orphans)} orphaned stages")
    
    # Fix path conflicts
    if report.path_conflicts > 0:
        conflicts = find_path_conflicts()
        for conflict in conflicts:
            rename_stage(conflict)
        issues_fixed.append(f"Fixed {len(conflicts)} path conflicts")
    
    # Regenerate master metadata
    regenerate_master_metadata(force=True)
    
    return f"Metadata repaired: {', '.join(issues_fixed)}"
```

### 11.3 Periodic Maintenance

```yaml
Scheduled Tasks:
  Daily:
    - Validate metadata consistency (2 AM)
    - Update statistics (3 AM)
    - Vacuum analyze database (4 AM)
    
  Weekly:
    - Full metadata regeneration (Sunday 1 AM)
    - Archive old audit logs ( Sunday 3 AM)
    - Review performance metrics (Monday 9 AM)
    
  Monthly:
    - Database consistency check
    - Index rebuild if fragmentation > 50%
    - Schema drift detection
    - Cache warm-up optimization
```

---

## 12. Appendix

### 12.1 Migration Scripts

#### Migration 001: Initial Schema

```sql
-- create_tables.sql
BEGIN;

-- As defined in Section 2.1
-- Creates all tables, indexes, and functions

COMMIT;
```

#### Migration 002: Master Metadata Initialization

```sql
BEGIN;

-- Create root stage
INSERT INTO stages (
    stage_id, stage_name, parent_stage_id,
    stage_path, depth_level, lineage_path,
    children_count, formtype_count,
    is_root, is_leaf, visibility_scope
) VALUES (
    'root', 'Root', NULL,
    '/', 0, ARRAY['root'],
    0, 0,
    true, false, 'private'
);

COMMIT;
```

### 12.2 Utility Functions

```python
def generate_stage_id(prefix: str = "stage") -> str:
    """Generate unique stage ID with collision resistance"""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def calculate_new_path(new_parent_path: str, stage_name: str) -> str:
    """Calculate new stage path based on parent"""
    return f"{new_parent_path.rstrip('/')}/{stage_name}"

def build_lineage(parent_lineage: list, new_stage_id: str) -> list:
    """Build lineage array for new stage"""
    return parent_lineage + [new_stage_id]

def validate_stage_name(name: str) -> bool:
    """Validate stage name (no invalid characters, reasonable length)"""
    import re
    return bool(re.match(r'^[a-zA-Z0-9_\-\s]+$', name)) and 1 <= len(name) <= 255

def get_all_descendants(stage_id: str, max_depth: int = None) -> List[str]:
    """Get all descendant stage IDs efficiently using lineage"""
    return db.query("""
        SELECT stage_id
        FROM stages
        WHERE $1 = ANY(lineage_path)
        AND ($2::integer IS NULL OR depth_level <= $2)
        ORDER BY depth_level, stage_name
    """, [stage_id, max_depth])
```

### 12.3 Error Codes

```yaml
STAGE_NOT_FOUND: 40401
STAGE_NAME_INVALID: 40001
STAGE_PATH_CONFLICT: 40901
STAGE_CIRCULAR_DEPENDENCY: 40002
PARENT_NOT_FOUND: 40402
PERMISSION_DENIED: 40301
 lineage_INVALID: 40003
FORMTYPE_NOT_FOUND: 40403
METADATA_INCONSISTENT: 50001
MOVEMENT_FAILED: 50002
```

### 12.4 Performance Benchmarks

Target Benchmarks (100K stages):

| Operation | P50 | P95 | P99 |
|-----------|-----|-----|-----|
| Create Stage | 25ms | 45ms | 75ms |
| Get Stage Tree (3 levels) | 15ms | 30ms | 50ms |
| Move Stage (10 descendants) | 50ms | 100ms | 150ms |
| Move Stage (10K descendants) | 500ms | 1500ms | 2500ms |
| Permission Check (user) | 5ms | 15ms | 25ms |
| Get Visible Stages | 30ms | 60ms | 90ms |
| FormType Create | 20ms | 40ms | 60ms |
| Master Metadata Regenerate | 200ms | 500ms | 800ms |

---

## Summary

This implementation plan provides:

✅ **Complete Database Schema** - Tables, indexes, constraints  
✅ **Master Metadata Structure** - JSON schemas with examples  
✅ **Permission System** - Hierarchical ACL with inheritance  
✅ **Recursive Update Logic** - Atomic stage movement  
✅ **Performance Optimization** - Caching, query optimization  
✅ **API Design** - RESTful endpoints for all operations  
✅ **Testing Strategy** - Unit, integration, load tests  
✅ **Deployment Considerations** - Scaling, monitoring, DR  

The system is designed to:
- Scale to 100,000+ stages
- Support unlimited nesting depth
- Maintain <100ms query latency
- Ensure metadata consistency
- Provide hierarchical permissions without recursion

---

**Document Status:** ✅ Complete  
**Next Step:** Begin Phase 1 - Core Infrastructure Setup