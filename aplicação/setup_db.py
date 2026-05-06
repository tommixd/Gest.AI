import mysql.connector
import os
from datetime import datetime

# Coloca aqui os teus dados do MySQL Workbench
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',             # O teu utilizador do MySQL
    'password': '04072002Tomas!', # A password que usas no Workbench
    'database': 'BaseDadosGestAI'          # O nome do schema que criaste no Workbench
}

def obter_ligacao():
    """Cria e devolve a ligação ao MySQL"""
    return mysql.connector.connect(**DB_CONFIG)

def popular_bd():
    """Percorre as pastas e insere os documentos na BD MySQL"""
    
    pastas_categorias = {
        'pdfs_teste' : 'pdf_llm',
        'Modelos Contratuais/Modelos Gerados': 'gerado',
        'Modelos Contratuais/tempo integral anual': 'tempo integral anual',
        'Modelos Contratuais/tempo parcial semestral': 'tempo parcial semestral'
    }

    try:
        conn = obter_ligacao()
        cursor = conn.cursor()

        # Limpa os registos antigos para não haver duplicados quando corres o script
        cursor.execute('TRUNCATE TABLE documentos') 

        documentos_inseridos = 0

        for pasta_base, categoria in pastas_categorias.items():
            if not os.path.exists(pasta_base):
                print(f"[Aviso] A pasta '{pasta_base}' não existe. A ignorar...")
                continue

            for root, dirs, files in os.walk(pasta_base):
                for file in files:
                    if file.startswith('.') or file.startswith('~$'):
                        continue 

                    caminho_completo = os.path.join(root, file).replace('\\', '/')

                    # ATENÇÃO: No MySQL usamos %s em vez de ?
                    query = '''
                        INSERT INTO documentos (nome, caminho, categoria, data_upload)
                        VALUES (%s, %s, %s, %s)
                    '''
                    valores = (file, caminho_completo, categoria, datetime.now().isoformat())
                    
                    cursor.execute(query, valores)
                    documentos_inseridos += 1
                    print(f"Inserido: {file} -> Categoria: [{categoria}]")
            
        conn.commit()
        print(f"\n[*] Sucesso! Total de documentos inseridos no MySQL: {documentos_inseridos}")

    except mysql.connector.Error as err:
        print(f"[!] Erro de ligação ao MySQL: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    print("[*] A ligar ao MySQL e a atualizar a base de dados...")
    popular_bd()