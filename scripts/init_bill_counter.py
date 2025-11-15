"""
Initialize bill counter - DEPRECATED
This script is no longer needed as the app uses PostgreSQL with proper migrations.
Use Alembic migrations instead: alembic upgrade head
"""
import os
import sys

print("⚠️ This script is deprecated.")
print("The app now uses PostgreSQL with Alembic migrations.")
print("To initialize the database, run: alembic upgrade head")
print("To create initial data, use the app's init_db() function or run: python scripts/init_db.py")
sys.exit(1)


