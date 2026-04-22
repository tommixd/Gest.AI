# Script de diagnóstico para verificar a integridade da BD e dos templates

import sqlite3
import os

# Caminho absoluto para a BD (ajuste se necessário)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, 'documentos.db')

def verificar():
    print(f"[*] A verificar BD em: {DATABASE}")
    if not os.path.exists(DATABASE):
        print("[!] ERRO: O ficheiro documentos.db não foi encontrado!")
        return

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 1. Ver todas as categorias existentes
    cursor.execute("SELECT DISTINCT categoria FROM documentos")
    categorias = [row[0] for row in cursor.fetchall()]
    print(f"[*] Categorias encontradas na BD: {categorias}")

    # 2. Testar as categorias que o app.py usa
    alvos = ["tempo integral anual", "tempo parcial semestral", "tempo parcial edital"]
    for alvo in alvos:
        cursor.execute("SELECT COUNT(*) FROM documentos WHERE categoria = ?", (alvo,))
        count = cursor.fetchone()[0]
        print(f"[*] Categoria '{alvo}': {count} documentos encontrados.")
        
        if count > 0:
            cursor.execute("SELECT nome, caminho FROM documentos WHERE categoria = ?", (alvo,))
            for doc in cursor.fetchall():
                print(f"   - Ficheiro: {doc[0]} | Caminho: {doc[1]}")
                if not os.path.exists(os.path.join(os.path.dirname(BASE_DIR), doc[1])):
                    print(f"     [!] AVISO: Ficheiro físico não encontrado no disco!")

    conn.close()

if __name__ == '__main__':
    verificar()
