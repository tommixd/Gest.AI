"""
Componente 2: RAG (Retrieval-Augmented Generation)
Responsabilidade única: receber documentos, criar embeddings + índice FAISS
e expor um retriever LangChain.

Também mantém o mapeamento pasta → chunks para forçar contexto por docente.
"""

from collections import defaultdict
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.vectorstores import VectorStoreRetriever


# Mapeamento global pasta → chunks (usado externamente para forçar contexto)
PASTA_TO_CHUNKS: dict[str, list[Document]] = defaultdict(list)


def construir_retriever(
    documentos: list[Document],
    chunk_size: int = 800,
    chunk_overlap: int = 150,
    k: int = 5,
    fetch_k: int = 20,
) -> VectorStoreRetriever:
    """
    Divide os documentos em chunks, cria embeddings multilingues
    e devolve um retriever FAISS pronto a usar.
    
    Args:
        documentos:    Lista de LangChain Documents do FileLoader.
        chunk_size:    Tamanho máximo de cada chunk em caracteres.
        chunk_overlap: Sobreposição entre chunks consecutivos.
        k:             Número de documentos a devolver por query.
        fetch_k:       Pool candidatos antes do ranking final.
    
    Returns:
        Um VectorStoreRetriever configurado.
    """
    global PASTA_TO_CHUNKS
    PASTA_TO_CHUNKS.clear()

    # --- Divisão em chunks ---
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_documents(documentos)

    # Preenche o mapa pasta → chunks para uso externo
    for chunk in chunks:
        pasta = chunk.metadata.get("pasta", "SEM_PASTA")
        PASTA_TO_CHUNKS[pasta].append(chunk)

    print(f"[RAG] {len(chunks)} chunks criados de {len(documentos)} documentos.")

    # --- Embeddings multilingues (CPU para poupar VRAM) ---
    print("[RAG] A carregar embeddings...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        model_kwargs={"device": "cpu"},
    )

    # --- Índice FAISS ---
    vectorstore = FAISS.from_documents(chunks, embeddings)
    retriever = vectorstore.as_retriever(
        search_kwargs={"k": k, "fetch_k": fetch_k}
    )

    print("[RAG] Índice FAISS criado.")
    return retriever


def recuperar_com_foco(
    pergunta: str,
    retriever: VectorStoreRetriever,
    nome_pasta: str | None = None,
    top_k: int = 10,
) -> list[Document]:
    """
    Faz a retrieval semântica e, opcionalmente, força a inclusão
    de todos os chunks da pasta de um docente específico.

    Args:
        pergunta:   Texto da pergunta do utilizador.
        retriever:  Retriever criado por `construir_retriever`.
        nome_pasta: Se fornecido, força a inclusão dos chunks desta pasta.
        top_k:      Número máximo de documentos no resultado final.

    Returns:
        Lista de Documents ordenada por relevância.
    """
    import re

    docs = retriever.invoke(pergunta)

    if nome_pasta and nome_pasta in PASTA_TO_CHUNKS:
        existing = {(d.page_content, d.metadata.get("source")) for d in docs}
        for chunk in PASTA_TO_CHUNKS[nome_pasta]:
            key = (chunk.page_content, chunk.metadata.get("source"))
            if key not in existing:
                docs.append(chunk)
                existing.add(key)

        # Ordena: pasta forçada primeiro, depois por período (mais recente)
        docs = sorted(docs, key=lambda d: (
            0 if d.metadata.get("pasta") == nome_pasta else 1,
            -int(re.search(r"\d+", d.metadata.get("periodo", "0")).group())
            if re.search(r"\d+", d.metadata.get("periodo", ""))
            else 0,
        ))

    return docs[:top_k]
