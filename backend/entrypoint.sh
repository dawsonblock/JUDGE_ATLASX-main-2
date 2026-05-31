#!/bin/sh
set -e

echo "Waiting for database connection..."
python3 - <<'PY'
import os, sys, time
from sqlalchemy import create_engine
url = os.environ.get('JTA_DATABASE_URL')
if not url:
    print('JTA_DATABASE_URL not set, skipping wait.')
    sys.exit(0)
for i in range(30):
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            print('Database connection successful!')
            sys.exit(0)
    except (ImportError, ModuleNotFoundError) as e:
        print(f'FATAL: Database driver missing or invalid configuration: {e}')
        sys.exit(1)
    except Exception as e:
        print(f"Database connection failed. Retrying in 2 seconds ({i+1}/30)...")
        time.sleep(2)
print('FATAL: Database did not become ready in time.')
sys.exit(1)
PY

echo "Running Alembic migrations..."
alembic upgrade head || { echo "FATAL: alembic upgrade head failed — aborting startup"; exit 1; }

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

