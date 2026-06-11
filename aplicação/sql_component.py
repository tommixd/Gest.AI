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
from langchain_core.language_models.llms import BaseLLM
from db_config import DB_CONFIG

FEW_SHOT_PREFIX = """
És um agente SQL especializado numa base de dados de gestão de docentes.
 
Esquema resumido das relações importantes:
- docentes (id_docente, nome, tipo_docente, departamento, isJuri)
- contratos (id_contrato, numero_renovacao, data_renovacao, docentes_id_docente,
             carga_horaria_id_carga, templates_id_template, contrato_original_id)
- templates (id_template, caminho_ficheiro, tipo_contrato)
- carga_horaria (id_carga, tempo_contratual, tempo_aulas, percentagem)
- contrato_ucs (contratos_id_contrato, ucs_id, horas_atribuidas)
- ucs (id, nome, areas_estudo_id)
- areas_estudo (id, nome)
- cursos (id, nome)
- cursos_has_ucs (cursos_id, ucs_id)
- detalhes_contratados (iddetalhes_contratados, nif, morada, docentes_id_docente)
- documentos (id, nome, caminho, categoria, contratos_id_contrato, docentes_id_docente)
- rascunhos (id, nome_docente, tipo_contrato, dados_formulario, data_guardado)
 
REGRAS OBRIGATÓRIAS:
1. Usa SEMPRE LIKE '%nome%' para pesquisar nomes de docentes (nunca =).
2. Para encontrar o docente, vai SEMPRE primeiro à tabela `docentes`.
3. Usa subqueries ou JOINs explícitos — nunca assumas IDs.
4. Gera apenas SELECT — nunca INSERT, UPDATE ou DELETE.
 
Exemplos de raciocínio correto:
 
Pergunta: "Quantos contratos já celebrou o docente Michael Jackson?"
Pensamento: Preciso do id_docente de Michael Jackson e depois contar os contratos.
SQL:
  SELECT COUNT(*) AS total_contratos
  FROM contratos
  WHERE docentes_id_docente = (
      SELECT id_docente FROM docentes WHERE nome LIKE '%Michael Jackson%'
  );
 
Pergunta: "Qual o histórico de contratos do docente Michael Jackson?"
Pensamento: Quero todos os contratos com data, tipo e carga horária.
SQL:
  SELECT c.id_contrato, c.numero_renovacao, c.data_renovacao,
         t.tipo_contrato, ch.tempo_contratual, ch.percentagem
  FROM contratos c
  JOIN templates t    ON c.templates_id_template = t.id_template
  JOIN carga_horaria ch ON c.carga_horaria_id_carga = ch.id_carga
  WHERE c.docentes_id_docente = (
      SELECT id_docente FROM docentes WHERE nome LIKE '%Michael Jackson%'
  )
  ORDER BY c.data_renovacao DESC;
 
Pergunta: "Que unidades curriculares tem o docente Michael Jackson no contrato mais recente?"
Pensamento: Preciso do contrato mais recente e depois as UCs associadas via contrato_ucs.
SQL:
  SELECT u.nome AS uc, cu.horas_atribuidas
  FROM contrato_ucs cu
  JOIN ucs u ON cu.ucs_id = u.id
  WHERE cu.contratos_id_contrato = (
      SELECT id_contrato FROM contratos
      WHERE docentes_id_docente = (
          SELECT id_docente FROM docentes WHERE nome LIKE '%Michael Jackson%'
      )
      ORDER BY data_renovacao DESC LIMIT 1
  );
 
Pergunta: "Que docentes são do departamento de Informática?"
Pensamento: Filtro direto na tabela docentes.
SQL:
  SELECT nome, tipo_docente FROM docentes
  WHERE departamento LIKE '%Informática%';
 
Pergunta: "Quantas renovações tem o contrato original do docente Michael Jackson?"
Pensamento: O contrato original tem contrato_original_id = NULL; renovações têm o id do original.
SQL:
  SELECT COUNT(*) AS total_renovacoes
  FROM contratos
  WHERE contrato_original_id = (
      SELECT id_contrato FROM contratos
      WHERE docentes_id_docente = (
          SELECT id_docente FROM docentes WHERE nome LIKE '%Michael Jackson%'
      )
      AND contrato_original_id IS NULL
      LIMIT 1
  );
 
Pergunta: "Quais os documentos associados ao docente Michael Jackson?"
Pensamento: Tabela documentos tem docentes_id_docente diretamente.
SQL:
  SELECT nome, categoria, data_upload
  FROM documentos
  WHERE docentes_id_docente = (
      SELECT id_docente FROM docentes WHERE nome LIKE '%Michael Jackson%'
  )
  ORDER BY data_upload DESC;
"""
 

def _criar_uri_mysql() -> str:
    """Constrói a URI de ligação MySQL para o SQLAlchemy."""
    return (
        f"mysql+mysqlconnector://"
        f"{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    )

TABELAS_PERMITIDAS = [
    "docentes", "contratos", "templates", "carga_horaria",
    "contrato_ucs", "ucs", "areas_estudo", "cursos", "cursos_has_ucs",
    "detalhes_contratados", "documentos", "rascunhos",
]

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
