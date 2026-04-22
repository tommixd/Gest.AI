import sqlite3
import os
from datetime import datetime

# 1. Definir o caminho da BD relativo ao local deste script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'documentos.db') # Cria a BD na mesma pasta do script

def criar_tabela():
    """Cria a base de dados e a tabela se não existirem (e limpa os dados antigos)"""
    # Garante que a pasta onde a BD vai ficar existe
    os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DROP TABLE IF EXISTS documentos')
    cursor.execute('''
        CREATE TABLE documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            caminho TEXT NOT NULL,
            categoria TEXT NOT NULL,
            data_upload TEXT NOT NULL
        )
    ''')
    conn.commit()
    return conn, cursor

def popular_bd(conn, cursor):
    """Percorre as pastas e insere os documentos na bd com filtro de subpastas"""
    
    pastas_categorias = {
        'pdfs_teste' : 'pdf_llm',
        'Modelos Contratuais/Modelos Gerados': 'gerado',
        'Modelos Contratuais/tempo integral anual': 'tempo integral anual',
        'Modelos Contratuais/tempo parcial semestral': 'tempo parcial semestral',
        'Modelos Contratuais/tempo parcial edital': 'tempo parcial edital'
    }

    documentos_inseridos = 0

    # O ROOT_DIR ajuda a calcular os caminhos relativos corretamente
    ROOT_DIR = os.path.dirname(BASE_DIR)

    for pasta_base, categoria in pastas_categorias.items():
        # Procuramos as pastas a partir da raiz do projeto (uma pasta acima de 'aplicação')
        caminho_busca = os.path.join(ROOT_DIR, pasta_base)
        
        if not os.path.exists(caminho_busca):
            print(f"[Aviso] A pasta '{caminho_busca}' não existe. A ignorar...")
            continue

        for root, dirs, files in os.walk(caminho_busca):
            for file in files:
                if file.startswith('.') or file.startswith('~$'):
                    continue 

                caminho_completo = os.path.join(root, file).replace('\\', '/')
                
                # --- NOVO FILTRO DE ORGANIZAÇÃO ---
                # Se for categoria 'gerado', só inserimos se estiver numa subpasta (Caso)
                # Ex: .../Modelos Gerados/Contrato_Maria/doc.docx -> OK
                # Ex: .../Modelos Gerados/doc.docx -> IGNORAR
                rel_path = os.path.relpath(caminho_completo, caminho_busca).replace('\\', '/')
                partes = rel_path.split('/')
                
                if categoria == 'gerado' and len(partes) < 2:
                    print(f"[-] A ignorar (fora de pasta de contrato): {file}")
                    continue

                # Guardamos o caminho relativo à raiz do projeto para o RAG funcionar
                caminho_db = os.path.relpath(caminho_completo, ROOT_DIR).replace('\\', '/')

                cursor.execute('''
                    INSERT INTO documentos (nome, caminho, categoria, data_upload)
                    VALUES (?, ?, ?, ?)
                ''', (file, caminho_db, categoria, datetime.now().isoformat()))

                documentos_inseridos += 1
                print(f"[+] Inserido: {file} -> [{categoria}]")
        
    conn.commit()
    print(f"\n[*] Total de documentos inseridos na base de dados: {documentos_inseridos}")

if __name__ == '__main__':
    print("[*] A limpar e atualizar a base de dados...")
    try:
        conexao, cursor_bd = criar_tabela()
        popular_bd(conexao, cursor_bd)
        conexao.close()
        print("[*] Base de dados pronta!")
    except Exception as e:
        print(f"[!] Erro durante o setup: {e}")
