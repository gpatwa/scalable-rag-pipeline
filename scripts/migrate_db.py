# scripts/migrate_db.py
# This is a wrapper around the Alembic CLI.
# Setup:
# 1. pip install alembic
# 2. alembic init migrations
# 3. Edit alembic.ini to point to your DB URL
# 4. Edit migrations/env.py to import your models

import os
import subprocess
from services.api.app.config import settings

def run_migrations():
    """
    Applies Alembic migrations to the database.
    """
    print("Running database migrations...")
    
    # Alembic needs the DB URL. We pass it via an env var.
    env = os.environ.copy()
    env["DATABASE_URL"] = settings.DATABASE_URL
    
    try:
        # The 'alembic upgrade head' command applies all pending migrations.
        subprocess.run(
            ["alembic", "upgrade", "head"], 
            check=True, 
            env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)) # Run from this script's dir
        )
        print("✅ Migrations applied successfully.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Migration failed: {e}")
        exit(1)

if __name__ == "__main__":
    run_migrations()