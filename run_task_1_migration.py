import os
from app.db.database import execute, query

def run_migration():
    print("Running migration...")
    migration_path = "supabase/migrations/20260615000000_add_paused_to_sessions.sql"
    with open(migration_path, "r") as f:
        sql = f.read()
    
    try:
        execute(sql)
        print("Migration executed successfully.")
    except Exception as e:
        print(f"Failed to execute migration: {e}")

    try:
        res = query("SELECT paused FROM sessions LIMIT 0")
        print(f"Verification query result: {res}")
    except Exception as e:
        print(f"Verification query failed: {e}")

if __name__ == "__main__":
    run_migration()
