"""
Orquestrador principal — RAG_LLM.py
Junta os três componentes (FileLoader, RAG, SQLAgent) e expõe
as funções `inicializar_rag` e `responder_pergunta`.
"""

import os
import re
import warnings
import torch
import unicodedata

from llama_cpp import Llama
from langchain_community.llms import LlamaCpp

from file_loader import carregar_documentos
from rag_component import construir_retriever, recuperar_com_foco, PASTA_TO_CHUNKS
from sql_component import criar_sql_agent, consultar_bd
from query_templates import tentar_template

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
dispositivo = "cuda" if torch.cuda.is_available() else "cpu"

# Tabelas que o SQL Agent pode consultar (lista branca de segurança)
TABELAS_SQL = ["docentes", "rascunhos", "documentos", "carga_horaria", "cursos"]


# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------

def inicializar_rag():
    """
    Inicializa os três componentes e devolve (retriever, llm, sql_agente).
    
    Returns:
        Tuple (retriever, llm, sql_agente) ou (None, None, None) em caso de erro.
    """
    print(f"[Sistema] Motor: {dispositivo.upper()}")

    # --- Componente 1: FileLoader ---
    documentos = carregar_documentos()
    if not documentos:
        print("[Sistema] Nenhum documento carregado. A abortar.")
        return None, None, None

    # --- Componente 2: RAG ---
    retriever = construir_retriever(documentos)

    # --- LLM (partilhada pelos componentes 2 e 3) ---
    model_path = os.path.join(BASE_DIR, "Qwen2.5.1-Coder-7B-Instruct-Q4_K_M.gguf")

    # LlamaCpp do LangChain (para o SQL Agent, que precisa de BaseLLM)
    llm_langchain = LlamaCpp(
        model_path=model_path,
        n_gpu_layers=-1,
        n_ctx=8192,
        temperature=0,
        verbose=False,
        stop=["<|im_end|>", ";"],
    )

    # llama-cpp nativa (para o prompt RAG final, mais controlo)
    llm_native = Llama(
        model_path=model_path,
        n_gpu_layers=-1,
        n_ctx=8192,
        verbose=False,
    )

    # --- Componente 3: SQL Agent ---
    sql_agente = criar_sql_agent(llm_langchain, tabelas_permitidas=TABELAS_SQL)

    print("[Sistema] Inicialização completa.")
    return retriever, llm_native, sql_agente


# ---------------------------------------------------------------------------
# Utilitários de extração
# ---------------------------------------------------------------------------

def _extrair_nome(pergunta: str) -> str | None:
    """Extrai um nome próprio composto da pergunta."""
    match = re.search(
        r'(?:da|de|do|d[ae])?\s*([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)+)',
        pergunta
    )
    if match:
        return match.group(1).strip()

    # Fallback: procura por nome de pasta em minúsculas
    pergunta_lower = pergunta.lower()
    for pasta in PASTA_TO_CHUNKS:
        if pasta.startswith("Contrato_"):
            nome = pasta.replace("Contrato_", "").replace("_", " ").lower()
            if nome and nome in pergunta_lower:
                return pasta.replace("Contrato_", "").replace("_", " ")
    return None

def remover_acentos(texto: str) -> str:
    """Remove acentos de uma string para garantir match nas pastas."""
    if not texto: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', texto)
                  if unicodedata.category(c) != 'Mn')

def _encontrar_pasta(nome: str) -> str | None:
    """Encontra a pasta 'Contrato_*' correspondente ao nome dado (ignorando acentos)."""
    nome_norm = remover_acentos(nome).replace(" ", "_").lower()
    for pasta in PASTA_TO_CHUNKS:
        pasta_norm = remover_acentos(pasta).lower()
        if nome_norm in pasta_norm:
            return pasta
    return None

def _formatar_contexto_docs(docs) -> str:
    partes = []
    for d in docs:
        fonte  = d.metadata.get("source", "?")
        pasta  = d.metadata.get("pasta", "Geral")
        period = d.metadata.get("periodo", "Desconhecido")
        partes.append(f"[Ficheiro: {fonte} | Pasta: {pasta} | Período: {period}]\n{d.page_content}\n")
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# Resposta principal
# ---------------------------------------------------------------------------

def responder_pergunta(
    pergunta: str,
    retriever,
    llm,
    sql_agente,
) -> tuple[str, str]:
    """
    Orquestra os três componentes para responder a uma pergunta:
      1. Componente 3 (SQL Agent): tenta obter dados estruturados da BD.
      2. Componente 2 (RAG): recupera documentos relevantes.
      3. LLM: gera a resposta final com todo o contexto combinado.
    
    Returns:
        Tuple (resposta, contexto_docs_usado).
    """

    # --- Extração de entidades ---
    nome_pessoa  = _extrair_nome(pergunta)
    pasta_forçada = _encontrar_pasta(nome_pessoa) if nome_pessoa else None
    anos = re.findall(r'\b(20\d{2}(?:/\d{2,4})?)\b', pergunta)

    # --- Componente 3: SQL Agent ---
    info_sql = tentar_template(pergunta)          # rápido, sem LLM
    if not info_sql:
        info_sql = consultar_bd(pergunta, sql_agente)  # fallback com LLM

    # --- Componente 2: RAG ---
    docs = recuperar_com_foco(pergunta, retriever, nome_pasta=pasta_forçada)
    if not docs and not info_sql:
        return "Não encontrei documentos ou registos sobre isso.", ""

    contexto_docs = _formatar_contexto_docs(docs)

    # --- Contexto combinado ---
    conhecimento = ""
    if info_sql:
        conhecimento += f"Informação da base de dados:\n{info_sql}\n\n"
    if contexto_docs:
        conhecimento += f"Informação dos documentos:\n{contexto_docs}\n\n"
    if not conhecimento:
        conhecimento = "Não possuis qualquer informação disponível sobre este assunto."

    #breach de segurança
    if "Alerta de Segurança:" in conhecimento:
        print("[Orquestrador] Curto-circuito devido a alerta de segurança. LLM abortada.")
        return "Alerta de Segurança: A inserção de código SQL direto não é permitida. Por favor, formule a sua questão em linguagem natural.", ""
    instrucao = ""
    # --- Prompt final ---
    prompt = f"""<|im_start|>system
És o Gest.AI, um assistente de recursos humanos e gestão académica.
Responde de forma natural, direta e profissional.

REGRA 1: Usa APENAS o conhecimento abaixo. Nunca inventes dados.
REGRA 2: Se a resposta vier dos documentos, cita o nome do ficheiro.
REGRA 3: SÓ podes dizer "De acordo com a base de dados" se a informação vier explicitamente do bloco "--- DADOS DA BASE DE DADOS ---". Se vier dos documentos, SÓ podes citar o nome do ficheiro.
REGRA 4: Prioriza sempre os dados da base de dados sobre os documentos em caso de conflito. NO ENTANTO, se os documentos fornecerem detalhes mais específicos e complementares que não contradigam a base de dados (ex: a base de dados diz a área, mas os documentos dizem o nome exato da cadeira), funde as duas informações numa resposta rica.
REGRA 5: Se houver dados para vários anos letivos, distingue-os claramente.
REGRA 6: Se a pergunta mencionar um nome específico, foca-te prioritariamente nos documentos relacionados com esse nome (ex: "Contrato_João_Silva").
REGRA 7: Quando fizeres querys às tabelas, verifica todas as tabelas a que fazes querys para teres respostas completas. Não respondas a meio do query.
REGRA 8: NUNCA inventes informações, colunas ou relações que não estejam expressamente escritas nas informações abaixo.
REGRA 9: Se as informações abaixo contiverem a frase "Não possuis qualquer informação", "0 linhas encontradas" ou "Sem dados estruturados", tens OBRIGATORIAMENTE de responder: "Não encontrei documentos ou registos na base de dados para responder a essa pergunta."
REGRA 10: NUNCA tentes adivinhar a resposta usando o teu conhecimento geral

[CONHECIMENTO]
{conhecimento}
[FIM DO CONHECIMENTO]

{instrucao}
<|im_end|>
<|im_start|>user
{pergunta}
<|im_end|>
<|im_start|>assistant
"""

    try:
        raw = llm(prompt, max_tokens=768, temperature=0.1, stop=["<|im_end|>"])
        resposta = raw["choices"][0]["text"].strip()
    except Exception as e:
        return f"Erro ao gerar resposta: {e}", ""

    # Adiciona fontes usadas
    ###if pasta_forçada:
        fontes = list({d.metadata.get("source", "?") for d in docs if d.metadata.get("pasta") == pasta_forçada})
        if fontes:
            fontes_str = ", ".join(fontes)
            if f"*(Fonte: {fontes_str})*" not in resposta:
                resposta += f"\n\n*(Fonte: {fontes_str})*"###

    return resposta, contexto_docs
