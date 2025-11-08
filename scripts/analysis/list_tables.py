#!/usr/bin/env python3
import psycopg2

# Database credentials
DB_HOST = '34.55.195.199'
DB_PORT = 5432
DB_USER = 'yogass09'
DB_PASSWORD = 'jaimaakamakhya'

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database='cp_ai'
)

cursor = conn.cursor()
cursor.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name
""")

print("Tables in cp_ai database:")
for row in cursor.fetchall():
    print(f"  - {row[0]}")

cursor.close()
conn.close()
