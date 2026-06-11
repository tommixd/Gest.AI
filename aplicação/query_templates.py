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

def _formatar_contagem(rows: list[dict], nome: str) -> str:
    total = rows[0].get("total_contratos", 0)
    ultimo = rows[0].get("ultimo_contrato", "desconhecido")
    return (
        f"O docente '{nome}' celebrou {total} contrato(s). "
        f"O mais recente data de {ultimo}."
    )
 
 
def _formatar_historico(rows: list[dict], nome: str) -> str:
    if not rows:
        return f"Não foram encontrados contratos para '{nome}'."
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
        return f"Não foram encontradas UCs para o contrato mais recente de '{nome}'."
    linhas = [f"UCs do contrato mais recente de '{nome}':"]
    for r in rows:
        linhas.append(f"  • {r['uc']} — {r['horas_atribuidas']}h atribuídas")
    return "\n".join(linhas)
 
 
def _formatar_renovacoes(rows: list[dict], nome: str) -> str:
    total = rows[0].get("total_renovacoes", 0)
    return f"O contrato original de '{nome}' tem {total} renovação(ões)."
 
 
def _formatar_documentos(rows: list[dict], nome: str) -> str:
    if not rows:
        return f"Não foram encontrados documentos para '{nome}'."
    linhas = [f"Documentos de '{nome}':"]
    for r in rows:
        linhas.append(
            f"  • {r['nome']} | Categoria: {r['categoria']} | Upload: {r['data_upload']}"
        )
    return "\n".join(linhas)
 
 
def _formatar_carga(rows: list[dict], nome: str) -> str:
    if not rows:
        return f"Não foram encontrados dados de carga horária para '{nome}'."
    linhas = [f"Carga horária do contrato mais recente de '{nome}':"]
    r = rows[0]
    linhas.append(f"  • Tempo contratual: {r['tempo_contratual']}h")
    linhas.append(f"  • Tempo de aulas:   {r['tempo_aulas']}h")
    linhas.append(f"  • Tempo de apoio:   {r['tempo_apoio']}h")
    linhas.append(f"  • Preparação:       {r['tempo_preparacao']}h")
    linhas.append(f"  • Percentagem:      {r['percentagem']}%")
    return "\n".join(linhas)
 
 
def _formatar_docentes_departamento(rows: list[dict], nome: str) -> str:
    if not rows:
        return f"Não foram encontrados docentes no departamento '{nome}'."
    linhas = [f"Docentes do departamento '{nome}':"]
    for r in rows:
        linhas.append(f"  • {r['nome']} ({r['tipo_docente']})")
    return "\n".join(linhas)
 
 
# ---------------------------------------------------------------------------
# Dicionário de templates
# ---------------------------------------------------------------------------
 
TEMPLATES = {
 
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
            r"([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+).+(?:ucs?|cadeiras?|disciplinas?|lecciona|ensina)",
        ],
        "query": """
            SELECT u.nome AS uc, cu.horas_atribuidas
            FROM contrato_ucs cu
            JOIN ucs u ON cu.ucs_id = u.id
            WHERE cu.contratos_id_contrato = (
                SELECT id_contrato FROM contratos
                WHERE docentes_id_docente = (
                    SELECT id_docente FROM docentes WHERE nome LIKE %s LIMIT 1
                )
                ORDER BY data_renovacao DESC LIMIT 1
            )
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
 
    "docentes_departamento": {
        "padroes": [
            r"docentes?.+departamento.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)*)",
            r"quem.+(?:é|são|pertence).+departamento.+?([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)*)",
        ],
        "query": """
            SELECT nome, tipo_docente
            FROM docentes
            WHERE departamento LIKE %s
            ORDER BY nome
        """,
        "formatar": _formatar_docentes_departamento,
        "param_tipo": "departamento",  # indica que o parâmetro não é um nome de docente
    },
}
 
 
# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
 
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
            match = re.search(padrao, pergunta, re.IGNORECASE)
            if match:
                parametro = match.group(1).strip()
 
                # Para templates de departamento o parâmetro já é o departamento
                # Para todos os outros é um nome de docente
                param_sql = f"%{parametro}%"
 
                print(f"[Template] Match: '{nome_template}' | Parâmetro: '{parametro}'")
 
                try:
                    conn   = mysql.connector.connect(**DB_CONFIG)
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute(config["query"], (param_sql,))
                    rows   = cursor.fetchall()
                    cursor.close()
                    conn.close()
 
                    return config["formatar"](rows, parametro)
 
                except Exception as e:
                    print(f"[Template] Erro em '{nome_template}': {e}")
                    return None  # fallback para o SQL Agent
 
    return None  # nenhum template bateu