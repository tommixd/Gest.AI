"""
query_templates.py - perguntas template com queries sql parametrizadas

lógica de execução no rag_llm:
1. tentar_template (pergunta): query direta, sem llm, resultado imediato
2. se None -> consultar_bd (pergunta, agente) - sql agent como fallback

adicionar um novo template:
1. acrescenta uma entrada ao dicionário templates,
2. define os padrões regex (em português, case insensitive)
3. escreve a query com %s onde vai o nome do docente (ou outro parametro)
4. define uma função _formatar_* para apresentar o restultado de forma legível
"""


import re
import mysql.connector
from db_config import DB_CONFIG
import json

def _formatar_juri (rows: list[dict], nome: str) -> str:
    if not rows:
        return None
    
    is_juri = rows[0].get("isJuri")

    if is_juri in [1, True, "sim"]:
        return f"Sim, o docente '{nome}' pertence ao júri."
    else:
        return f"Não, o docente '{nome}' não pertence ao júri."

def _formatar_contagem(rows: list[dict], nome: str) -> str:
    total = rows[0].get("total_contratos", 0)
    ultimo = rows[0].get("ultimo_contrato", "desconhecido")
    return (
        f"O docente '{nome}' celebrou {total} contrato(s). "
        f"O mais recente data de {ultimo}."
    )
 
 
def _formatar_historico(rows: list[dict], nome: str) -> str:
    if not rows:
        return None
    linhas = [f"Histórico de contratos de '{nome}':"]
    for r in rows:
        linhas.append(
            f"  • Contrato #{r['id_contrato']} | Renovação nº {r['numero_renovacao']} "
            f"| Data: {r['data_renovacao']} | Tipo: {r['tipo_contrato']} "
            f"| Carga: {r['tempo_contratual']}h ({r['percentagem']}%)"
        )
    return "\n".join(linhas)
 
 
def _formatar_ucs(rows: list[dict], nome: str) -> str:
    if not rows:
        return None
    
    dados_str = rows[0].get("dados_historico")
    if not dados_str:
        return None
    try: 
        dados = json.loads(dados_str)
    except: 
        return None
    
    ucs = []
    for key, value in dados.items():
        if key.startswith("uc_") and value:
            ucs.append((value))
    if not ucs:
        return None
    
    return f"As unidades curriculares do contrato de '{nome}' são: {', '.join(ucs)}."

 
 
def _formatar_renovacoes(rows: list[dict], nome: str) -> str:
    total = rows[0].get("total_renovacoes", 0)
    return f"O contrato original de '{nome}' tem {total} renovação(ões)."
 
 
def _formatar_documentos(rows: list[dict], nome: str) -> str:
    if not rows:
        return None
    linhas = [f"Documentos de '{nome}':"]
    for r in rows:
        linhas.append(
            f"  • {r['nome']} | Categoria: {r['categoria']} | Upload: {r['data_upload']}"
        )
    return "\n".join(linhas)
 
 
def _formatar_carga(rows: list[dict], nome: str) -> str:
    if not rows:
        return None
    linhas = [f"Carga horária do contrato mais recente de '{nome}':"]
    r = rows[0]
    linhas.append(f"  • Tempo contratual: {r['tempo_contratual']}h")
    linhas.append(f"  • Tempo de aulas:   {r['tempo_aulas']}h")
    linhas.append(f"  • Tempo de apoio:   {r['tempo_apoio']}h")
    linhas.append(f"  • Preparação:       {r['tempo_preparacao']}h")
    linhas.append(f"  • Percentagem:      {r['percentagem']}%")
    return "\n".join(linhas)
 
 
def tentar_template(pergunta: str) -> str | None:
    """
    Verifica se a pergunta bate com algum template.
    Se sim, executa a query parametrizada diretamente (sem LLM) e devolve
    o resultado já formatado como texto.
    Se não houver match, devolve None e o SQL Agent trata a pergunta.
 
    Args:
        pergunta: Pergunta em linguagem natural do utilizador.
 
    Returns:
        String com a resposta formatada, ou None se nenhum template bater.
    """
    for nome_template, config in TEMPLATES.items():
        for padrao in config["padroes"]:
            match = re.search(padrao, pergunta) # Mantém sem IGNORECASE
            if match:
                # Pega no grupo 1 se existir (nome), senão fica vazio (perguntas globais)
                parametro = match.group(1).strip() if match.groups() else ""
                param_sql = f"%{parametro}%"
 
                print(f"[Template] Match: '{nome_template}' | Parâmetro: '{parametro}'")
 
                try:
                    conn   = mysql.connector.connect(**DB_CONFIG)
                    cursor = conn.cursor(dictionary=True)
                    
                    # Só passa a tupla (param_sql,) se a query tiver '%s'
                    if "%s" in config["query"]:
                        cursor.execute(config["query"], (param_sql,))
                    else:
                        cursor.execute(config["query"])
                        
                    rows   = cursor.fetchall()
                    cursor.close()
                    conn.close()
 
                    return config["formatar"](rows, parametro)
 
                except Exception as e:
                    print(f"[Template] Erro em '{nome_template}': {e}")
                    return None
 
    return None

def _formatar_listar_juris(rows: list[dict], parametro: str) -> str | None:
    if not rows:
        return None
    nomes = [r["nome"] for r in rows]
    return "Os seguintes docentes fazem parte do júri: " + ", ".join(nomes) + "."


TEMPLATES = {

    "docente_juri": {
        "padroes": [
            r"(?:o|a).+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+).+?j[uú]ri",
            r"j[uú]ri.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+).+j[uú]ri",
        ],
        "query": """
            SELECT isJuri 
            FROM docentes 
            WHERE nome LIKE %s LIMIT 1
        """,
        "formatar": _formatar_juri,
    },
 
    "contratos_docente": {
        "padroes": [
            r"quantos contratos.+(?:tem|celebrou|possui|fez).+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"(?:tem|celebrou|possui|fez).+contratos?.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"contratos?.+docente\s+([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
        ],
        "query": """
            SELECT COUNT(*) AS total_contratos,
                   MAX(c.data_renovacao) AS ultimo_contrato
            FROM contratos c
            WHERE c.docentes_id_docente = (
                SELECT id_docente FROM docentes WHERE nome LIKE %s LIMIT 1
            )
        """,
        "formatar": _formatar_contagem,
    },
 
    "historico_docente": {
        "padroes": [
            r"histór(?:ia|ico).+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"todos os contratos.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"lista.+contratos.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
        ],
        "query": """
            SELECT c.id_contrato, c.numero_renovacao, c.data_renovacao,
                   t.tipo_contrato, ch.tempo_contratual, ch.percentagem
            FROM contratos c
            JOIN templates t      ON c.templates_id_template  = t.id_template
            JOIN carga_horaria ch ON c.carga_horaria_id_carga = ch.id_carga
            WHERE c.docentes_id_docente = (
                SELECT id_docente FROM docentes WHERE nome LIKE %s LIMIT 1
            )
            ORDER BY c.data_renovacao DESC
        """,
        "formatar": _formatar_historico,
    },
 
    "ucs_docente": {
        "padroes": [
            r"unidades? curriculares?.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"(?:ucs?|cadeiras?|disciplinas?).+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+).+(?:ucs?|cadeiras?|disciplinas?|leciona|ensina)",
        ],
        "query": """
            SELECT dados_historico 
            FROM docentes 
            WHERE nome LIKE %s LIMIT 1
        """,
        "formatar": _formatar_ucs,
    },
 
    "renovacoes_docente": {
        "padroes": [
            r"quantas? renova[çc][õo]es?.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"renova[çc][õo]es?.+contrato.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
        ],
        "query": """
            SELECT COUNT(*) AS total_renovacoes
            FROM contratos
            WHERE contrato_original_id = (
                SELECT id_contrato FROM contratos
                WHERE docentes_id_docente = (
                    SELECT id_docente FROM docentes WHERE nome LIKE %s LIMIT 1
                )
                AND contrato_original_id IS NULL
                LIMIT 1
            )
        """,
        "formatar": _formatar_renovacoes,
    },
 
    "documentos_docente": {
        "padroes": [
            r"documentos?.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"ficheiros?.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
        ],
        "query": """
            SELECT nome, categoria, data_upload
            FROM documentos
            WHERE docentes_id_docente = (
                SELECT id_docente FROM docentes WHERE nome LIKE %s LIMIT 1
            )
            ORDER BY data_upload DESC
        """,
        "formatar": _formatar_documentos,
    },
 
    "carga_horaria_docente": {
        "padroes": [
            r"carga hor[aá]ria.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"horas?.+contrato.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)",
            r"([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+).+carga hor[aá]ria",
        ],
        "query": """
            SELECT ch.tempo_contratual, ch.tempo_aulas,
                   ch.tempo_apoio, ch.tempo_preparacao, ch.percentagem
            FROM carga_horaria ch
            JOIN contratos c ON c.carga_horaria_id_carga = ch.id_carga
            WHERE c.docentes_id_docente = (
                SELECT id_docente FROM docentes WHERE nome LIKE %s LIMIT 1
            )
            ORDER BY c.data_renovacao DESC LIMIT 1
        """,
        "formatar": _formatar_carga,
    },
 
    

    # No teu dicionário TEMPLATES, junta este novo bloco:
    "listar_todos_juris": {
        "padroes": [
            r"que docentes s[ãa]o j[uú]ris?",
            r"quais s[ãa]o os j[uú]ris?",
            r"lista.+j[uú]ris",
        ],
        "query": """
            SELECT nome FROM docentes WHERE isJuri = 'sim'
        """,
        "formatar": _formatar_listar_juris,
    },
}