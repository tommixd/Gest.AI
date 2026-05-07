import os
import torch
import warnings
import pdfplumber
import mysql.connector
import re
from pathlib import Path
from collections import defaultdict
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings, HuggingFacePipeline
from langchain_community.vectorstores import FAISS
from transformers import pipeline
from docx import Document as DocxDocument

warnings.filterwarnings("ignore")
dispositivo = "cuda" if torch.cuda.is_available() else "cpu"

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
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(BASE_DIR)
    
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
        nome_pasta = caminho_obj.parent.name

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
                            "pasta": nome_pasta
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
                                    "pasta": nome_pasta
                                }
                            ))
        except Exception as e:
            print(f"[!] Erro ao processar {nome_doc}: {e}")

    print(f"[*] Documentos carregados: {len(documentos_langchain)}")
    return documentos_langchain


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
        chunk_overlap=800,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = splitter.split_documents(docs)

    PASTA_TO_CHUNKS.clear()
    for chunk in chunks:
        pasta = chunk.metadata.get('pasta', 'SEM_PASTA')
        PASTA_TO_CHUNKS[pasta].append(chunk)

    print("[*] A carregar embeddings...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={'device': dispositivo}
    )
    
    db = FAISS.from_documents(chunks, embeddings)
    
    print("[*] A carregar Qwen2.5-3B...")
    model_id = "unsloth/Qwen2.5-3B-Instruct-bnb-4bit"
    
    pipe = pipeline(
        "text-generation",
        model=model_id,
        model_kwargs={"dtype": torch.float16, "low_cpu_mem_usage": True},
        max_new_tokens=512,
        temperature=0.4,
        top_p=0.9,
        do_sample=True,
        repetition_penalty=1.15,
        device_map="auto",
        return_full_text=False
    )
    
    retriever = db.as_retriever(search_kwargs={"k": 5, "fetch_k": 10})
    return retriever, HuggingFacePipeline(pipeline=pipe)


def responder_pergunta(pergunta, retriever, llm):
    global PASTA_TO_CHUNKS
    
    # 1. Extrair nome da pessoa (AGORA SUPORTA ACENTOS E CARACTERES PORTUGUESES)
    nome_pessoa = None
    match = re.search(r'(?:da|de|do|d[ae])\s+([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)*)', pergunta, re.IGNORECASE)
    if match:
        nome_pessoa = match.group(1).strip()
    if not nome_pessoa:
        match = re.search(r'([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+){1,2})', pergunta)
        if match:
            nome_pessoa = match.group(1).strip()
            
    print(f"[DEBUG] Nome extraído: {nome_pessoa}")
    
    # 2. Pesquisar dinamicamente na Base de Dados por Rascunhos
    info_bd = ""
    if nome_pessoa:
        try:
            db = mysql.connector.connect(**DB_CONFIG)
            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT * FROM rascunhos WHERE nome_docente LIKE %s", (f"%{nome_pessoa}%",))
            rascunho = cursor.fetchone()
            cursor.close()
            db.close()
            
            if rascunho:
                info_bd = f"O processo de {rascunho['nome_docente']} encontra-se guardado como um RASCUNHO (Incompleto) do tipo '{rascunho['tipo_contrato']}'."
                print(f"[DEBUG] Rascunho encontrado para: {nome_pessoa}")
        except Exception as e:
            print(f"[!] Erro ao consultar BD para rascunhos: {e}")

    # 3. Processar RAG (PDFs/Docs)
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
    
    # Ordenar: primeiro os da pasta forçada
    if pasta_forcada:
        docs_rel = sorted(docs_rel, key=lambda d: 0 if d.metadata.get('pasta') == pasta_forcada else 1)
    
    docs_rel = docs_rel[:8]
    
    contexto_parts = []
    for i, d in enumerate(docs_rel, 1):
        fonte = d.metadata.get('source', '?')
        conteudo = d.page_content
        contexto_parts.append(f"[Documento: {fonte}]\n{conteudo}\n")
    contexto = "\n".join(contexto_parts)
    
    # 4. Construção Orgânica do Conhecimento
    conhecimento_sistema = ""
    if info_bd:
        conhecimento_sistema += f"Informação atual dos Rascunhos:\n{info_bd}\n\n"
    if contexto:
        conhecimento_sistema += f"Informação extraída dos Documentos do processo:\n{contexto}\n\n"
    if not conhecimento_sistema:
        conhecimento_sistema = "Não possuis qualquer informação no momento sobre este assunto."

    instrucao = ""
    if pasta_forcada:
        instrucao = f"Se a pergunta exigir analisar documentos, foca-te na informação da pasta '{pasta_forcada}'."

    # 5. Prompt Dinâmico (Livre de camisa de forças)
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
    
    # 6. Invocar a IA
    try:
        resposta_raw = llm.invoke(prompt)
        resposta = resposta_raw.replace("<|im_end|>", "").strip()
    except Exception as e:
        return f"Erro ao gerar resposta da IA: {e}", ""
    
    # Opcional: Adicionar a fonte discretamente no final
    if pasta_forcada and "rascunho" not in resposta.lower() and "incompleto" not in resposta.lower():
        docs_filtrados = [d for d in docs_rel if d.metadata.get('pasta') == pasta_forcada]
        if docs_filtrados:
            melhor_fonte = docs_filtrados[0].metadata.get('source', '?')
            resposta += f"\n\n*(Fonte: {melhor_fonte})*"
            
    return resposta, contexto