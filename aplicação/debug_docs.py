import mysql.connector
from db_config import DB_CONFIG

ligacao = mysql.connector.connect(**DB_CONFIG)
cursor = ligacao.cursor(dictionary=True)
cursor.execute('SELECT categoria, caminho FROM documentos ORDER BY categoria, caminho')
docs = cursor.fetchall()

for doc in docs:
    partes = doc['caminho'].split('/')
    print(f"[{doc['categoria']}] {doc['caminho']} ({len(partes)} partes)")
    if len(partes) >= 3:
        print(f"  -> partes[2] = {partes[2]}")
