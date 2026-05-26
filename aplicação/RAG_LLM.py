import os
import torch
import warnings
import pdfplumber
import mysql.connector
import re
from pathlib import Path
from db_config import DB_CONFIG
from collections import defaultdict
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from docx import Document as DocxDocument

# NOVO IMPORT PARA O MOTOR GGUF DA NVIDIA/RTX 4060
from llama_cpp import Llama

warnings.filterwarnings("ignore")
dispositivo = "cuda" if torch.cuda.is_available() else "cpu"

# Definir caminhos base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

# --- CONFIGURAÇÃO DA BASE DE DADOS MYSQL ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',            
    'password': '04072002Tomas!', 
    'database': 'BaseDadosGestAI' 
}

# Variável global para mapear pasta -> lista de chunks (usado na resposta)
PASTA_TO_CHUNKS = defaultdict(list)

def ler_documentos_via_mysql():
    """Liga-se ao MySQL e obtém documentos, extraindo o nome da pasta."""
    
    documentos_langchain = []
    
    try:
        ligacao = mysql.connector.connect(**DB_CONFIG)
        cursor = ligacao.cursor(dictionary=True)
        cursor.execute("SELECT nome, caminho, categoria FROM documentos")
        registos = cursor.fetchall()
        cursor.close()
        ligacao.close()
    except Exception as e:
        print(f"[!] Erro MySQL: {e}")
        return []

    print(f"[*] Encontrados {len(registos)} documentos na BD.")

    for registo in registos:
        caminho_db = registo["caminho"]
        nome_doc = registo["nome"]
        categoria = registo["categoria"]
        
        caminho_ficheiro = os.path.join(ROOT_DIR, caminho_db).replace('\\', '/')
        if not os.path.exists(caminho_ficheiro):
            caminho_ficheiro = os.path.join(BASE_DIR, caminho_db).replace('\\', '/')
            if not os.path.exists(caminho_ficheiro):
                print(f"[Aviso] '{nome_doc}' não encontrado em: {caminho_ficheiro}")
                continue

        caminho_obj = Path(caminho_ficheiro)
        # Estrutura: Contrato_Name/2025-2026/ficheiro.docx
        # parent = 2025-2026, parent.parent = Contrato_Name
        periodo = caminho_obj.parent.name
        nome_pasta = caminho_obj.parent.parent.name  # obtém o nome do contrato (ex: Contrato_Helena_Pinto)

        try:
            if caminho_ficheiro.lower().endswith(".docx"):
                doc_word = DocxDocument(caminho_ficheiro)
                texto = "\n".join([p.text for p in doc_word.paragraphs if p.text.strip()])
                if texto.strip():
                    documentos_langchain.append(Document(
                        page_content=texto, 
                        metadata={
                            "source": nome_doc,
                            "categoria": categoria,
                            "tipo": "docx",
                            "pasta": nome_pasta,
                            "periodo": periodo
                        }
                    ))

            elif caminho_ficheiro.lower().endswith(".pdf"):
                with pdfplumber.open(caminho_ficheiro) as pdf:
                    for num_p, page in enumerate(pdf.pages):
                        texto = page.extract_text() or ""
                        if texto.strip():
                            documentos_langchain.append(Document(
                                page_content=texto, 
                                metadata={
                                    "source": nome_doc,
                                    "categoria": categoria,
                                    "page": num_p + 1,
                                    "tipo": "pdf",
                                    "pasta": nome_pasta,
                                    "periodo": periodo
                                }
                            ))
        except Exception as e:
            print(f"[!] Erro ao processar {nome_doc}: {e}")

    print(f"[*] Documentos carregados: {len(documentos_langchain)}")
    return documentos_langchain


def obter_tabelas_com_coluna_nome_docente():
    """Retorna as tabelas que contêm a coluna nome_docente na BD atual."""
    try:
        db = mysql.connector.connect(**DB_CONFIG)
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND column_name = 'nome_docente'
            """,
            (DB_CONFIG['database'],)
        )
        tabelas = [row[0] for row in cursor.fetchall()]
        cursor.close()
        db.close()
        return tabelas
    except Exception as e:
        print(f"[!] Erro ao obter tabelas com nome_docente: {e}")
        return []


def buscar_registos_por_nome(nome_pessoa):
    """Procura em todas as tabelas com nome_docente e devolve registos encontrados."""
    resultados = []
    tabelas = obter_tabelas_com_coluna_nome_docente()
    if not tabelas:
        return resultados

    try:
        db = mysql.connector.connect(**DB_CONFIG)
        cursor = db.cursor(dictionary=True)
        for tabela in tabelas:
            try:
                cursor.execute(
                    f"SELECT * FROM `{tabela}` WHERE nome_docente LIKE %s LIMIT 5",
                    (f"%{nome_pessoa}%",)
                )
                for registo in cursor.fetchall():
                    resultados.append({
                        'tabela': tabela,
                        'registo': registo
                    })
            except Exception as sub_e:
                print(f"[!] Erro ao consultar {tabela}: {sub_e}")
        cursor.close()
        db.close()
    except Exception as e:
        print(f"[!] Erro ao conectar à BD para buscar registos: {e}")

    return resultados


def formatar_registo_bd(tabela, registo):
    """Formata um registo para texto compacto no prompt."""
    campos = []
    for chave, valor in registo.items():
        if valor is None:
            continue
        campos.append(f"{chave}={valor}")
        if len(campos) >= 6:
            break
    return f"[{tabela}] " + ", ".join(campos)


def inicializar_rag():
    """Inicializa o sistema RAG e cria o mapeamento pasta->chunks."""
    global PASTA_TO_CHUNKS
    print(f"[*] Motor: {dispositivo.upper()}")
    
    docs = ler_documentos_via_mysql()
    if not docs:
        print("[!] Nenhum documento carregado.")
        return None, None

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=300,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = splitter.split_documents(docs)

    PASTA_TO_CHUNKS.clear()
    for chunk in chunks:
        pasta = chunk.metadata.get('pasta', 'SEM_PASTA')
        PASTA_TO_CHUNKS[pasta].append(chunk)

    print("[*] A carregar embeddings no CPU para poupar VRAM...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={'device': 'cpu'}
    )
    
    db = FAISS.from_documents(chunks, embeddings)
    
    # --- NOVO BLOCO GGUF PARA A RTX 4060 ---
    print("[*] A carregar Qwen2.5-Coder-7B GGUF...")
    model_path = os.path.join(BASE_DIR, "Qwen2.5.1-Coder-7B-Instruct-Q4_K_M.gguf")
    llm = Llama(
        model_path=model_path, # Caminho absoluto baseado no diretório do script
        n_gpu_layers=-1, 
        n_ctx=4096,      
        verbose=True    
    )
    
    retriever = db.as_retriever(search_kwargs={"k": 2, "fetch_k": 10})
    return retriever, llm


def responder_pergunta(pergunta, retriever, llm):
    global PASTA_TO_CHUNKS
    
    nome_pessoa = None
    match = re.search(r'(?:da|de|do|d[ae])\s+([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)*)', pergunta, re.IGNORECASE)
    if match:
        nome_pessoa = match.group(1).strip()
    if not nome_pessoa:
        match = re.search(r'([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+){1,2})', pergunta)
        if match:
            nome_pessoa = match.group(1).strip()
            
    print(f"[DEBUG] Nome extraído: {nome_pessoa}")
    
    info_bd = ""
    if nome_pessoa:
        registos_bd = buscar_registos_por_nome(nome_pessoa)
        if registos_bd:
            info_partes = []
            for item in registos_bd:
                texto_registo = formatar_registo_bd(item['tabela'], item['registo'])
                info_partes.append(texto_registo)
                if item['tabela'] == 'rascunhos':
                    rascunho = item['registo']
                    info_partes.append(
                        f"O processo de {rascunho.get('nome_docente')} encontra-se guardado como um RASCUNHO (Incompleto) do tipo '{rascunho.get('tipo_contrato')}'."
                    )
                    print(f"[DEBUG] Rascunho encontrado para: {nome_pessoa}")

            info_bd = "\n".join(info_partes)
        else:
            print(f"[DEBUG] Nenhum registo encontrado em tabelas com nome_docente para: {nome_pessoa}")

    docs_rel = retriever.invoke(pergunta)
    
    pasta_forcada = None
    if nome_pessoa:
        pasta_esperada = f"Contrato_{nome_pessoa.replace(' ', '_')}"
        for pasta in PASTA_TO_CHUNKS.keys():
            if pasta_esperada.lower() in pasta.lower() or nome_pessoa.lower() in pasta.lower():
                pasta_forcada = pasta
                break
        if pasta_forcada:
            chunks_adicionais = PASTA_TO_CHUNKS[pasta_forcada]
            existing = {(d.page_content, d.metadata.get('source')) for d in docs_rel}
            for chunk in chunks_adicionais:
                key = (chunk.page_content, chunk.metadata.get('source'))
                if key not in existing:
                    docs_rel.append(chunk)
                    existing.add(key)
    
    if not docs_rel and not info_bd:
        return "Não encontrei documentos ou registos na base de dados sobre isso.", ""
    
    if pasta_forcada:
        docs_rel = sorted(docs_rel, key=lambda d: 0 if d.metadata.get('pasta') == pasta_forcada else 1)
    
    docs_rel = docs_rel[:8]
    
    contexto_parts = []
    for i, d in enumerate(docs_rel, 1):
        fonte = d.metadata.get('source', '?')
        conteudo = d.page_content
        contexto_parts.append(f"[Documento: {fonte}]\n{conteudo}\n")
    contexto = "\n".join(contexto_parts)
    
    conhecimento_sistema = ""
    if info_bd:
        conhecimento_sistema += f"Informação atual da base de dados:\n{info_bd}\n\n"
    if contexto:
        conhecimento_sistema += f"Informação extraída dos Documentos do processo:\n{contexto}\n\n"
    if not conhecimento_sistema:
        conhecimento_sistema = "Não possuis qualquer informação no momento sobre este assunto."

    instrucao = ""
    if pasta_forcada:
        instrucao = f"Se a pergunta exigir analisar documentos, foca-te na informação da pasta '{pasta_forcada}'."

    prompt = f"""<|im_start|>system
És o Gest.AI, um assistente inteligente de recursos humanos e gestão académica.
A tua missão é responder à pergunta do utilizador de forma natural, direta e prestável.

Abaixo está a tua base de conhecimento atual sobre este caso. Usa APENAS esta informação para responder. 
Age como se este conhecimento fosse teu. Não uses frases robóticas como "De acordo com os documentos" ou "A base de dados diz". Assume os factos com naturalidade.

[INÍCIO DO CONHECIMENTO]
{conhecimento_sistema}
[FIM DO CONHECIMENTO]

{instrucao}
<|im_end|>
<|im_start|>user
{pergunta}
<|im_end|>
<|im_start|>assistant
"""
    
    # --- NOVA GERAÇÃO DE TEXTO DO LlamaCpp ---
    try:
        resposta_raw = llm(
            prompt,
            max_tokens=512,
            temperature=0.1,      # Temperatura super baixa para dados fiáveis
            stop=["<|im_end|>"]   # Diz ao modelo quando a resposta acabou
        )
        resposta = resposta_raw["choices"][0]["text"].strip()
    except Exception as e:
        return f"Erro ao gerar resposta da IA: {e}", ""
    
    if pasta_forcada and "rascunho" not in resposta.lower() and "incompleto" not in resposta.lower():
        docs_filtrados = [d for d in docs_rel if d.metadata.get('pasta') == pasta_forcada]
        if docs_filtrados:
            melhor_fonte = docs_filtrados[0].metadata.get('source', '?')
            resposta += f"\n\n*(Fonte: {melhor_fonte})*"
            
    return resposta, contexto