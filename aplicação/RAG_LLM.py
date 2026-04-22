import os
import torch
import warnings
import pdfplumber
import sqlite3
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

# Variável global para mapear pasta -> lista de chunks (usado na resposta)
PASTA_TO_CHUNKS = defaultdict(list)

def ler_documentos_via_sqlite():
    """Liga-se ao SQLite e obtém documentos, extraindo o nome da pasta."""
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
        print(f"[!] Erro SQLite: {e}")
        return []

    print(f"[*] Encontrados {len(registos)} documentos na BD.")

    for registo in registos:
        caminho_db = registo["caminho"]
        nome_doc = registo["nome"]
        categoria = registo["categoria"]
        
        # Constrói caminho absoluto
        caminho_ficheiro = os.path.join(ROOT_DIR, caminho_db).replace('\\', '/')
        if not os.path.exists(caminho_ficheiro):
            caminho_ficheiro = os.path.join(BASE_DIR, caminho_db).replace('\\', '/')
            if not os.path.exists(caminho_ficheiro):
                print(f"[Aviso] '{nome_doc}' não encontrado em: {caminho_ficheiro}")
                continue

        # Extrai o nome da pasta (diretório pai do ficheiro)
        caminho_obj = Path(caminho_ficheiro)
        nome_pasta = caminho_obj.parent.name
        print(f"[DEBUG] Processando: {nome_doc} | Pasta: {nome_pasta}")

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
    # Mostrar pastas distintas
    pastas = set(doc.metadata.get('pasta', 'SEM_PASTA') for doc in documentos_langchain)
    print(f"[*] Pastas encontradas: {', '.join(pastas)}")
    for doc in documentos_langchain[:5]:
        print(f"   - {doc.metadata.get('source')} (pasta: {doc.metadata.get('pasta')}) ({len(doc.page_content)} chars)")
    return documentos_langchain


def inicializar_rag():
    """Inicializa o sistema RAG e cria o mapeamento pasta->chunks."""
    global PASTA_TO_CHUNKS
    print(f"[*] Motor: {dispositivo.upper()}")
    
    docs = ler_documentos_via_sqlite()
    if not docs:
        print("[!] Nenhum documento carregado.")
        return None, None

    print(f"[*] Total documentos: {len(docs)}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=4000,
        chunk_overlap=800,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = splitter.split_documents(docs)
    print(f"[*] Chunks criados: {len(chunks)}")

    # Construir mapeamento pasta -> chunks (para uso na resposta)
    PASTA_TO_CHUNKS.clear()
    for chunk in chunks:
        pasta = chunk.metadata.get('pasta', 'SEM_PASTA')
        PASTA_TO_CHUNKS[pasta].append(chunk)
    print(f"[*] Mapeamento de pastas: {len(PASTA_TO_CHUNKS)} pastas únicas")

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
    
    # Retriever com k alto para ter mais hipóteses
    retriever = db.as_retriever(search_kwargs={"k": 20, "fetch_k": 40})
    return retriever, HuggingFacePipeline(pipeline=pipe)


def responder_pergunta(pergunta, retriever, llm):
    global PASTA_TO_CHUNKS
    
    # Extrair nome da pessoa
    nome_pessoa = None
    match = re.search(r'(?:da|de|do|d[ae])\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', pergunta, re.IGNORECASE)
    if match:
        nome_pessoa = match.group(1).strip()
    if not nome_pessoa:
        match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})', pergunta)
        if match:
            nome_pessoa = match.group(1).strip()
    
    print(f"[DEBUG] Nome extraído: {nome_pessoa}")
    
    docs_rel = retriever.invoke(pergunta)
    
    pasta_forcada = None
    if nome_pessoa:
        pasta_esperada = f"Contrato_{nome_pessoa.replace(' ', '_')}"
        for pasta in PASTA_TO_CHUNKS.keys():
            if pasta_esperada.lower() in pasta.lower() or nome_pessoa.lower() in pasta.lower():
                pasta_forcada = pasta
                break
        if pasta_forcada:
            print(f"[DEBUG] Forçando inclusão de {len(PASTA_TO_CHUNKS[pasta_forcada])} chunks da pasta '{pasta_forcada}'")
            chunks_adicionais = PASTA_TO_CHUNKS[pasta_forcada]
            existing = {(d.page_content, d.metadata.get('source')) for d in docs_rel}
            for chunk in chunks_adicionais:
                key = (chunk.page_content, chunk.metadata.get('source'))
                if key not in existing:
                    docs_rel.append(chunk)
                    existing.add(key)
    
    if not docs_rel:
        return "Não encontrei documentos relevantes.", ""
    
    # Ordenar: primeiro os da pasta forçada
    if pasta_forcada:
        docs_rel = sorted(docs_rel, key=lambda d: 0 if d.metadata.get('pasta') == pasta_forcada else 1)
    
    docs_rel = docs_rel[:8]
    
    # Construir contexto
    contexto_parts = []
    fontes_unicas = set()
    for i, d in enumerate(docs_rel, 1):
        fonte = d.metadata.get('source', '?')
        pasta = d.metadata.get('pasta', '?')
        page = d.metadata.get('page', '')
        page_info = f" [pág {page}]" if page else ""
        fontes_unicas.add(fonte)
        conteudo = d.page_content
        bloco = f"[DOC {i}] PASTA: {pasta} | {fonte}{page_info}\n{conteudo}\n"
        contexto_parts.append(bloco)
    contexto = "\n".join(contexto_parts)
    
    # Prompt com ênfase em ignorar outras pastas
    instrucao = ""
    if pasta_forcada:
        instrucao = f"Ignore completamente qualquer documento que NÃO pertença à pasta '{pasta_forcada}'. Use APENAS os documentos dessa pasta."
    
        prompt = f"""<|im_start|>system
Você é um assistente jurídico. Responda APENAS com uma das duas palavras: "Parcial" ou "Integral".
Não escreva mais nada, nem frases, nem pontuação, nem fontes. Apenas a palavra.
Se a informação não estiver nos documentos, responda "Não sei".
<|im_end|>
<|im_start|>user
Com base nos documentos abaixo, responda com uma única palavra: o contrato da pessoa mencionada é a tempo parcial ou integral?

DOCUMENTOS:
{contexto}

PERGUNTA: {pergunta}
<|im_end|>
<|im_start|>assistant
"""
    resposta_raw = llm.invoke(prompt)
    resposta = resposta_raw.replace("<|im_end|>", "").strip()
    
    # Limpeza: garantir que só fica a palavra esperada
    if "parcial" in resposta.lower():
        resposta = "Parcial"
    elif "integral" in resposta.lower():
        resposta = "Integral"
    elif "não sei" in resposta.lower() or "não sei" in resposta.lower():
        resposta = "Não sei"
    else:
        resposta = "Não sei"
    
    # Adicionar a fonte mais relevante (apenas uma, da pasta forçada)
    if pasta_forcada:
        # Escolhe o primeiro documento da pasta forçada (ou o que tiver "proposta" ou "necessidade")
        docs_filtrados = [d for d in docs_rel if d.metadata.get('pasta') == pasta_forcada]
        if docs_filtrados:
            melhor_fonte = docs_filtrados[0].metadata.get('source', '?')
            # Se houver algum com "Proposta" ou "Necessidade", prefere esse
            for d in docs_filtrados:
                nome = d.metadata.get('source', '')
                if 'proposta' in nome.lower() or 'necessidade' in nome.lower():
                    melhor_fonte = nome
                    break
            resposta += f" (Fonte: {melhor_fonte})"
    
    return resposta, contexto