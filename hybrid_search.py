"""
hybrid_search.py
Busca híbrida via Qdrant: Dense (OpenAI) + Sparse BM25 (fastembed) + RRF nativo.

O Qdrant executa o RRF internamente com a API de Prefetch + FusionQuery,
sem precisar de implementação manual.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import FusionQuery, Fusion, Prefetch

logger = logging.getLogger(__name__)


def hybrid_search(
    client: QdrantClient,
    collection_name: str,
    query_text: str,
    query_vector: List[float],
    top_k: int = 10,
    bm25_candidates: int = 30,
    dense_candidates: int = 30,
    content_field: str = "content",   # mantido por compatibilidade
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Busca híbrida Qdrant: dense + sparse BM25 → RRF nativo.

    Fluxo:
      1. Prefetch dense   → top dense_candidates por similaridade semântica
      2. Prefetch sparse  → top bm25_candidates por BM25 keyword match
      3. FusionQuery RRF  → funde os dois rankings em top_k resultados

    Se o modelo BM25 não estiver disponível, cai para busca apenas semântica.

    Returns:
        Lista de dicts com payload + _rrf_score + _qdrant_id
    """
    from qdrant_utils import embed_sparse

    sparse_vec = embed_sparse(query_text)

    prefetches = [
        Prefetch(
            query=query_vector,
            using="dense",
            limit=dense_candidates,
        )
    ]

    if sparse_vec is not None:
        prefetches.append(
            Prefetch(
                query=sparse_vec,
                using="sparse",
                limit=bm25_candidates,
            )
        )
    else:
        logger.warning("BM25 indisponível — buscando apenas com vetor semântico.")

    try:
        results = client.query_points(
            collection_name=collection_name,
            prefetch=prefetches,
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )

        docs = []
        for point in results.points:
            doc = dict(point.payload or {})
            doc["_rrf_score"] = round(point.score, 6)
            doc["_qdrant_id"] = str(point.id)
            docs.append(doc)

        logger.info(f"Hybrid search → {len(docs)} resultados (prefetches={len(prefetches)})")
        return docs

    except Exception as exc:
        logger.error(f"Hybrid search falhou: {exc}. Tentando fallback denso...")

        # Fallback: só dense
        try:
            results = client.search(
                collection_name=collection_name,
                query_vector=("dense", query_vector),
                limit=top_k,
                with_payload=True,
            )
            docs = []
            for point in results:
                doc = dict(point.payload or {})
                doc["_rrf_score"] = round(point.score, 6)
                doc["_qdrant_id"] = str(point.id)
                docs.append(doc)
            logger.info(f"Fallback denso → {len(docs)} resultados")
            return docs

        except Exception as exc2:
            logger.error(f"Fallback denso também falhou: {exc2}")
            return []
