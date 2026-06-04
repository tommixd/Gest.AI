import os
import re
import json
import mysql.connector
from db_config import DB_CONFIG

# NOVO IMPORT: Sai o "import docx", entra o DocxTemplate
from docxtpl import DocxTemplate 

CATEGORIA_POR_TIPO = {
    "integral": "tempo integral anual",
    "parcial": "tempo parcial semestral",
    "parcial-edital": "tempo parcial edital"
}

pasta_output = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Modelos Contratuais", "Modelos Gerados"))

def criar_nome_pasta_limpo(nome_completo):
    nome = nome_completo.replace("Professor ", "").replace("Professora ", "")
    nome = nome.replace("Prof. Dr. ", "").replace("Prof. ", "")
    nome = nome.strip().replace(" ", "_")
    nome_limpo = re.sub(r'[\\/*?:"<>|]', "", nome)
    return f"Contrato_{nome_limpo}"

def processar_renovacao(dados_contrato):
    tipo_contrato = dados_contrato.get("tipo_contrato", "integral").lower()
    categoria_bd = CATEGORIA_POR_TIPO.get(tipo_contrato)
    
    if not categoria_bd:
        print(f"[!] Erro: O tipo '{tipo_contrato}' não tem uma categoria associada no sistema.")
        return

    print(f"[*] A processar contratação do tipo: {tipo_contrato.upper()} (Categoria BD: '{categoria_bd}')")

    nome_docente = dados_contrato.get("nome_docente", "Docente_Desconhecido")
    nome_subpasta = criar_nome_pasta_limpo(nome_docente)
    caminho_final = os.path.join(pasta_output, nome_subpasta)
    
    if not os.path.exists(caminho_final):
        os.makedirs(caminho_final)
        print(f"[*] Criada pasta para o processo: {caminho_final}")

    templates_encontrados = []
    try:
        ligacao = mysql.connector.connect(**DB_CONFIG)
        cursor = ligacao.cursor(dictionary=True)
        query = "SELECT nome, caminho FROM documentos WHERE categoria = %s"
        cursor.execute(query, (categoria_bd,))
        templates_encontrados = cursor.fetchall()
        cursor.close()
        ligacao.close()
    except Exception as e:
        print(f"[!] Erro ao ligar à base de dados MySQL: {e}")
        return

    if not templates_encontrados:
        print(f"[!] Aviso: Nenhum documento encontrado na BD para a categoria '{categoria_bd}'.")
        return

    print(f"[*] Encontrados {len(templates_encontrados)} templates na categoria '{categoria_bd}'. A preencher...")

    # --- INÍCIO DA NOVA LÓGICA DOCXTPL ---
    for template in templates_encontrados:
        nome_ficheiro = template["nome"]
        caminho_template = template["caminho"]

        if not os.path.exists(caminho_template):
            print(f"[Aviso] O ficheiro '{nome_ficheiro}' não foi encontrado no disco: {caminho_template}")
            continue

        try:
            # 1. Carregar o documento com o DocxTemplate
            doc = DocxTemplate(caminho_template)

            # 2. Limpar as chaves para criar o contexto limpo.
            # O docxtpl não quer "{{chave}}" no dicionário, apenas "chave".
            contexto = {}
            for k, v in dados_contrato.items():
                chave_limpa = k.replace("{", "").replace("}", "").strip()

                valor_limpo = str(v).replace("{", "").replace("}", "").strip()
                contexto[chave_limpa] = valor_limpo

            # 3. A magia acontece aqui: o render substitui tudo automaticamente 
            # sem quebrar tabelas, parágrafos ou formatação!
            doc.render(contexto)

            # 4. Guardar o documento final
            caminho_output_doc = os.path.join(caminho_final, nome_ficheiro)
            doc.save(caminho_output_doc)
            print(f"[*] Sucesso: Ficheiro '{nome_ficheiro}' gerado.")
            
        except Exception as e:
            print(f"[!] Erro ao processar o documento '{nome_ficheiro}': {e}")
    # --- FIM DA NOVA LÓGICA ---
            
    print("\n[*] Processo concluído com sucesso!")