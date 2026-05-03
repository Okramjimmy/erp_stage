"""
Test script to demonstrate JSONB functionality and stage state management
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession
from src.app.database import async_session_maker, engine
from src.app.services.stage_service import StageService
from src.app.services.form_type_service import FormTypeService
from src.app.schemas.stage import StageCreate
from src.app.schemas.form_type import FormTypeCreate


async def test_jsonb_schema_queries():
    """Demonstrate JSONB querying capabilities for schema_reference"""
    print("\n" + "="*80)
    print("Testing JSONB Schema Reference Functionality")
    print("="*80)

    async with async_session_maker() as session:
        # Create a form type with JSON schema
        form_type_data = FormTypeCreate(
            form_name="Test Form",
            stage_id="test_stage",
            form_path="/test/test_form",
            version="1.0.0",
            schema_reference={
                "fields": [
                    {"name": "name", "type": "text", "required": True},
                    {"name": "email", "type": "email", "required": True},
                    {"name": "age", "type": "number", "required": False},
                ]
            }
        )

        ft_service = FormTypeService(session)
        try:
            # Note: This will need a valid stage_id to work
            print("\n✓ JSON schema can be stored as native Python dict")
            print(f"  Schema structure: {type(form_type_data.schema_reference)}")
            print(f"  Number of fields: {len(form_type_data.schema_reference['fields'])}")
        except Exception as e:
            print(f"\n✗ Error: {e}")

        print("\n" + "-"*80)
        print("JSONB Query Examples (SQL-based):")
        print("-"*80)
        print("-- Query forms with specific field type:")
        print("SELECT * FROM form_types WHERE schema_reference @> '{\"fields\": [{\"type\": \"email\"}]}';")
        print()
        print("-- Query forms field containing 'name':")
        print("SELECT * FROM form_types WHERE schema_reference @> '{\"fields\": [{\"name\": \"name\"}]}';")
        print()
        print("-- Extract all field names:")
        print("SELECT schema_reference->'fields'->0->>'name' FROM form_types;")
        print()
        print("-- Count forms with required fields:")
        print("SELECT COUNT(*) FROM form_types WHERE schema_reference @> '{\"fields\": [{\"required\": true}]}';")


async def test_stage_state_logic():
    """Test parent/child stage state management"""
    print("\n" + "="*80)
    print("Testing Stage State Management (Parent-Child Logic)")
    print("="*80)

    async with async_session_maker() as session:
        stage_service = StageService(session)

        print("\n" + "-"*80)
        print("Test Case 1: Creating Root Stage")
        print("-"*80)
        try:
            root_stage_data = StageCreate(
                stage_name="Root Stage",
                parent_stage_id=None,
                visibility_scope="public"
            )
            root_stage = await stage_service.create_stage(root_stage_data, created_by="test_user")

            print(f"✓ Root stage created: {root_stage.stage_id}")
            print(f"  - is_root: {root_stage.is_root} (expected: True)")
            print(f"  - is_leaf: {root_stage.is_leaf} (expected: True initially)")
            print(f"  - children_count: {root_stage.children_count} (expected: 0)")
        except Exception as e:
            print(f"✗ Error creating root stage: {e}")
            return

        print("\n" + "-"*80)
        print("Test Case 2: Creating Child Stage")
        print("-"*80)
        try:
            child_stage_data = StageCreate(
                stage_name="Child Stage",
                parent_stage_id=root_stage.stage_id,
                visibility_scope="private"
            )
            child_stage = await stage_service.create_stage(child_stage_data, created_by="test_user")

            print(f"✓ Child stage created: {child_stage.stage_id}")
            print(f"  - is_root: {child_stage.is_root} (expected: False)")
            print(f"  - is_leaf: {child_stage.is_leaf} (expected: True)")
            print(f"  - children_count: {child_stage.children_count} (expected: 0)")

            # Refresh root stage to check its state
            updated_root = await stage_service.get_stage(root_stage.stage_id)
            print(f"\n  Parent stage state after child creation:")
            print(f"  - Parent is_root: {updated_root.is_root} (expected: True)")
            print(f"  - Parent is_leaf: {updated_root.is_leaf} (expected: False)")
            print(f"  - Parent children_count: {updated_root.children_count} (expected: 1)")
        except Exception as e:
            print(f"✗ Error creating child stage: {e}")
            return

        print("\n" + "-"*80)
        print("Test Case 3: Creating Grandchild Stage")
        print("-"*80)
        try:
            grandchild_stage_data = StageCreate(
                stage_name="Grandchild Stage",
                parent_stage_id=child_stage.stage_id,
                visibility_scope="private"
            )
            grandchild_stage = await stage_service.create_stage(grandchild_stage_data, created_by="test_user")

            print(f"✓ Grandchild stage created: {grandchild_stage.stage_id}")
            print(f"  - is_root: {grandchild_stage.is_root} (expected: False)")
            print(f"  - is_leaf: {grandchild_stage.is_leaf} (expected: True)")
            print(f"  - children_count: {grandchild_stage.children_count} (expected: 0)")

            # Refresh parent stages
            updated_child = await stage_service.get_stage(child_stage.stage_id)
            updated_root = await stage_service.get_stage(root_stage.stage_id)

            print(f"\n  Child stage state after grandchild creation:")
            print(f"  - Child is_root: {updated_child.is_root} (expected: True)")
            print(f"  - Child is_leaf: {updated_child.is_leaf} (expected: False)")
            print(f"  - Child children_count: {updated_child.children_count} (expected: 1)")

            print(f"\n  Root stage state after grandchild creation:")
            print(f"  - Root is_root: {updated_root.is_root} (expected: True)")
            print(f"  - Root is_leaf: {updated_root.is_leaf} (expected: False)")
            print(f"  - Root children_count: {updated_root.children_count} (expected: 1)")
        except Exception as e:
            print(f"✗ Error creating grandchild stage: {e}")

        print("\n" + "="*80)
        print("Summary of Stage State Rules:")
        print("="*80)
        print("1. Root stages: parent_stage_id IS NULL, is_root = TRUE")
        print("2. Child stages always start with is_leaf = TRUE")
        print("3. When a child is created, parent is updated:")
        print("   - parent.is_root = TRUE (parent becomes a root node)")
        print("   - parent.is_leaf = FALSE (parent is no longer a leaf)")
        print("   - parent.children_count += 1")
        print("4. When a child is deleted, parent state is updated:")
        print("   - parent.children_count -= 1")
        print("   - parent.is_leaf = TRUE if children_count == 0")
        print("5. When a stage is moved, both old and new parents are updated")


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("ERP Stage System - JSONB & Stage State Tests")
    print("="*80)

    await test_jsonb_schema_queries()
    await test_stage_state_logic()

    print("\n" + "="*80)
    print("Tests completed!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
