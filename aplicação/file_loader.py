"""
Componente 1: FileLoader
Responsabilidade única: ler documentos (.docx, .pdf) a partir dos caminhos
guardados no MySQL e devolver uma lista de LangChain Documents.
"""

import os
import pdfplumber
from pathlib import Path
from docx import Document as DocxDocument
from langchain_core.documents import Document
import mysql.connector
from db_config import DB_CONFIG


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)


def _resolver_caminho(caminho_db: str) -> str | None:
    """Tenta resolver o caminho do ficheiro a partir da raiz ou do diretório base."""
    for base in [ROOT_DIR, BASE_DIR]:
        caminho = os.path.join(base, caminho_db).replace("\\", "/")
        if os.path.exists(caminho):
            return caminho
    return None


def _extrair_nome_pasta(caminho_obj: Path) -> str:
    """Extrai o nome da pasta 'Contrato_*' a partir do caminho do ficheiro."""
    for parte in caminho_obj.parts:
        if parte.startswith("Contrato_"):
            return parte
    return "Geral"


def _ler_docx(caminho: str, metadata: dict) -> Document | None:
    doc = DocxDocument(caminho)
    texto = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if texto.strip():
        return Document(page_content=texto, metadata={**metadata, "tipo": "docx"})
    return None


def _ler_pdf(caminho: str, metadata: dict) -> list[Document]:
    docs = []
    with pdfplumber.open(caminho) as pdf:
        for num_p, page in enumerate(pdf.pages):
            texto = page.extract_text() or ""
            if texto.strip():
                docs.append(Document(
                    page_content=texto,
                    metadata={**metadata, "tipo": "pdf", "page": num_p + 1}
                ))
    return docs


def carregar_documentos() -> list[Document]:
    """
    Liga ao MySQL, obtém os registos da tabela `documentos`
    e devolve uma lista de LangChain Documents prontos a usar.
    """
    documentos = []

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT nome, caminho, categoria FROM documentos")
        registos = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[FileLoader] Erro MySQL: {e}")
        return []

    print(f"[FileLoader] {len(registos)} documentos encontrados na BD.")

    for reg in registos:
        caminho = _resolver_caminho(reg["caminho"])
        if not caminho:
            print(f"[FileLoader] Aviso: '{reg['nome']}' não encontrado.")
            continue

        caminho_obj = Path(caminho)
        metadata = {
            "source":    reg["nome"],
            "categoria": reg["categoria"],
            "pasta":     _extrair_nome_pasta(caminho_obj),
            "periodo":   caminho_obj.parent.name,
        }

        try:
            ext = caminho.lower()
            if ext.endswith(".docx"):
                doc = _ler_docx(caminho, metadata)
                if doc:
                    documentos.append(doc)
            elif ext.endswith(".pdf"):
                documentos.extend(_ler_pdf(caminho, metadata))
        except Exception as e:
            print(f"[FileLoader] Erro ao processar {reg['nome']}: {e}")

    print(f"[FileLoader] {len(documentos)} documentos carregados.")
    return documentos
