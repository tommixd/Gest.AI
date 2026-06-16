"""
Componente 3: SQL Agent (Text-to-SQL Direto)
Responsabilidade única: receber a pergunta, injetar o esquema da BD no prompt,
pedir à LLM APENAS o código SQL, executar no MySQL e devolver o resultado bruto.
"""

import warnings
from langchain_community.utilities import SQLDatabase
from langchain_core.language_models.llms import BaseLLM
from db_config import DB_CONFIG

# Suprimir warnings do SQLAlchemy para um terminal limpo
warnings.filterwarnings("ignore", category=UserWarning)

TABELAS_PERMITIDAS = [
    "docentes", "contratos", "templates", "carga_horaria",
    "contrato_ucs", "ucs", "areas_estudo", "cursos", "cursos_has_ucs",
    "detalhes_contratados", "documentos", "rascunhos",
]

def _criar_uri_mysql() -> str:
    """Constrói a URI de ligação MySQL para o SQLAlchemy."""
    return (
        f"mysql+mysqlconnector://"
        f"{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    )

def criar_sql_agent(llm: BaseLLM, tabelas_permitidas: list[str] | None = None):
    """
    Guarda a ligação à BD e a instância da LLM num dicionário simples.
    Adeus LangChain AgentExecutor!
    """
    uri = _criar_uri_mysql()
    db = SQLDatabase.from_uri(uri, include_tables=tabelas_permitidas or TABELAS_PERMITIDAS)
    print(f"[Text-to-SQL] Componente ativado. Tabelas: {len(tabelas_permitidas or TABELAS_PERMITIDAS)}")
    
    return {"db": db, "llm": llm}

def consultar_bd(pergunta: str, agente: dict) -> str | None:
    p_lower = pergunta.lower().strip()
    is_sql_injection = False
    
    comandos_iniciais = ["select ", "update ", "delete ", "insert ", "drop ", "alter ", "create "]
    
    # Regra 1: A pergunta começa DIRETAMENTE com um comando SQL? (Ex: "SELECT * FROM...")
    if any(p_lower.startswith(cmd) for cmd in comandos_iniciais):
        is_sql_injection = True
        
    # Regra 2: Contém estruturas relacionais exclusivas de SQL no meio do texto?
    elif ("select " in p_lower and "from " in p_lower) or \
         ("update " in p_lower and "set " in p_lower) or \
         ("insert into " in p_lower):
        is_sql_injection = True

    if is_sql_injection:
        print("[Segurança] Tentativa de injeção SQL bloqueada por heurística.")
        return "Alerta de Segurança: A inserção de código SQL direto não é permitida. Por favor, formule a sua questão em linguagem natural."
    
    db = agente["db"]
    llm = agente["llm"]
    
    esquema = db.get_table_info()
    
    prompt = f"""<|im_start|>system
És um engenheiro de dados MySQL hiper-preciso.
A tua ÚNICA função é traduzir a pergunta do utilizador para código SQL (SELECT) puro.

REGRAS OBRIGATÓRIAS:
REGRAS OBRIGATÓRIAS:
1. Apenas código SQL. Sem formatação markdown (```sql) e sem texto extra.
2. Usa SEMPRE `LIKE '%termo%'` em vez de `=`.
3. REGRA 1 (Templates): A coluna 'tipo_contrato' NÃO EXISTE na tabela 'contratos'. Para extrair o tipo, usa o JOIN: `JOIN templates t ON c.templates_id_template = t.id_template`.
4. REGRA 2 (Otimização Carga Horária): Se a pergunta solicitar APENAS a relação entre horas e percentagens (ex: 50%), acede DIRETAMENTE à tabela 'carga_horaria' sem efetuar JOINs com outras tabelas.
5. REGRA 3 (Relação Docentes-Contratos): Para associar nomes de docentes a tipos de contrato (ex: "tempo integral"), usa OBRIGATORIAMENTE a tripla junção: `FROM docentes d JOIN contratos c ON d.id_docente = c.docentes_id_docente JOIN templates t ON c.templates_id_template = t.id_template`.

EXEMPLOS DE COMPORTAMENTO OBRIGATÓRIO (IMITA ISTO):

Pergunta: Existem docentes no departamento de Informática?
SQL: SELECT nome FROM docentes WHERE departamento LIKE '%Informática%';

Pergunta: Que áreas de contratação estão mencionadas no histórico?
SQL: SELECT DISTINCT dados_historico->>'$.area_contratacao' FROM docentes WHERE dados_historico IS NOT NULL AND dados_historico != '';

Pergunta: Qual é o tipo de contrato mais comum?
SQL: SELECT t.tipo_contrato, COUNT(*) FROM contratos c JOIN templates t ON c.templates_id_template = t.id_template GROUP BY t.tipo_contrato ORDER BY COUNT(*) DESC LIMIT 1;

Pergunta: Quantas horas de apoio tem um contrato a tempo parcial de 50% de carga horaria?
SQL: SELECT tempo_apoio FROM carga_horaria WHERE percentagem LIKE '%50%' LIMIT 1;

Pergunta: Quais são os docentes a tempo integral?
SQL: SELECT DISTINCT d.nome FROM docentes d JOIN contratos c ON d.id_docente = c.docentes_id_docente JOIN templates t ON c.templates_id_template = t.id_template WHERE t.tipo_contrato LIKE '%integral%';

ESQUEMA DA BASE DE DADOS:
{esquema}
<|im_end|>
<|im_start|>user
{pergunta}
<|im_end|>
<|im_start|>assistant
SELECT """

    try:
        raw_output = llm.invoke(prompt)
        sql_limpo = raw_output.strip().replace("```sql", "").replace("```", "").split(";")[0]
        query = "SELECT " + sql_limpo + ";"
        
        print(f"\n[Text-to-SQL] Query Gerada: {query}")
        
        resultado = db.run(query)
        
        # Correção brutal: Se o resultado for vazio, nós AVISAMOS a LLM que é vazio (em vez de devolver None)
        if not resultado or resultado == "[]" or resultado == "":
            print("[Text-to-SQL] A query executou com sucesso mas devolveu 0 linhas.")
            return f"Query executada: {query}\nResultado bruto: 0 linhas encontradas. Isto significa que a resposta à pergunta do utilizador é negativa ou zero."
            
        print(f"[Text-to-SQL] Sucesso! Linhas obtidas.")
        return f"Query executada: {query}\nResultado bruto: {resultado}"
        
    except Exception as e:
        print(f"[Text-to-SQL] Falha na execução da query: {e}")
        return None