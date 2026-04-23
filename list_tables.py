
import sqlite3

db_path = r'd:\Irn-olympiada-back\db.sqlite3'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for t in tables:
    print(t[0])

conn.close()
