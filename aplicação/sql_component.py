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
    db = agente["db"]
    llm = agente["llm"]
    
    esquema = db.get_table_info()
    
    prompt = f"""<|im_start|>system
És um engenheiro de dados MySQL hiper-preciso.
A tua ÚNICA função é traduzir a pergunta do utilizador para código SQL (SELECT) puro.

REGRAS OBRIGATÓRIAS:
1. Apenas código SQL. Sem formatação markdown (```sql) e sem texto extra.
2. Usa SEMPRE `LIKE '%termo%'` em vez de `=`.
3. REGRA DE OURO: A coluna 'tipo_contrato' NÃO EXISTE na tabela 'contratos'. Para saberes o tipo de contrato, tens OBRIGATORIAMENTE de fazer JOIN com a tabela 'templates' (ex: JOIN templates t ON c.templates_id_template = t.id_template).

EXEMPLOS DE COMPORTAMENTO OBRIGATÓRIO (IMITA ISTO):

Pergunta: Existem docentes no departamento de Informática?
SQL: SELECT nome FROM docentes WHERE departamento LIKE '%Informática%';

Pergunta: Que áreas de contratação estão mencionadas no histórico?
SQL: SELECT DISTINCT dados_historico->>'$.area_contratacao' FROM docentes WHERE dados_historico IS NOT NULL AND dados_historico != '';

Pergunta: Qual é o tipo de contrato mais comum?
SQL: SELECT t.tipo_contrato, COUNT(*) FROM contratos c JOIN templates t ON c.templates_id_template = t.id_template GROUP BY t.tipo_contrato ORDER BY COUNT(*) DESC LIMIT 1;

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