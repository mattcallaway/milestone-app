
"""
Migration: Add plan_id to operations table to link execution.
"""

import sqlite3

def migrate(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(operations)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "plan_id" not in columns:
            print("Adding plan_id to operations table...")
            cursor.execute("ALTER TABLE operations ADD COLUMN plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_operations_plan ON operations(plan_id)")
            conn.commit()
            print("Migration successful.")
        else:
            print("Column plan_id already exists.")
            
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    import os
    
    # Default path for dev
    db_path = "data/milestone.db"
    
    # Allow override
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        sys.exit(1)
        
    migrate(db_path)
