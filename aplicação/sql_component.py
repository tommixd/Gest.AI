"""
Componente 3: SQL Agent (Text-to-SQL nativo com LangChain)
Responsabilidade única: receber uma pergunta em linguagem natural
e devolver os dados relevantes da BD, usando o SQLDatabaseChain
ou create_sql_agent do LangChain — sem implementar o loop manualmente.

Vantagens vs. a abordagem manual:
  - Retry automático quando o SQL falha
  - Valida o SQL contra o esquema real antes de executar
  - Apenas SELECTs são permitidos via `include_tables` + modo read-only
"""

from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_core.language_models.llms import BaseLLM
from db_config import DB_CONFIG


def _criar_uri_mysql() -> str:
    """Constrói a URI de ligação MySQL para o SQLAlchemy."""
    return (
        f"mysql+mysqlconnector://"
        f"{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    )


def criar_sql_agent(llm: BaseLLM, tabelas_permitidas: list[str] | None = None):
    """
    Cria e devolve um agente SQL LangChain pronto a usar.
    
    Args:
        llm:                Instância da LLM (LlamaCpp ou compatível).
        tabelas_permitidas: Lista de tabelas que o agente pode consultar.
                            Se None, usa todas as tabelas da BD.
    
    Returns:
        Um AgentExecutor do LangChain configurado para Text-to-SQL seguro.
    
    Exemplo de uso:
        agente = criar_sql_agent(llm, tabelas_permitidas=["docentes", "rascunhos"])
        resultado = agente.invoke({"input": "Quantos docentes existem?"})
        print(resultado["output"])
    """

    prefixo_customizado = """
    És um agente SQL que consulta a base de dados de uma universidade.
    DICAS IMPORTANTES:
    - Se perguntarem por "cadeiras", "disciplinas" ou o que um professor "leciona", deves consultar a coluna 'dados_historico' na tabela 'docentes', ou procurar na tabela 'carga_horaria'.
    - Nunca faças UPDATE, DELETE ou DROP. Apenas SELECT.
    """
    
    uri = _criar_uri_mysql()

    # include_tables limita o acesso às tabelas definidas (segurança)
    db = SQLDatabase.from_uri(
        uri,
        include_tables=tabelas_permitidas,
        sample_rows_in_table_info=2,   # Mostra 2 exemplos por tabela ao modelo
    )

    agente = create_sql_agent(
        llm=llm,
        db=db,
        agent_type="zero-shot-react-description",
        verbose=True,
        # Limita iterações para evitar loops infinitos com modelos locais
        prefix=prefixo_customizado,
        max_iterations=5,
        max_execution_time=30,
        handle_parsing_errors=True,
    )

    print(f"[SQLAgent] Agente criado. Tabelas: {tabelas_permitidas or 'todas'}")
    return agente


def consultar_bd(pergunta: str, agente) -> str:
    """
    Executa uma pergunta em linguagem natural contra a BD.
    
    Args:
        pergunta: Pergunta do utilizador (ex: "Quantos docentes existem?").
        agente:   Agente criado por `criar_sql_agent`.
    
    Returns:
        Resposta em texto com os dados encontrados.
    """
    try:
        resultado = agente.invoke({"input": pergunta})
        return resultado.get("output", "Sem resposta do agente SQL.")
    except Exception as e:
        return f"[SQLAgent] Erro: {e}"
