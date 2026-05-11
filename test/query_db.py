import sqlite3

conn = sqlite3.connect('database/legal_documents.db')
cursor = conn.cursor()
cursor.execute("SELECT so_hieu FROM document_metadata WHERE ten_van_ban LIKE '%BỘ LUẬT HÌNH SỰ%'")
print([r[0] for r in cursor.fetchall()])
