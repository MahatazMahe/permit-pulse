"""
One-off script to confirm we can actually connect to the Neon Postgres
database from Python before we build anything on top of it.
"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

database_url = os.environ["DATABASE_URL"]

conn = psycopg2.connect(database_url)
cursor = conn.cursor()

cursor.execute("SELECT version();")
result = cursor.fetchone()

print("Connected successfully!")
print("Postgres version:", result[0])

cursor.close()
conn.close()