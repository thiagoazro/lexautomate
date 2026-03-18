"""
api.py
FastAPI — ponto de entrada principal do LexAutomate.

Endpoints:
  GET  /health                 → status dos serviços
  POST /api/search             → busca híbrida (BM25 + kNN + RRF + reranking)
  POST /api/generate           → geração de resposta com RAG completo
  POST /api/index              → dispara indexação dos documentos_juridicos/
  GET  /api/graph/{filename}   → serve HTML do grafo GraphRAG

Iniciar:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

GRAPH_VIZ_DIR = os.getenv("GRAPH_VIZ_DIR", "graph_visualizations")
DEFAULT_DOCS_FOLDER = "documentos_juridicos"

app = FastAPI(
    title="LexAutomate API",
    description="RAG jurídico com busca híbrida, reranking e GraphRAG.",
    version="2.0.0",
)


# ─── Schemas ─────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., description="Consulta de busca em linguagem natural")
    top_k: int = Field(10, ge=1, le=50, description="Número de resultados")
    bm25_candidates: int = Field(30, ge=5, le=100)
    dense_candidates: int = Field(30, ge=5, le=100)
    use_rerank: bool = Field(True, description="Aplicar reranking nos resultados")
    use_cross_encoder: bool = Field(True, description="Usar cross-encoder (se disponível)")
    top_k_rerank: int = Field(7, ge=1, le=20)


class SearchResult(BaseModel):
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    arquivo_origem: Optional[str] = None
    tipo_documento: Optional[str] = None
    area_direito: Optional[str] = None
    content: str
    rrf_score: Optional[float] = None
    bm25_score: Optional[float] = None
    dense_score: Optional[float] = None
    rerank_score: Optional[float] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[SearchResult]


class GenerateRequest(BaseModel):
    query: str = Field(..., description="Pergunta ou instrução jurídica")
    system_prompt: str = Field("", description="Prompt de sistema (instruções ao LLM)")
    chat_history: List[Dict[str, str]] = Field(
        [], description="Histórico de conversa [{'role': 'user'|'assistant', 'content': '...'}]"
    )
    top_k: int = Field(10, ge=1, le=30)
    use_rerank: bool = Field(True)
    use_cross_encoder: bool = Field(True)
    use_graph_rag: str = Field(
        "auto",
        description="Modo GraphRAG: 'auto' | 'on' | 'off'",
    )
    use_web_fallback: bool = Field(True)
    temperature: float = Field(0.2, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=100, le=16000)
    save_graph_html: bool = Field(True)


class GenerateResponse(BaseModel):
    answer: str
    contexts_count: int
    graph_summary: str
    graph_html_path: str
    web_results_count: int


class IndexRequest(BaseModel):
    folder: str = Field(DEFAULT_DOCS_FOLDER, description="Pasta com os documentos")
    recreate: bool = Field(False, description="Recriar índice do zero")
    skip_existing: bool = Field(True, description="Pular documentos já indexados")
    chunk_size: int = Field(800, ge=200, le=4000)
    chunk_overlap: int = Field(120, ge=0, le=500)


class IndexResponse(BaseModel):
    status: str
    message: str
    stats: Optional[Dict[str, int]] = None


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check() -> Dict[str, Any]:
    """Verifica disponibilidade dos serviços (OpenSearch, OpenAI)."""
    from rag_utils import get_opensearch_client, get_openai_client, get_anthropic_client

    os_ok = False
    try:
        client = get_opensearch_client()
        os_ok = client is not None and client.ping()
    except Exception:
        pass

    anthropic_ok = False
    try:
        ac = get_anthropic_client()
        anthropic_ok = ac is not None
    except Exception:
        pass

    openai_ok = False
    try:
        client_oai = get_openai_client()
        openai_ok = client_oai is not None
    except Exception:
        pass

    status = "ok" if (os_ok and anthropic_ok and openai_ok) else "degraded"
    return {
        "status": status,
        "services": {
            "opensearch": "ok" if os_ok else "unavailable",
            "anthropic_llm": "ok" if anthropic_ok else "unavailable",
            "openai_embeddings": "ok" if openai_ok else "unavailable",
        },
    }


# ─── Busca híbrida ────────────────────────────────────────────────────────────

@app.post("/api/search", response_model=SearchResponse, tags=["RAG"])
def search(req: SearchRequest) -> SearchResponse:
    """
    Busca híbrida: BM25 + kNN + RRF + reranking opcional.

    Retorna os chunks mais relevantes para a consulta.
    """
    from rag_utils import (
        get_openai_client, get_opensearch_client, get_anthropic_client,
        get_embedding, OPENSEARCH_INDEX,
        OPENSEARCH_TEXT_FIELD, OPENSEARCH_VECTOR_FIELD,
    )
    from hybrid_search import hybrid_search
    from reranker import rerank

    os_client = get_opensearch_client()
    oai_client = get_openai_client()       # para embeddings
    anth_client = get_anthropic_client()   # para reranking LLM fallback

    if not os_client or not oai_client:
        raise HTTPException(status_code=503, detail="Serviços não disponíveis")

    # Gerar embedding da query (OpenAI)
    vec = get_embedding(req.query, oai_client)
    if vec is None:
        raise HTTPException(status_code=500, detail="Falha ao gerar embedding da query")

    # Busca híbrida
    hits = hybrid_search(
        os_client,
        OPENSEARCH_INDEX,
        req.query,
        vec,
        top_k=req.top_k,
        text_field=OPENSEARCH_TEXT_FIELD,
        vector_field=OPENSEARCH_VECTOR_FIELD,
        bm25_candidates=req.bm25_candidates,
        dense_candidates=req.dense_candidates,
    )

    # Reranking (cross-encoder local ou Claude como fallback)
    if req.use_rerank and hits:
        hits = rerank(
            req.query,
            hits,
            top_k=req.top_k_rerank,
            anthropic_client=anth_client,
            use_cross_encoder=req.use_cross_encoder,
            content_field=OPENSEARCH_TEXT_FIELD,
        )

    # Montar resposta
    results = []
    for h in hits:
        content = (h.get(OPENSEARCH_TEXT_FIELD) or "").strip()
        if not content:
            continue
        results.append(
            SearchResult(
                chunk_id=h.get("chunk_id"),
                document_id=h.get("document_id"),
                arquivo_origem=h.get("arquivo_origem"),
                tipo_documento=h.get("tipo_documento"),
                area_direito=h.get("area_direito"),
                content=content,
                rrf_score=h.get("_rrf_score"),
                bm25_score=h.get("_bm25_score"),
                dense_score=h.get("_dense_score"),
                rerank_score=h.get("_rerank_score"),
            )
        )

    return SearchResponse(query=req.query, total=len(results), results=results)


# ─── Geração com RAG ──────────────────────────────────────────────────────────

@app.post("/api/generate", response_model=GenerateResponse, tags=["RAG"])
def generate(req: GenerateRequest) -> GenerateResponse:
    """
    Pipeline RAG completo:
      1. Busca híbrida (BM25 + kNN + RRF)
      2. Reranking (cross-encoder ou LLM)
      3. GraphRAG (PageRank + betweenness + comunidades)
      4. Web fallback via Serper (se necessário)
      5. Geração de resposta com LLM (OpenAI)
    """
    from rag_utils import generate_response_with_rag_and_web_fallback

    try:
        answer, contexts, details, web_results, graph_summary, graph_html_path = (
            generate_response_with_rag_and_web_fallback(
                user_query=req.query,
                system_message_base=req.system_prompt,
                chat_history=req.chat_history,
                top_k=req.top_k,
                use_rerank=req.use_rerank,
                use_cross_encoder=req.use_cross_encoder,
                use_graph_rag=req.use_graph_rag,
                use_web_fallback=req.use_web_fallback,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                save_graph_html=req.save_graph_html,
            )
        )
    except Exception as exc:
        logger.error(f"Erro na geração RAG: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro na geração: {exc}")

    return GenerateResponse(
        answer=answer,
        contexts_count=len(contexts),
        graph_summary=graph_summary or "",
        graph_html_path=graph_html_path or "",
        web_results_count=len(web_results),
    )


# ─── Indexação ────────────────────────────────────────────────────────────────

_indexing_status: Dict[str, Any] = {"running": False, "last_stats": None}


def _run_indexing(req: IndexRequest) -> None:
    """Executa indexação em background."""
    global _indexing_status
    _indexing_status["running"] = True
    try:
        from indexer import index_folder
        stats = index_folder(
            folder=req.folder,
            recreate=req.recreate,
            skip_existing=req.skip_existing,
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
        )
        _indexing_status["last_stats"] = stats
        logger.info(f"Indexação concluída: {stats}")
    except Exception as exc:
        logger.error(f"Erro na indexação: {exc}", exc_info=True)
        _indexing_status["last_stats"] = {"error": str(exc)}
    finally:
        _indexing_status["running"] = False


@app.post("/api/index", response_model=IndexResponse, tags=["Admin"])
def trigger_indexing(
    req: IndexRequest,
    background_tasks: BackgroundTasks,
) -> IndexResponse:
    """
    Dispara indexação dos documentos em background.
    O processo roda assincronamente — consulte /api/index/status para acompanhar.
    """
    if _indexing_status["running"]:
        return IndexResponse(
            status="running",
            message="Indexação já em andamento. Aguarde a conclusão.",
        )

    folder_path = Path(req.folder)
    if not folder_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Pasta não encontrada: {req.folder}",
        )

    background_tasks.add_task(_run_indexing, req)

    return IndexResponse(
        status="started",
        message=f"Indexação iniciada para '{req.folder}'. Use GET /api/index/status para acompanhar.",
    )


@app.get("/api/index/status", tags=["Admin"])
def indexing_status() -> Dict[str, Any]:
    """Retorna o status atual da indexação."""
    return {
        "running": _indexing_status["running"],
        "last_stats": _indexing_status["last_stats"],
    }


# ─── Visualização de grafo ────────────────────────────────────────────────────

@app.get("/api/graph/{filename}", tags=["GraphRAG"])
def serve_graph(filename: str) -> FileResponse:
    """Serve o HTML de visualização do grafo GraphRAG."""
    # Sanitizar nome do arquivo
    safe_name = Path(filename).name
    if not safe_name.endswith(".html"):
        raise HTTPException(status_code=400, detail="Apenas arquivos .html são servidos")

    file_path = Path(GRAPH_VIZ_DIR) / safe_name
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Grafo não encontrado: {safe_name}")

    return FileResponse(path=str(file_path), media_type="text/html")


@app.get("/api/graph", tags=["GraphRAG"])
def list_graphs() -> Dict[str, Any]:
    """Lista os grafos GraphRAG disponíveis."""
    graph_dir = Path(GRAPH_VIZ_DIR)
    if not graph_dir.is_dir():
        return {"graphs": []}

    graphs = sorted(
        [f.name for f in graph_dir.glob("*.html")],
        reverse=True,
    )
    return {"graphs": graphs, "total": len(graphs)}
