"""
qdrant_utils.py
Cliente Qdrant Cloud: coleção híbrida (dense OpenAI + sparse BM25 fastembed) + upsert em lote.

Variáveis de ambiente:
  QDRANT_URL         → URL do cluster Qdrant (ex: https://xxx.qdrant.io)
  QDRANT_API_KEY     → API key do Qdrant Cloud
  QDRANT_COLLECTION  → nome da coleção (padrão: docs-index)
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FusionQuery,
    Fusion,
    Prefetch,
    PointStruct,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

logger = logging.getLogger(__name__)

QDRANT_URL = (os.getenv("QDRANT_URL") or "http://localhost:6333").strip()
QDRANT_API_KEY = (os.getenv("QDRANT_API_KEY") or "").strip()
QDRANT_COLLECTION = (os.getenv("QDRANT_COLLECTION") or "docs-index").strip()
# text-embedding-3-small = 1536d, text-embedding-3-large = 3072d
_emb_model = (os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small").strip()
EMBEDDING_DIM = 1536 if "small" in _emb_model else 3072

# ─── Singletons ───────────────────────────────────────────────────────────────
_qdrant_client: Optional[QdrantClient] = None
_bm25_model = None


def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client

    kwargs: Dict[str, Any] = {"url": QDRANT_URL}
    if QDRANT_API_KEY:
        kwargs["api_key"] = QDRANT_API_KEY
    kwargs["timeout"] = 60

    _qdrant_client = QdrantClient(**kwargs)
    return _qdrant_client


def get_bm25_model():
    """Carrega o modelo BM25 via fastembed (lazy, singleton)."""
    global _bm25_model
    if _bm25_model is not None:
        return _bm25_model

    try:
        from fastembed import SparseTextEmbedding
        _bm25_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        logger.info("BM25 model carregado: Qdrant/bm25")
    except Exception as exc:
        logger.warning(f"BM25 model indisponível: {exc}. Buscas serão apenas semânticas.")
        _bm25_model = None

    return _bm25_model


def embed_sparse(text: str) -> Optional[SparseVector]:
    """Gera vetor esparso BM25 para um texto."""
    model = get_bm25_model()
    if model is None:
        return None
    try:
        emb = list(model.embed([text]))[0]
        return SparseVector(
            indices=emb.indices.tolist(),
            values=emb.values.tolist(),
        )
    except Exception as exc:
        logger.error(f"Sparse embedding falhou: {exc}")
        return None


def chunk_id_to_uuid(chunk_id: str) -> str:
    """Converte chunk_id string em UUID determinístico para o Qdrant."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


# ─── Coleção ──────────────────────────────────────────────────────────────────

def ensure_collection(
    client: QdrantClient,
    collection_name: str = QDRANT_COLLECTION,
    embedding_dim: int = EMBEDDING_DIM,
    recreate: bool = False,
) -> None:
    """
    Garante que a coleção existe com vetores dense + sparse.

    Schema:
      dense  → OpenAI text-embedding-3-large (3072 dims, cosine)
      sparse → BM25 fastembed (Qdrant/bm25, dimensão variável)
    """
    exists = client.collection_exists(collection_name)

    if exists and recreate:
        client.delete_collection(collection_name)
        logger.info(f"Coleção '{collection_name}' deletada para recriação.")
        exists = False

    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": VectorParams(size=embedding_dim, distance=Distance.COSINE)
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(
                    index=SparseIndexParams(on_disk=False)
                )
            },
        )
        logger.info(f"Coleção '{collection_name}' criada (dense={embedding_dim}d + sparse BM25).")


# ─── Indexação em lote ────────────────────────────────────────────────────────

def upsert_points(
    client: QdrantClient,
    points: List[Dict[str, Any]],
    collection_name: str = QDRANT_COLLECTION,
    batch_size: int = 100,
) -> Tuple[int, int]:
    """
    Insere/atualiza pontos na coleção Qdrant.

    Cada dict deve ter:
      - chunk_id (str)         → ID único do chunk
      - content_vector (list)  → embedding denso OpenAI
      - sparse_vector          → SparseVector BM25 (opcional)
      - content (str)          → texto do chunk
      - + demais campos de metadados como payload

    Retorna (success_count, error_count).
    """
    success = 0
    errors = 0

    for start in range(0, len(points), batch_size):
        batch = points[start: start + batch_size]
        qdrant_points: List[PointStruct] = []

        for p in batch:
            chunk_id = str(p.get("chunk_id") or uuid.uuid4())
            dense_vector = p.get("content_vector") or p.get("dense_vector")
            sparse_vector = p.get("sparse_vector")

            if not dense_vector:
                errors += 1
                continue

            vector: Dict[str, Any] = {"dense": dense_vector}
            if isinstance(sparse_vector, SparseVector):
                vector["sparse"] = sparse_vector

            # Payload = tudo exceto os vetores
            payload = {
                k: v for k, v in p.items()
                if k not in ("content_vector", "dense_vector", "sparse_vector")
            }

            qdrant_points.append(
                PointStruct(
                    id=chunk_id_to_uuid(chunk_id),
                    vector=vector,
                    payload=payload,
                )
            )

        if not qdrant_points:
            continue

        try:
            client.upsert(
                collection_name=collection_name,
                points=qdrant_points,
                wait=True,
            )
            success += len(qdrant_points)
            logger.debug(f"Upsert: {len(qdrant_points)} pontos OK")
        except Exception as exc:
            logger.error(f"Upsert batch falhou: {exc}")
            errors += len(qdrant_points)

    return success, errors


# ─── Utilitários ─────────────────────────────────────────────────────────────

def ping(client: QdrantClient) -> bool:
    try:
        client.get_collections()
        return True
    except Exception:
        return False


def count_points(
    client: QdrantClient,
    collection_name: str = QDRANT_COLLECTION,
) -> int:
    """Retorna o número de pontos na coleção."""
    try:
        info = client.get_collection(collection_name)
        return info.points_count or 0
    except Exception:
        return 0
