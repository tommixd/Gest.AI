import os
import torch
import warnings
import pdfplumber
import sqlite3
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings, HuggingFacePipeline
from langchain_community.vectorstores import FAISS
from transformers import pipeline
from docx import Document as DocxDocument

# Ocultar avisos
warnings.filterwarnings("ignore")

# Configuração do Dispositivo
dispositivo = "cuda" if torch.cuda.is_available() else "cpu"

def ler_documentos_via_sqlite():
    """Liga-se ao SQLite e obtém a lista de documentos ativos."""
    # O DATABASE deve estar na mesma pasta que este script
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATABASE = os.path.join(BASE_DIR, 'documentos.db')
    ROOT_DIR = os.path.dirname(BASE_DIR)
    
    documentos_langchain = []
    
    if not os.path.exists(DATABASE):
        print(f"[!] Erro: Base de dados não encontrada em: {DATABASE}")
        return []

    try:
        ligacao = sqlite3.connect(DATABASE)
        ligacao.row_factory = sqlite3.Row
        cursor = ligacao.cursor()
        cursor.execute("SELECT nome, caminho, categoria FROM documentos")
        registos = cursor.fetchall()
        ligacao.close()
    except Exception as e:
        print(f"[!] Erro ao ligar à base de dados SQLite: {e}")
        return []

    print(f"[*] Encontrados {len(registos)} documentos na base de dados SQLite.")

    for registo in registos:
        caminho_db = registo["caminho"]
        nome_doc = registo["nome"]
        categoria = registo["categoria"]
        
        # Resolver caminho absoluto (procura na raiz do projeto)
        caminho_ficheiro = os.path.join(ROOT_DIR, caminho_db).replace('\\', '/')
        
        if not os.path.exists(caminho_ficheiro):
            # Tenta relativo à pasta 'aplicação' se não encontrar na raiz
            caminho_ficheiro = os.path.join(BASE_DIR, caminho_db).replace('\\', '/')
            if not os.path.exists(caminho_ficheiro):
                print(f"[Aviso] Ficheiro '{nome_doc}' não encontrado em: {caminho_ficheiro}")
                continue

        try:
            if caminho_ficheiro.lower().endswith(".docx"):
                doc_word = DocxDocument(caminho_ficheiro)
                texto = "\n".join([p.text for p in doc_word.paragraphs if p.text.strip()])
                if texto.strip():
                    documentos_langchain.append(Document(page_content=texto, metadata={"source": nome_doc, "categoria": categoria}))

            elif caminho_ficheiro.lower().endswith(".pdf"):
                with pdfplumber.open(caminho_ficheiro) as pdf:
                    for num_p, page in enumerate(pdf.pages):
                        texto = page.extract_text() or ""
                        if texto.strip():
                            documentos_langchain.append(Document(page_content=texto, metadata={"source": nome_doc, "categoria": categoria, "page": num_p + 1}))
        except Exception as e:
            print(f"[!] Erro ao processar {nome_doc}: {e}")

    return documentos_langchain

def inicializar_rag():
    """Inicializa o motor RAG (Embeddings + FAISS + LLM)."""
    print(f"[*] Motor: {dispositivo.upper()} | A carregar base de conhecimento...")
    
    docs = ler_documentos_via_sqlite()
    if not docs:
        print("[!] Erro: Nenhum documento válido foi carregado.")
        return None, None

    # Divisão de texto
    splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=300)
    chunks = splitter.split_documents(docs)

    # Embeddings (Português)
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={'device': dispositivo}
    )
    
    db = FAISS.from_documents(chunks, embeddings)
    
    # Carregar LLM (Qwen 2.5 3B)
    print("[*] A carregar Qwen2.5-3B-Instruct...")
    model_id = "unsloth/Qwen2.5-3B-Instruct-bnb-4bit"
    
    pipe = pipeline(
        "text-generation",
        model=model_id,
        model_kwargs={"dtype": torch.float16, "low_cpu_mem_usage": True},
        max_new_tokens=512,
        temperature=0.1,
        do_sample=False,
        repetition_penalty=1.1,
        device_map="auto",
        return_full_text=False
    )
    
    return db.as_retriever(search_kwargs={"k": 5}), HuggingFacePipeline(pipeline=pipe)

def responder_pergunta(pergunta, retriever, llm):
    docs_rel = retriever.invoke(pergunta)
    if not docs_rel:
        return "Não encontrei documentos relevantes nos arquivos.", ""

    contexto_parts = []
    for d in docs_rel:
        fonte = d.metadata.get('source', 'Desconhecido')
        # Extraímos a categoria que o teu setup_db.py definiu (ex: 'tempo integral anual')
        categoria = d.metadata.get('categoria', 'Geral')
        
        # Criamos um bloco de contexto muito mais explícito
        bloco = (
            f"--- INFORMAÇÃO DO SISTEMA ---\n"
            f"DOCUMENTO: {fonte}\n"
            f"CLASSIFICAÇÃO DO CONTRATO: {categoria}\n"
            f"--- CONTEÚDO DO DOCUMENTO ---\n"
            f"{d.page_content}\n"
            f"----------------------------"
        )
        contexto_parts.append(bloco)

    contexto = "\n\n".join(contexto_parts)

    # Prompt mais "agressivo" para forçar a análise da classificação
    prompt = f"""<|im_start|>system
És um analista jurídico de alta precisão.
O utilizador vai perguntar sobre o regime de um contrato (parcial ou integral).
REGRAS CRÍTICAS:
1. Observa primeiro a 'CLASSIFICAÇÃO DO CONTRATO' fornecida no contexto. Essa é a classificação oficial do sistema.
2. Cruza essa classificação com o 'CONTEÚDO DO DOCUMENTO'.
3. Se a CLASSIFICAÇÃO diz 'tempo integral' e o conteúdo menciona 'integral', confirma que é integral.
4. Sê direto. Não digas que é inconclusivo se a classificação do sistema for clara.
5. Responde em Português de Portugal.<|im_end|>
<|im_start|>user
CONTEXTO DOS DOCUMENTOS:
{contexto}

PERGUNTA DO UTILIZADOR: {pergunta}<|im_end|>
<|im_start|>assistant
"""
    resposta = llm.invoke(prompt)
    return resposta.replace("<|im_end|>", "").strip(), contexto

