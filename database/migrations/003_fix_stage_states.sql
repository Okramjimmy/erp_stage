-- Migration: Fix stage root/leaf states
-- Description: Updates is_root and is_leaf flags to reflect actual hierarchy state
-- Created: 2026-05-02

-- Step 1: Mark all stages with no parent as root nodes
UPDATE stages
SET is_root = TRUE
WHERE parent_stage_id IS NULL;

-- Step 2: Mark all stages with children as non-leaf nodes
UPDATE stages
SET is_leaf = FALSE
WHERE stage_id IN (
    SELECT DISTINCT parent_stage_id
    FROM stages
    WHERE parent_stage_id IS NOT NULL
);

-- Step 3: Mark all stages without children as leaf nodes
UPDATE stages
SET is_leaf = TRUE
WHERE stage_id NOT IN (
    SELECT DISTINCT parent_stage_id
    FROM stages
    WHERE parent_stage_id IS NOT NULL
);

-- Step 4: Update children_count for all stages
UPDATE stages s
SET children_count = COALESCE(
    (SELECT COUNT(*)
     FROM stages c
     WHERE c.parent_stage_id = s.stage_id),
    0
);

-- Step 5: Verify the updates
SELECT
    'Stage state verification' as check_type,
    COUNT(*) FILTER (WHERE is_root = TRUE) as root_stages,
    COUNT(*) FILTER (WHERE is_leaf = TRUE) as leaf_stages,
    COUNT(*) FILTER (WHERE is_root = FALSE AND is_leaf = FALSE) as intermediate_stages,
    COUNT(*) FILTER (WHERE children_count > 0) as stages_with_children,
    SUM(children_count) as total_children_count
FROM stages;

-- Step 6: Check for any inconsistencies
SELECT
    'Inconsistency check' as check_type,
    s.stage_id,
    s.stage_name,
    s.is_root,
    s.is_leaf,
    s.children_count
FROM stages s
WHERE
    -- Leaf stages should have 0 children
    (s.is_leaf = TRUE AND s.children_count > 0)
    OR
    -- Non-leaf stages should have children
    (s.is_leaf = FALSE AND s.children_count = 0)
    OR
    -- Root stages should have no parent
    (s.is_root = TRUE AND s.parent_stage_id IS NOT NULL)
    OR
    -- Non-root stages should have a parent
    (s.is_root = FALSE AND s.parent_stage_id IS NULL);

-- Expected results:
-- - The second query should return 0 rows (no inconsistencies)
-- - Root stages should have parent_stage_id IS NULL
-- - Leaf stages should have children_count = 0
-- - Non-leaf stages should have children_count > 0
