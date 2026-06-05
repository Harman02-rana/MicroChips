import os
os.chdir(r"D:\Setup Files\Desktop\MicroChips")

import sys
sys.path.insert(0, r"D:\Setup Files\Desktop\MicroChips")

from database import build_database_url
from sqlalchemy import create_engine, inspect

def main():
    db_url = build_database_url()
    print("Database URL:", db_url)
    engine = create_engine(db_url)
    inspector = inspect(engine)
    
    for table_name in inspector.get_table_names():
        print(f"\nTable: {table_name}")
        for column in inspector.get_columns(table_name):
            print(f"  Column: {column['name']} ({column['type']})")
        
        fks = inspector.get_foreign_keys(table_name)
        if fks:
            print("  Foreign Keys:")
            for fk in fks:
                print(f"    {fk}")

if __name__ == "__main__":
    main()
