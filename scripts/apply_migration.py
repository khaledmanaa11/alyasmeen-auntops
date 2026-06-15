import sys
import os
from app.db.database import execute

def apply_migration(file_path):
    print(f"Applying migration: {file_path}")
    with open(file_path, 'r') as f:
        sql = f.read()
    
    # We execute the entire file as a single batch.
    # This is safer for PL/pgSQL functions which contain internal semicolons.
    try:
        execute(sql)
        print("Migration applied successfully.")
    except Exception as e:
        print(f"Error executing migration: {e}")
        # Note: If a migration partially fails, it might leave the DB in an inconsistent state
        # if not wrapped in a transaction. PostgreSQL EXECUTE runs in its own context.
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apply_migration.py <path_to_sql>")
        sys.exit(1)
    apply_migration(sys.argv[1])
