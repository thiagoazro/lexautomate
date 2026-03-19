"""
api.py
FastAPI — LexAutomate Backend

Endpoints:
  GET  /health                → status dos serviços
  POST /api/search            → busca híbrida (dense + BM25 + RRF + reranking)
  POST /api/generate          → geração RAG completa (Claude)
  POST /api/index             → indexa documentos_juridicos/ no Qdrant
  GET  /api/index/status      → status da indexação
  GET  /api/graph/{filename}  → HTML de visualização do grafo

Deploy:
    uvicorn api:app --host 0.0.0.0 --port 8000

Render:
    Veja render.yaml / Dockerfile na raiz do projeto.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

GRAPH_VIZ_DIR = os.getenv("GRAPH_VIZ_DIR", "/tmp/graph_visualizations")
DEFAULT_DOCS_FOLDER = "documentos_juridicos"
os.makedirs(GRAPH_VIZ_DIR, exist_ok=True)

app = FastAPI(
    title="LexAutomate API",
    description=(
        "RAG jurídico com busca híbrida (BM25 + semântica + RRF), "
        "reranking cross-encoder, GraphRAG e Claude (Anthropic)."
    ),
    version="3.0.0",
)

# ─── CORS — permite que o Lovable (ou qualquer frontend) chame a API ──────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Em produção, troque por ["https://seu-app.lovable.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Startup: valida conexões ─────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info("LexAutomate API iniciando...")
    try:
        from rag_utils import get_qdrant_client, get_openai_client, get_anthropic_client
        from qdrant_utils import ensure_collection, QDRANT_COLLECTION, EMBEDDING_DIM

        qdrant = get_qdrant_client()
        if qdrant:
            ensure_collection(qdrant, QDRANT_COLLECTION, EMBEDDING_DIM, recreate=False)
            logger.info("Qdrant: OK")
        else:
            logger.warning("Qdrant: INDISPONÍVEL")

        oai = get_openai_client()
        logger.info(f"OpenAI (embeddings): {'OK' if oai else 'INDISPONÍVEL'}")

        anth = get_anthropic_client()
        logger.info(f"Anthropic (Claude): {'OK' if anth else 'INDISPONÍVEL'}")

    except Exception as exc:
        logger.error(f"Erro no startup: {exc}")


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., description="Consulta em linguagem natural")
    top_k: int = Field(10, ge=1, le=50)
    bm25_candidates: int = Field(30, ge=5, le=100)
    dense_candidates: int = Field(30, ge=5, le=100)
    use_rerank: bool = Field(True)
    use_cross_encoder: bool = Field(True)
    top_k_rerank: int = Field(7, ge=1, le=20)


class SearchResult(BaseModel):
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    arquivo_origem: Optional[str] = None
    tipo_documento: Optional[str] = None
    area_direito: Optional[str] = None
    content: str
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[SearchResult]


class GenerateRequest(BaseModel):
    query: str
    system_prompt: str = Field("", description="Instrução de sistema para o Claude")
    chat_history: List[Dict[str, str]] = Field(
        [], description="[{'role':'user','content':'...'}, {'role':'assistant','content':'...'}]"
    )
    top_k: int = Field(10, ge=1, le=30)
    use_rerank: bool = Field(True)
    use_cross_encoder: bool = Field(True)
    use_graph_rag: str = Field("auto", description="'auto' | 'on' | 'off'")
    use_web_fallback: bool = Field(True)
    temperature: float = Field(0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(4096, ge=100, le=16000)
    save_graph_html: bool = Field(True)


class GenerateResponse(BaseModel):
    answer: str
    contexts_count: int
    graph_summary: str
    graph_html_path: str
    web_results_count: int


class IndexRequest(BaseModel):
    folder: str = Field(DEFAULT_DOCS_FOLDER)
    recreate: bool = Field(False)
    skip_existing: bool = Field(True)
    chunk_size: int = Field(800, ge=200, le=4000)
    chunk_overlap: int = Field(120, ge=0, le=500)


class IndexResponse(BaseModel):
    status: str
    message: str
    stats: Optional[Dict[str, int]] = None


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check() -> Dict[str, Any]:
    """Verifica status de todos os serviços."""
    from rag_utils import get_qdrant_client, get_openai_client, get_anthropic_client
    from qdrant_utils import ping, count_points, QDRANT_COLLECTION

    qdrant_ok = False
    points_count = 0
    try:
        qc = get_qdrant_client()
        if qc:
            qdrant_ok = ping(qc)
            points_count = count_points(qc, QDRANT_COLLECTION)
    except Exception:
        pass

    anthropic_ok = get_anthropic_client() is not None
    openai_ok = get_openai_client() is not None

    status = "ok" if (qdrant_ok and anthropic_ok and openai_ok) else "degraded"
    return {
        "status": status,
        "services": {
            "qdrant": "ok" if qdrant_ok else "unavailable",
            "anthropic_llm": "ok" if anthropic_ok else "unavailable",
            "openai_embeddings": "ok" if openai_ok else "unavailable",
        },
        "collection": {
            "name": QDRANT_COLLECTION,
            "points": points_count,
        },
    }


# ─── Busca ────────────────────────────────────────────────────────────────────

@app.post("/api/search", response_model=SearchResponse, tags=["RAG"])
def search(req: SearchRequest) -> SearchResponse:
    """Busca híbrida: dense (OpenAI) + sparse BM25 + RRF nativo Qdrant + reranking.

    Pesquisa pura — retorna trechos de documentos sem chamar LLM.
    Usa query expansion e deduplicação para melhorar resultados.
    No futuro pode ser substituído/complementado pela API JurisRimor.
    """
    from rag_utils import (
        get_qdrant_client, get_openai_client, get_anthropic_client,
        get_embedding, expand_query, deduplicate_contexts,
    )
    from qdrant_utils import QDRANT_COLLECTION
    from hybrid_search import hybrid_search
    from reranker import rerank

    qdrant = get_qdrant_client()
    oai = get_openai_client()
    anth = get_anthropic_client()

    if not qdrant or not oai:
        raise HTTPException(status_code=503, detail="Serviços não disponíveis")

    # Query expansion: adiciona termos jurídicos equivalentes
    expanded = expand_query(req.query)

    vec = get_embedding(expanded, oai)
    if vec is None:
        raise HTTPException(status_code=500, detail="Falha ao gerar embedding")

    hits = hybrid_search(
        qdrant, QDRANT_COLLECTION, expanded, vec,
        top_k=req.top_k,
        bm25_candidates=req.bm25_candidates,
        dense_candidates=req.dense_candidates,
    )

    if req.use_rerank and hits:
        hits = rerank(
            req.query, hits,
            top_k=req.top_k_rerank,
            anthropic_client=anth,
            use_cross_encoder=req.use_cross_encoder,
            content_field="content",
        )

    # JuIT Rimor — jurisprudência pública (ativado se JUIT_API_KEY definida)
    try:
        from juit_rimor import is_available as juit_available, buscar_jurisprudencias
        if juit_available():
            juit_results = buscar_jurisprudencias(req.query, top_k=5)
            if juit_results:
                hits.extend(juit_results)
                logger.info(f"JuIT Rimor: +{len(juit_results)} resultados adicionados")
    except Exception as exc:
        logger.warning(f"JuIT Rimor indisponível: {exc}")

    # Deduplicação
    hits = deduplicate_contexts(hits, similarity_threshold=0.85)

    results = [
        SearchResult(
            chunk_id=h.get("chunk_id"),
            document_id=h.get("document_id"),
            arquivo_origem=h.get("arquivo_origem"),
            tipo_documento=h.get("tipo_documento"),
            area_direito=h.get("area_direito"),
            content=(h.get("content") or "").strip(),
            rrf_score=h.get("_rrf_score"),
            rerank_score=h.get("_rerank_score"),
        )
        for h in hits if (h.get("content") or "").strip()
    ]

    return SearchResponse(query=req.query, total=len(results), results=results)


# ─── Geração RAG ──────────────────────────────────────────────────────────────

@app.post("/api/generate", response_model=GenerateResponse, tags=["RAG"])
def generate(req: GenerateRequest) -> GenerateResponse:
    """Pipeline RAG completo: busca híbrida → reranking → GraphRAG → Claude."""
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
        raise HTTPException(status_code=500, detail=str(exc))

    return GenerateResponse(
        answer=answer,
        contexts_count=len(contexts),
        graph_summary=graph_summary or "",
        graph_html_path=graph_html_path or "",
        web_results_count=len(web_results),
    )


# ─── Indexação ────────────────────────────────────────────────────────────────

_indexing: Dict[str, Any] = {"running": False, "last_stats": None}


def _run_indexing(req: IndexRequest) -> None:
    global _indexing
    _indexing["running"] = True
    try:
        from indexer import index_folder
        stats = index_folder(
            folder=req.folder,
            recreate=req.recreate,
            skip_existing=req.skip_existing,
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
        )
        _indexing["last_stats"] = stats
    except Exception as exc:
        logger.error(f"Erro na indexação: {exc}", exc_info=True)
        _indexing["last_stats"] = {"error": str(exc)}
    finally:
        _indexing["running"] = False


@app.post("/api/index", response_model=IndexResponse, tags=["Admin"])
def trigger_indexing(req: IndexRequest, background_tasks: BackgroundTasks) -> IndexResponse:
    """Dispara indexação dos documentos em background."""
    if _indexing["running"]:
        return IndexResponse(status="running", message="Indexação já em andamento.")

    if not Path(req.folder).is_dir():
        raise HTTPException(status_code=400, detail=f"Pasta não encontrada: {req.folder}")

    background_tasks.add_task(_run_indexing, req)
    return IndexResponse(
        status="started",
        message=f"Indexação iniciada para '{req.folder}'. Acompanhe em GET /api/index/status",
    )


@app.get("/api/index/status", tags=["Admin"])
def indexing_status() -> Dict[str, Any]:
    return {"running": _indexing["running"], "last_stats": _indexing["last_stats"]}


# ─── Grafos GraphRAG ──────────────────────────────────────────────────────────

@app.get("/api/graph/{filename}", tags=["GraphRAG"])
def serve_graph(filename: str) -> FileResponse:
    safe = Path(filename).name
    if not safe.endswith(".html"):
        raise HTTPException(status_code=400, detail="Apenas .html")
    path = Path(GRAPH_VIZ_DIR) / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Grafo não encontrado")
    return FileResponse(str(path), media_type="text/html")


@app.get("/api/graph", tags=["GraphRAG"])
def list_graphs() -> Dict[str, Any]:
    graph_dir = Path(GRAPH_VIZ_DIR)
    if not graph_dir.is_dir():
        return {"graphs": [], "total": 0}
    graphs = sorted([f.name for f in graph_dir.glob("*.html")], reverse=True)
    return {"graphs": graphs, "total": len(graphs)}
