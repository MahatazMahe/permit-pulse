"""
Runs schema.sql against the database to create our tables.
Safe to run multiple times -- every statement uses IF NOT EXISTS,
so re-running this won't error out or duplicate anything.
"""

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

database_url = os.environ["DATABASE_URL"]
schema_sql = Path("src/permit_pulse/schema.sql").read_text(encoding="utf-8")

conn = psycopg2.connect(database_url)
cursor = conn.cursor()

cursor.execute(schema_sql)
conn.commit()

print("Schema applied successfully.")

# Confirm what actually exists now by asking Postgres directly,
# rather than just trusting that our script "should have" worked.
cursor.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name;
""")
tables = cursor.fetchall()
print("Tables in database:", [t[0] for t in tables])

cursor.close()
conn.close()