import docx
import os
import sqlite3
import re
import json

# Define o caminho para a BD 
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'documentos.db')

# ---------------------------------------------------------
# NOVIDADE: MAPEAMENTO PARA A CATEGORIA DA BASE DE DADOS
# ---------------------------------------------------------
# Associa o que vem do teu JSON à categoria exata que tens na tua BD
CATEGORIA_POR_TIPO = {
    "integral": "tempo integral anual",
    "parcial": "tempo parcial semestral",
    "parcial-edital": "tempo parcial edital"
}

# Pasta principal onde os documentos preenchidos vão ser guardados
pasta_output = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Modelos Contratuais", "Modelos Gerados"))

def criar_nome_pasta_limpo(nome_completo):
    """
    Pega no nome do docente e transforma num nome de pasta válido e limpo.
    """
    nome = nome_completo.replace("Professor ", "").replace("Professora ", "")
    nome = nome.replace("Prof. Dr. ", "").replace("Prof. ", "")
    nome = nome.strip().replace(" ", "_")
    nome_limpo = re.sub(r'[\\/*?:"<>|]', "", nome)
    return f"Contrato_{nome_limpo}"

def processar_renovacao(dados_contrato):
    # 1. Determinar o tipo de contrato e a categoria correspondente na BD
    tipo_contrato = dados_contrato.get("tipo_contrato", "integral").lower()
    categoria_bd = CATEGORIA_POR_TIPO.get(tipo_contrato)
    
    if not categoria_bd:
        print(f"[!] Erro: O tipo '{tipo_contrato}' não tem uma categoria associada no sistema.")
        return

    print(f"[*] A processar contratação do tipo: {tipo_contrato.upper()} (Categoria BD: '{categoria_bd}')")

    # 2. Criar a subpasta do docente
    nome_docente = dados_contrato.get("{{nome_docente}}", "Docente_Desconhecido")
    nome_subpasta = criar_nome_pasta_limpo(nome_docente)
    caminho_final = os.path.join(pasta_output, nome_subpasta)
    
    if not os.path.exists(caminho_final):
        os.makedirs(caminho_final)
        print(f"[*] Criada pasta para o processo: {caminho_final}")

    # 3. Ligar à BD e procurar TODOS os templates dessa categoria!
    templates_encontrados = []
    try:
        ligacao = sqlite3.connect(DATABASE)
        ligacao.row_factory = sqlite3.Row
        cursor = ligacao.cursor()
        
        # MAGIA AQUI: Em vez de procurar por nomes, procuramos por categoria!
        query = "SELECT nome, caminho FROM documentos WHERE categoria = ?"
        cursor.execute(query, (categoria_bd,))
        templates_encontrados = cursor.fetchall()
        ligacao.close()
        
    except Exception as e:
        print(f"[!] Erro ao ligar à base de dados SQLite: {e}")
        return

    if not templates_encontrados:
        print(f"[!] Aviso: Nenhum documento encontrado na BD para a categoria '{categoria_bd}'.")
        return

    print(f"[*] Encontrados {len(templates_encontrados)} templates na categoria '{categoria_bd}'. A preencher...")

    # 4. Processar cada template encontrado
    for template in templates_encontrados:
        nome_ficheiro = template["nome"]
        caminho_template = template["caminho"]

        if not os.path.exists(caminho_template):
            print(f"[Aviso] O ficheiro '{nome_ficheiro}' está na BD, mas não foi encontrado no disco: {caminho_template}")
            continue

        try:
            documento = docx.Document(caminho_template)

            # Substituir nos parágrafos normais
            for paragrafo in documento.paragraphs:
                for chave, valor in dados_contrato.items():
                    if chave in paragrafo.text:
                        paragrafo.text = paragrafo.text.replace(chave, str(valor))

            # Substituir nas tabelas
            for tabela in documento.tables:
                for linha in tabela.rows:
                    for celula in linha.cells:
                        for paragrafo in celula.paragraphs:
                            for chave, valor in dados_contrato.items():
                                if chave in paragrafo.text:
                                    paragrafo.text = paragrafo.text.replace(chave, str(valor))

            # Guardar o ficheiro final na nova subpasta
            caminho_output_doc = os.path.join(caminho_final, nome_ficheiro)
            documento.save(caminho_output_doc)
            print(f"[*] Sucesso: Ficheiro '{nome_ficheiro}' guardado.")
            
        except Exception as e:
            print(f"[!] Erro ao processar o documento '{nome_ficheiro}': {e}")
            
    print("\n[*] Processo concluído com sucesso!")


# Executar a função com dados de teste 
if __name__ == '__main__':
    caminho_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testeDinamicoTemplates.json")
    
    try:
        with open(caminho_json, 'r', encoding='utf-8') as ficheiro:
            dados_externos = json.load(ficheiro)
            
        print("[*] Dados carregados do ficheiro JSON.")
        processar_renovacao(dados_externos)
        
    except FileNotFoundError:
        print(f"[!] Erro: Ficheiro '{caminho_json}' não encontrado.")