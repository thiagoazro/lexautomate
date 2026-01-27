# chroma_utils.py
# Contexto por URL usando Chroma + OpenAI Embeddings (SEM Azure)
#
# Usado para enriquecer o prompt com trechos relevantes extraídos de uma página web.
#
# Requisitos:
#   pip install python-dotenv langchain langchain-community langchain-openai chromadb beautifulsoup4 html2text
#
# .env:
#   OPENAI_API_KEY=...
#   OPENAI_EMBEDDING_MODEL=text-embedding-3-large   (opcional; default abaixo)

from __future__ import annotations

import os
import traceback
from dotenv import load_dotenv

load_dotenv()

from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_EMBEDDING_MODEL = (os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-large").strip()


def _criar_retriever_chroma_de_url(url: str, top_k_retriever: int = 3):
    """Cria um retriever Chroma em memória a partir do conteúdo de uma URL (OpenAI embeddings)."""
    try:
        if not OPENAI_API_KEY:
            print("ERRO CHROMA_UTILS: OPENAI_API_KEY não definida no .env", flush=True)
            return None

        print(f"INFO CHROMA_UTILS: Carregando URL para Chroma: {url}", flush=True)
        loader = WebBaseLoader(url, continue_on_failure=True, raise_for_status=False)
        docs = loader.load()

        if not docs:
            print(f"AVISO CHROMA_UTILS: Nenhum documento carregado da URL: {url}", flush=True)
            return None

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        chunks = splitter.split_documents(docs)

        if not chunks:
            print(f"AVISO CHROMA_UTILS: Nenhum chunk gerado da URL: {url}", flush=True)
            return None

        embeddings = OpenAIEmbeddings(
            model=OPENAI_EMBEDDING_MODEL,
            api_key=OPENAI_API_KEY,
        )

        vectorstore = Chroma.from_documents(documents=chunks, embedding=embeddings)
        print(f"INFO CHROMA_UTILS: Vectorstore Chroma criado para {url} com {len(chunks)} chunks.", flush=True)
        return vectorstore.as_retriever(search_kwargs={"k": top_k_retriever})

    except Exception as e:
        print(f"ERRO CHROMA_UTILS: Falha ao criar retriever para {url}: {e}", flush=True)
        traceback.print_exc()
        return None


def formatar_contexto_chroma_para_llm(documentos_chroma: list, url_fonte: str) -> str:
    if not documentos_chroma:
        return (
            f"\n\n--- CONTEXTO DA URL ({url_fonte}) ---\n"
            "Nenhum conteúdo relevante encontrado nesta URL para a consulta.\n"
            f"--- FIM DO CONTEXTO DA URL ({url_fonte}) ---\n"
        )

    contexto_formatado = f"\n\n--- INÍCIO DO CONTEXTO DA URL ({url_fonte}) ---\n"
    contexto_formatado += "Conteúdo extraído da URL para consulta:\n"
    for i, doc in enumerate(documentos_chroma):
        conteudo = getattr(doc, "page_content", "") or ""
        metadata_source = getattr(doc, "metadata", {}).get("source", url_fonte)
        contexto_formatado += f"\n[TRECHO {i+1} DA URL: {metadata_source}]\n"
        contexto_formatado += f"Conteúdo do Trecho: {conteudo}\n"
    contexto_formatado += f"--- FIM DO CONTEXTO DA URL ({url_fonte}) ---\n"
    return contexto_formatado


def obter_contexto_relevante_de_url(url_referencia: str, pergunta_usuario: str, top_k_chunks: int = 3) -> str:
    """Retorna contexto formatado (string) com top_k trechos relevantes da URL."""
    if not url_referencia:
        return ""

    retriever = _criar_retriever_chroma_de_url(url_referencia, top_k_retriever=top_k_chunks)
    if not retriever:
        return (
            f"\n\n--- CONTEXTO DA URL ({url_referencia}) ---\n"
            "Falha ao carregar ou processar o conteúdo da URL.\n"
            f"--- FIM DO CONTEXTO DA URL ({url_referencia}) ---\n"
        )

    try:
        documentos_relevantes = retriever.invoke(pergunta_usuario)
        return formatar_contexto_chroma_para_llm(documentos_relevantes, url_referencia)
    except Exception as e:
        print(f"ERRO CHROMA_UTILS: Falha ao obter contexto da URL {url_referencia}: {e}", flush=True)
        traceback.print_exc()
        return (
            f"\n\n--- CONTEXTO DA URL ({url_referencia}) ---\n"
            f"Erro ao buscar informações na URL: {str(e)}\n"
            f"--- FIM DO CONTEXTO DA URL ({url_referencia}) ---\n"
        )
