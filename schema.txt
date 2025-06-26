import sqlite3

def analyze_database(db_path):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        print("DATABASE SCHEMA ANALYSIS")
        print("=" * 50)
        
        for table in tables:
            print(f"\nTable: {table}")
            print("-" * 30)
            
            # Get column info
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            
            for col in columns:
                col_id, name, data_type, not_null, default, pk = col
                print(f"  {name}: {data_type}" + (" (PRIMARY KEY)" if pk else ""))
            
            # Get sample data (first 3 rows)
            cursor.execute(f"SELECT * FROM {table} LIMIT 3")
            sample_data = cursor.fetchall()
            
            if sample_data:
                print("  Sample data:")
                for row in sample_data:
                    print(f"    {row}")
            
            # Get record count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  Total records: {count}")

# Run this
analyze_database("testing.db")