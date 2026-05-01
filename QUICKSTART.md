# ERP Stage Builder - Quick Start Guide

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+ (optional, for caching)
- Docker & Docker Compose (optional)

### Installation

#### 1. Clone and Setup Environment

```bash
cd /Users/okrammeitei/Developer/erp_stage

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### 2. Database Setup

**Option A: Using Docker (Recommended)**

```bash
# Start PostgreSQL and Redis using Docker
docker-compose up -d

# Wait for services to be ready
docker-compose ps
```

**Option B: Using Local PostgreSQL**

```sql
-- Create database
CREATE DATABASE erp_stage;

-- Create user
CREATE USER postgres WITH PASSWORD 'postgres';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE erp_stage TO postgres;
```

#### 3. Environment Configuration

Create a `.env` file in the project root:

```bash
# Application
APP_NAME=ERP Stage Builder
APP_VERSION=1.0.0
DEBUG=True
SECRET_KEY=your-secret-key-change-in-production

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/erp_stage
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=erp_stage
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# CORS
CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000"]
```

#### 4. Initialize Database

```bash
# Run database migrations
cd database/migrations
psql -U postgres -d erp_stage -f 001_initial_schema.sql

# Or using the application's init_db (on first run)
```

### Running the Application

#### Development Mode

```bash
# From project root
cd src

# Run with uvicorn
python main.py

# Or using uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### Production Mode

```bash
# Using gunicorn with uvicorn workers
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

### Access the Application

- **API Root**: http://localhost:8000/
- **API Documentation (Swagger)**: http://localhost:8000/docs
- **Alternative Documentation (ReDoc)**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 📚 API Endpoints

### Stage Management

- `POST /api/v1/stages` - Create a new stage
- `GET /api/v1/stages` - List all stages (paginated)
- `GET /api/v1/stages/tree` - Get hierarchical stage tree
- `GET /api/v1/stages/search` - Search stages by name
- `GET /api/v1/stages/{stage_id}` - Get specific stage
- `PUT /api/v1/stages/{stage_id}` - Update a stage
- `POST /api/v1/stages/{stage_id}/move` - Move stage to new parent
- `DELETE /api/v1/stages/{stage_id}` - Delete a stage

### Form Type Management

- `POST /api/v1/form-types` - Create a new form type
- `GET /api/v1/form-types` - List all form types (paginated)
- `GET /api/v1/form-types/search` - Search form types by name
- `GET /api/v1/form-types/stage/{stage_id}` - Get form types by stage
- `GET /api/v1/form-types/{form_type_id}` - Get specific form type
- `GET /api/v1/form-types/{form_type_id}/schema` - Get form type with schema
- `PUT /api/v1/form-types/{form_type_id}` - Update a form type
- `DELETE /api/v1/form-types/{form_type_id}` - Delete a form type

### Permission Management

- `POST /api/v1/permissions/stages/{stage_id}` - Grant stage permission
- `DELETE /api/v1/permissions/stages/{stage_id}/roles/{role_name}` - Revoke permission
- `POST /api/v1/permissions/form-types/{form_type_id}` - Grant form type permission
- `POST /api/v1/permissions/users/roles` - Assign role to user
- `GET /api/v1/permissions/users/{user_id}/roles` - Get user roles
- `GET /api/v1/permissions/users/{user_id}/accessible-stages` - Get accessible stages
- `GET /api/v1/permissions/users/{user_id}/check-stage/{stage_id}` - Check permission

### Metadata Management

- `GET /api/v1/metadata/master` - Get master metadata tree
- `GET /api/v1/metadata/registry` - Get flat metadata registry
- `GET /api/v1/metadata/stages/{stage_id}` - Get stage metadata
- `POST /api/v1/metadata/regenerate` - Regenerate all metadata
- `GET /api/v1/metadata/validate` - Validate metadata consistency
- `GET /api/v1/metadata/statistics` - Get system statistics

## 🧪 Testing

### Run Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest

# Run with coverage
pytest --cov=src/app --cov-report=html

# Run specific test file
pytest tests/test_stage_service.py -v
```

### Example Test Cases

See `tests/` directory for comprehensive test suites including:
- Unit tests for services
- Integration tests for API endpoints
- Performance tests for lineage-based queries
- Load tests for stage movement operations

## 🔧 Development

### Code Formatting

```bash
# Format code with black
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking
mypy src/
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## 📊 Performance Optimization

### Redis Caching

The application uses Redis for caching with the following TTLs:
- Master metadata: 1 hour
- Stage paths: 24 hours
- User visible stages: 15 minutes
- Permission cache: 30 minutes

### Database Indexes

Key indexes for performance:
- `lineage_path` GIN index for subtree queries
- `stage_path` unique index for path lookups
- `parent_stage_id` for parent-child navigation
- `depth_level` for depth-based filtering

## 🐳 Docker Deployment

### Using Docker Compose

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose down

# Reset everything
docker-compose down -v
```

### Dockerfile

Create a `Dockerfile` in the project root:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY database/ ./database/

WORKDIR /app/src

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 🔒 Security Considerations

1. **Authentication**: Add JWT/OAuth2 authentication middleware
2. **Authorization**: Use the permission system for access control
3. **Input Validation**: All inputs validated via Pydantic schemas
4. **SQL Injection**: Protected via SQLAlchemy parameterized queries
5. **CORS**: Configure allowed origins in settings
6. **Secrets**: Use environment variables for sensitive data

## 📈 Monitoring

### Health Check Endpoint

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "cache": "connected"
}
```

### Metrics to Monitor

- API latency (p99 < 100ms)
- Database query duration (p95 < 50ms)
- Cache hit rate (> 95%)
- Stage count and average depth
- Permission check latency

## 🐛 Troubleshooting

### Common Issues

**Database Connection Error**
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check connection
psql -U postgres -d erp_stage -c "SELECT 1"
```

**Redis Connection Error**
```bash
# Check Redis is running
docker-compose ps redis

# Test connection
redis-cli ping
```

**Import Errors**
```bash
# Ensure you're in the src directory
cd src

# Or set PYTHONPATH
export PYTHONPATH=/Users/okrammeitei/Developer/erp_stage/src:$PYTHONPATH
```

## 📝 Example Usage

### Create a Stage Hierarchy

```python
import httpx

# Create root stage
response = httpx.post("http://localhost:8000/api/v1/stages", json={
    "stage_name": "Recruitment",
    "visibility_scope": "public"
})
root_stage = response.json()
print(f"Root stage ID: {root_stage['stage_id']}")

# Create child stage
response = httpx.post("http://localhost:8000/api/v1/stages", json={
    "stage_name": "Applications",
    "parent_stage_id": root_stage['stage_id'],
    "visibility_scope": "private"
})
child_stage = response.json()
print(f"Child stage ID: {child_stage['stage_id']}")

# Create form type
response = httpx.post("http://localhost:8000/api/v1/form-types", json={
    "form_name": "Application Form",
    "stage_id": child_stage['stage_id'],
    "version": "1.0.0",
    "schema": {
        "fields": [
            {
                "field_id": "name",
                "field_label": "Full Name",
                "field_type": "text",
                "required": True
            },
            {
                "field_id": "email",
                "field_label": "Email Address",
                "field_type": "email",
                "required": True
            }
        ]
    }
})
form_type = response.json()
print(f"Form type ID: {form_type['form_type_id']}")

# Get stage tree
response = httpx.get("http://localhost:8000/api/v1/stages/tree")
tree = response.json()
print(f"Stage tree: {tree}")
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## 📄 License

MIT License - See LICENSE file for details