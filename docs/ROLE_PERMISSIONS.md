# Role Permission Management

## Overview

The Role Permission Management system provides a Frappe-like interface for managing permissions across stages and form types. This system allows administrators to grant, revoke, and manage permissions for different roles in a hierarchical structure.

## Features

### Permission Types

#### Stage Permissions
- **View**: Can view the stage and its contents
- **Create**: Can create children stages and form types within this stage
- **Edit**: Can edit the stage properties
- **Delete**: Can delete the stage
- **Manage Permissions**: Can grant/revoke permissions on this stage

#### Form Type Permissions
- **View**: Can view the form type
- **Create**: Can create new form instances
- **Edit**: Can edit the form type schema
- **Delete**: Can delete the form type
- **Submit**: Can submit forms
- **Manage Permissions**: Can manage permissions on this form type

## Using the Permission Manager UI

### Accessing the Permission Page

Navigate to `/permissions` in your application to access the Role Permission Manager.

### Selecting a Role

1. **Existing Role**: Use the dropdown to select from existing roles that already have permissions configured
2. **New Role**: Type a new role name in the text input field to create permissions for a new role

### Managing Stage Permissions

1. Click on the "Stage Permissions" tab
2. View all stage permissions for the selected role
3. Use checkboxes to toggle permissions:
   - ✓ = Permission granted
   - ☐ = Permission not granted
4. Click **Save** to update individual permissions
5. Click **Revoke** to remove all permissions for a stage
6. Click **Add Stage Permission** to grant permissions for a new stage

### Managing Form Type Permissions

1. Click on the "Form Type Permissions" tab
2. View all form type permissions for the selected role
3. Use checkboxes to toggle permissions
4. Click **Save** to update individual permissions
5. Click **Add Form Type Permission** to grant permissions for a new form type

## API Endpoints

### List Stage Permissions
```http
GET /api/v1/permissions/stages?role_name={role_name}
```

### Grant Stage Permission
```http
POST /api/v1/permissions/stages/{stage_id}
Content-Type: application/json

{
  "role_name": "manager",
  "can_view": true,
  "can_create": true,
  "can_edit": true,
  "can_delete": false,
  "can_manage_permissions": false
}
```

### Revoke Stage Permission
```http
DELETE /api/v1/permissions/stages/{stage_id}/roles/{role_name}
```

### List Form Type Permissions
```http
GET /api/v1/permissions/form-types?role_name={role_name}
```

### Grant Form Type Permission
```http
POST /api/v1/permissions/form-types/{form_type_id}
Content-Type: application/json

{
  "role_name": "editor",
  "can_view": true,
  "can_create": true,
  "can_edit": true,
  "can_delete": false,
  "can_submit": true,
  "can_manage_permissions": false
}
```

### Get All Permissions for a Role
```http
GET /api/v1/permissions/roles/{role_name}
```

Response:
```json
{
  "role_name": "manager",
  "stage_permissions": [...],
  "form_type_permissions": [...],
  "all_roles": ["admin", "manager", "editor"]
}
```

## Hierarchical Permission System

### Lineage-Based Visibility

The permission system uses lineage-based visibility, which means:

1. **Direct Permissions**: Permissions granted directly on a stage/form type
2. **Inherited Permissions**: Users inherit permissions from ancestor stages

### Permission Inheritance Rules

- If a user has permission on a stage, they automatically have the same permission on all descendant stages
- This allows for efficient O(1) permission checks without recursion
- Permission checks use the lineage path stored in each stage

### Example

Given the following hierarchy:
```
/Company
  /Company/Departments
    /Company/Departments/Engineering
```

If a user has "View" permission on `/Company`:
- They can view `/Company`
- They can view `/Company/Departments` (inherited)
- They can view `/Company/Departments/Engineering` (inherited)

## User Role Assignment

### Assign Role to User
```http
POST /api/v1/permissions/users/roles
Content-Type: application/json

{
  "user_id": "john_doe",
  "role_name": "manager"
}
```

### Get User Roles
```http
GET /api/v1/permissions/users/{user_id}/roles
```

### Check User Permission
```http
GET /api/v1/permissions/users/{user_id}/check-stage/{stage_id}?permission_type=can_view
```

## Best Practices

1. **Role Naming Convention**: Use clear, descriptive role names (e.g., "admin", "manager", "editor", "viewer")
2. **Principle of Least Privilege**: Grant only the minimum required permissions
3. **Regular Audits**: Periodically review role permissions to ensure they align with business requirements
4. **Document Roles**: Maintain clear documentation of what each role can do
5. **Test Permissions**: Verify permissions work as expected before deploying to production

## Common Use Cases

### Creating a Manager Role
1. Select "manager" from the role dropdown or type "manager" in the new role field
2. Add stage permissions for the stages they should manage
3. Grant: View, Create, Edit (typically not Delete or Manage Permissions)
4. Add form type permissions as needed

### Creating a Viewer Role
1. Select "viewer" from the role dropdown or type "viewer" in the new role field
2. Add stage permissions with only "View" checked
3. Add form type permissions with only "View" checked

### Creating an Admin Role
1. Select "admin" from the role dropdown or type "admin" in the new role field
2. Grant all permissions on root stages
3. The lineage-based system will automatically grant permissions on all child stages

## Troubleshooting

### Permission Not Working
- Verify the user has the correct role assigned
- Check if the permission is granted on the specific stage/form type or its ancestors
- Use the "Check User Permission" endpoint to debug permission checks

### Cannot See Stages
- Ensure the user's role has at least "View" permission on the stage or one of its ancestors
- Check the user's role assignments

### Changes Not Reflected
- The system caches permissions for 15 minutes
- Wait for the cache to expire or restart the application

## Security Considerations

1. **Authentication Required**: All permission endpoints should be protected with authentication
2. **Authorization Checks**: Always verify the user has permission to manage permissions before allowing changes
3. **Audit Trail**: All permission changes are tracked with `granted_by` and `granted_at` timestamps
4. **Input Validation**: All inputs are validated via Pydantic schemas
5. **SQL Injection Protection**: SQLAlchemy ORM prevents SQL injection attacks