# Depth Level and Path Validation Improvements

## Overview

This update addresses two critical edge cases in the stage hierarchy management system:

1. **Preventing Root Stages (Depth 0) from Moving to Their Children**
2. **Validating New Root Stage Creation and Path Conflict Resolution**

## Problem Statement

### Issue 1: Root Stages Moving to Descendants
Previously, the system allowed root stages (depth level 0) to be moved to their own descendants, which creates logical inconsistencies in the hierarchy. A root stage with children should not be able to move into its own subtree.

### Issue 2: Path Conflicts at Root Level
When creating new root stages (depth 0), the system needed proper validation to prevent duplicate root-level stage names and ensure path integrity across the entire hierarchy.

## Solutions Implemented

### 1. Root Stage Movement Prevention

**File**: `src/app/services/stage_service.py`

**Enhanced Validation Logic**:
```python
# Check for circular reference - prevent any stage from moving to its own descendant
if target_parent_id in stage.lineage_path:
    raise ValueError(f"Cannot move stage '{stage.stage_name}' to its own descendant '{target_parent.stage_name}'")

# NEW: Prevent root stages (depth 0) from moving to their descendants
if stage.depth_level == 0:
    # Get all descendants of this root stage
    root_descendants_result = await self.db.execute(
        select(Stage).where(Stage.lineage_path.contains([stage.stage_id]))
    )
    root_descendants = [d.stage_id for d in root_descendants_result.scalars().all()]
    
    # Check if target parent is a descendant of this root stage
    if target_parent_id in root_descendants:
        raise ValueError(f"Cannot move root stage '{stage.stage_name}' to its descendant '{target_parent.stage_name}'. Root stages cannot be moved within their own subtree.")
```

**Key Points**:
- Root stages (depth 0) have empty `lineage_path`, so they require special checking
- We query all descendants using `Stage.lineage_path.contains([stage.stage_id])`
- Any attempt to move a root stage into its subtree is prevented
- Clear error messages help users understand the constraint

### 2. New Root Stage Creation Validation

**File**: `src/app/services/stage_service.py`

**Enhanced Path Conflict Checking**:
```python
# Check for path conflicts - this also handles root stage creation
existing = await self.db.execute(
    select(Stage).where(Stage.stage_path == stage_path)
)
if existing.scalar_one_or_none():
    raise ValueError(f"Stage path '{stage_path}' already exists. A stage with the name '{stage_data.stage_name}' already exists at this location in the hierarchy.")

# Additional validation: Check if stage_name would conflict at the root level
if not parent_stage:
    # For root stages, ensure we're not creating a duplicate root-level name
    root_path_conflict = await self.db.execute(
        select(Stage).where(
            Stage.stage_path == f"/{stage_data.stage_name}")
    )
    if root_path_conflict.scalar_one_or_none():
        raise ValueError(f"A root-level stage named '{stage_data.stage_name}' already exists. Root-stage names must be unique.")
```

**Key Points**:
- Root stages always have paths like `"/ProjectName"` with depth 0
- Duplicate root-level names are prevented
- Same names can exist under different parents (different paths)
- Clear error messages indicate the exact conflict

## Behavior Examples

### Example 1: Root Stage Moving Prevention

**Scenario**:
```
RootProject (depth: 0)
├── Child1 (depth: 1)
│   └── Grandchild1 (depth: 2)
└── Child2 (depth: 1)
```

**Attempted Move 1**: Move RootProject to Child1
```
Result: ✗ Error - "Cannot move root stage 'RootProject' to its descendant 'Child1'. Root stages cannot be moved within their own subtree."
```

**Attempted Move 2**: Move RootProject to Grandchild1
```
Result: ✗ Error - "Cannot move root stage 'RootProject' to its descendant 'Grandchild1'. Root stages cannot be moved within their own subtree."
```

**Valid Move**: Move Child1 to Child2
```
Result: ✓ Success - Non-root stages can move within the hierarchy (with circular reference checks)
```

### Example 2: New Root Stage Creation

**Scenario**: Existing root stages
```
/projectA (root, depth: 0)
/projectB (root, depth: 0)
```

**Attempt 1**: Create root with new name
```
POST /api/v1/stages
{
  "stage_name": "ProjectC",
  "parent_stage_id": null
}

Result: ✓ Success
ProjectC path: /ProjectC (depth: 0)
```

**Attempt 2**: Create root with duplicate name
```
POST /api/v1/stages
{
  "stage_name": "ProjectA",
  "parent_stage_id": null
}

Result: ✗ Error - "A root-level stage named 'ProjectA' already exists. Root-stage names must be unique."
```

**Attempt 3**: Create child under ProjectA
```
POST /api/v1/stages
{
  "stage_name": "Module1",
  "parent_stage_id": "projectA_id"
}

Result: ✓ Success
Module1 path: /ProjectA/Module1 (depth: 1)
```

**Attempt 4**: Create child with same name under ProjectB
```
POST /api/v1/stages
{
  "stage_name": "Module1",
  "parent_stage_id": "projectB_id"
}

Result: ✓ Success
Module1 path: /ProjectB/Module1 (depth: 1)
```

## Path Structure and Rules

### Path Construction Rules

1. **Root Stages**: `/{stage_name}` with `depth_level = 0`
2. **Child Stages**: `{parent_path}/{stage_name}` with `depth_level = parent_depth + 1`
3. **No two stages can have the same path**

### Example Hierarchy with Paths

```
/ProjectA (depth: 0)
├── /ProjectA/Module1 (depth: 1)
│   ├── /ProjectA/Module1/SubModule1 (depth: 2)
│   └── /ProjectA/Module1/SubModule2 (depth: 2)
└── /ProjectA/Module2 (depth: 1)

/ProjectB (depth: 0)
└── /ProjectB/Module1 (depth: 1)  // Same name as ProjectA/Module1, different path
```

### Depth Level Properties

- **Depth 0**: Root stages, no parent
- **Depth 1-...**: Child stages with clear parent hierarchy
- **Depth increases by 1** for each level down in the tree
- **Depth decreases appropriately** when stages move up the tree

## Testing

### Test Coverage

**File**: `test_stage_depth_and_path_validations.py`

#### Test 1: Root Stage Moving Prevention
- ✓ Prevents root moving to immediate child
- ✓ Prevents root moving to grandchild
- ✓ Prevents root moving to any descendant
- ✓ Clear error messages for failed moves

#### Test 2: New Root Stage Creation
- ✓ Creates first root stage successfully
- ✓ Creates multiple root stages with different names
- ✓ Prevents duplicate root names
- ✓ Allows same names under different parents
- ✓ Maintains path integrity

#### Test 3: Path Integrity
- ✓ Verifies correct path construction
- ✓ Ensures depth levels are accurate
- ✓ Validates hierarchical relationships
- ✓ Tests path updates during moves

### Running Tests

```bash
# Navigate to project directory
cd /home/mangal/Projects/erp_stage

# Run the validation tests
python test_stage_depth_and_path_validations.py
```

## Error Messages

### Root Stage Move Errors

1. **Moving to Direct Child**:
   ```
   Cannot move root stage '{root_name}' to its descendant '{child_name}'. 
   Root stages cannot be moved within their own subtree.
   ```

2. **Moving to Any Descendant**:
   ```
   Cannot move stage '{stage_name}' to its own descendant '{descendant_name}'.
   ```

3. **Self-Move Attempt**:
   ```
   Cannot move stage to itself
   ```

### Path Conflict Errors

1. **Duplicate Path**:
   ```
   Stage path '/Path/To/Stage' already exists. 
   A stage with the name 'StageName' already exists at this location in the hierarchy.
   ```

2. **Duplicate Root Name**:
   ```
   A root-level stage named '{stage_name}' already exists. 
   Root-stage names must be unique.
   ```

## Benefits

### 1. Data Integrity
- Prevents logical inconsistencies in the hierarchy
- Ensures root stages remain at depth 0
- Maintains clear parent-child relationships

### 2. User Experience
- Clear, actionable error messages
- Prevents confusing state changes
- Validates inputs before database updates

### 3. System Robustness
- Self-healing validation logic
- Comprehensive edge case handling
- Database-level consistency checks

### 4. Maintenance
- Well-documented behavior
- Comprehensive test coverage
- Easy to understand and modify

## Migration Notes

### No Database Changes Required
This update only adds validation logic - no schema modifications are needed.

### Backward Compatibility
- Existing hierarchies remain unchanged
- New validation applies to future operations
- No data migration required

### API Impact
- Same endpoints, same request/response format
- Additional validation may return new error messages
- Client applications should handle ValueError exceptions

## Performance Considerations

### Root Stage Move Validation
- **Query**: 1 additional query to get descendants for root stages
- **Impact**: Minimal - only executed for depth 0 stages
- **Optimization**: Could add index on `lineage_path` if performance issues arise

### Path Conflict Checking
- **Query**: 2 queries (general path + root-specific)
- **Impact**: Negligible - uses indexed `stage_path` field
- **Optimization**: Already optimized with unique constraint on `stage_path`

## Future Enhancements

### Potential Improvements

1. **Batch Path Updates**: If moving a root stage's path could update entire subtree
2. **Path Renaming**: Allow changing stage names with automatic descendant path updates
3. **Path Normalization**: Ensure consistent path formatting (trailing slashes, etc.)
4. **Path Validation API**: Dedicated endpoint to validate potential moves before execution

### Advanced Features

1. **Path Search**: API to search stages by path patterns
2. **Path History**: Track path changes over time
3. **Path Permissions**: Control who can move stages at certain depths
4. **Path Export/Import**: Maintain path structure during data transfers

## Conclusion

This update significantly improves the reliability and usability of the stage hierarchy management system by:

1. ✅ Preventing root stages from moving to their descendants
2. ✅ Properly validating new root stage creation
3. ✅ Maintaining path integrity across all operations
4. ✅ Providing clear, actionable error messages

The implementation is robust, well-tested, and maintains backward compatibility while adding essential validation logic.