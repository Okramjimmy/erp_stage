-- Migration: Convert schema_reference from Text to JSONB
-- This migration improves query performance and enables JSON operations
-- Description: Changes the schema_reference column from Text type to JSONB type
-- Created: 2026-05-02

-- Step 1: Create a GIN index on schema_reference for better JSON query performance
CREATE INDEX IF NOT EXISTS idx_form_types_schema_reference
    ON form_types
    USING GIN (schema_reference);

-- Step 2: Alter the column type to JSONB
-- This automatically converts existing valid JSON strings to JSONB format
ALTER TABLE form_types
    ALTER COLUMN schema_reference
    TYPE JSONB
    USING schema_reference::jsonb;

-- Step 3: Add comment to document the change
COMMENT ON COLUMN form_types.schema_reference IS
    'JSON-formatted schema definition stored as JSONB for optimized querying and indexing';

-- Step 4: Verify the migration
-- This query checks that the conversion was successful
SELECT
    'Migration completed: schema_reference converted to JSONB' as status,
    COUNT(*) as total_form_types,
    COUNT(schema_reference) as forms_with_schema
FROM form_types;

-- Benefits of this migration:
-- 1. Better query performance with GIN indexing
-- 2. Ability to query JSON fields directly in SQL
-- 3. More efficient storage (binary format vs text)
-- 4. Support for partial JSON updates
-- 5. Data validation at database level
