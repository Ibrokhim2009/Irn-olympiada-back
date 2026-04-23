
import sqlite3

db_path = r'd:\Irn-olympiada-back\db.sqlite3'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

user_id = 2
olympiad_id = 5

query = "SELECT id, user_id, olympiad_id, sub_olympiad_grade_id, completed_at, length(answers_json) FROM core_examresult WHERE user_id = ? AND olympiad_id = ?"
cursor.execute(query, (user_id, olympiad_id))
rows = cursor.fetchall()

print(f"Results for user {user_id} and olympiad {olympiad_id}:")
for row in rows:
    print(row)

conn.close()
