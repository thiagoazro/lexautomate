"""
hybrid_search.py
Busca híbrida: BM25 (OpenSearch) + Dense Retrieval (kNN) + Reciprocal Rank Fusion (RRF).

Etapas:
  1. BM25 keyword search via OpenSearch (analyzer português com stemmer)
  2. Dense kNN vector search via OpenSearch (embeddings OpenAI)
  3. Reciprocal Rank Fusion (Cormack et al., 2009) para fundir os rankings
  4. Retorna top_k resultados fundidos com scores de transparência
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Constante RRF — Cormack et al. 2009. Valor 60 é padrão bem estabelecido.
RRF_K: int = 60


# ─── BM25 ────────────────────────────────────────────────────────────────────

def bm25_search(
    client,
    index: str,
    query_text: str,
    top_k: int = 30,
    text_field: str = "content",
) -> List[Tuple[Dict[str, Any], float]]:
    """
    Busca BM25 pura via OpenSearch.
    Usa match phrase boost para termos exatos terem prioridade.
    Retorna [(doc_source, score)] ordenado por score decrescente.
    """
    body = {
        "size": top_k,
        "query": {
            "bool": {
                "should": [
                    {
                        "match": {
                            text_field: {
                                "query": query_text,
                                "operator": "or",
                                "boost": 1.0,
                                "fuzziness": "AUTO",
                            }
                        }
                    },
                    {
                        "match_phrase": {
                            text_field: {
                                "query": query_text,
                                "slop": 2,
                                "boost": 2.5,
                            }
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        },
    }

    try:
        res = client.search(index=index, body=body)
        hits = res.get("hits", {}).get("hits", []) or []
        results = []
        for h in hits:
            src = dict(h.get("_source", {}) or {})
            src["_os_id"] = h.get("_id", "")
            results.append((src, float(h.get("_score", 0.0))))
        return results
    except Exception as exc:
        logger.error(f"BM25 search failed: {exc}")
        return []


# ─── Dense retrieval ─────────────────────────────────────────────────────────

def dense_search(
    client,
    index: str,
    query_vector: List[float],
    top_k: int = 30,
    vector_field: str = "content_vector",
) -> List[Tuple[Dict[str, Any], float]]:
    """
    Busca semântica kNN via OpenSearch.
    Retorna [(doc_source, score)] ordenado por score decrescente.
    """
    body = {
        "size": top_k,
        "query": {
            "knn": {
                vector_field: {
                    "vector": query_vector,
                    "k": top_k,
                }
            }
        },
    }

    try:
        res = client.search(index=index, body=body)
        hits = res.get("hits", {}).get("hits", []) or []
        results = []
        for h in hits:
            src = dict(h.get("_source", {}) or {})
            src["_os_id"] = h.get("_id", "")
            results.append((src, float(h.get("_score", 0.0))))
        return results
    except Exception as exc:
        logger.error(f"Dense search failed: {exc}")
        return []


# ─── RRF ─────────────────────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    *result_lists: List[Tuple[Dict[str, Any], float]],
    k: int = RRF_K,
    id_field: str = "chunk_id",
) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion (Cormack et al., 2009).

    Para cada documento em cada lista ranqueada:
        RRF(d) = Σ_i  1 / (k + rank_i(d))

    Listas com o mesmo documento (por chunk_id) acumulam score.
    Maior RRF score → mais relevante.

    Mantém scores individuais (bm25, dense) para transparência.
    """
    rrf_scores: Dict[str, float] = {}
    id_to_doc: Dict[str, Dict[str, Any]] = {}
    per_list_scores: Dict[str, Dict[int, float]] = {}  # doc_id → {list_idx: raw_score}

    for list_idx, result_list in enumerate(result_lists):
        for rank, (doc, raw_score) in enumerate(result_list, start=1):
            doc_id = str(
                doc.get(id_field)
                or doc.get("_os_id")
                or doc.get("document_id")
                or hash(frozenset(doc.get("content", "")[:64]))
            )
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)

            if doc_id not in id_to_doc:
                id_to_doc[doc_id] = doc

            per_list_scores.setdefault(doc_id, {})[list_idx] = raw_score

    merged: List[Dict[str, Any]] = []
    for doc_id in sorted(rrf_scores, key=lambda d: rrf_scores[d], reverse=True):
        doc = dict(id_to_doc[doc_id])
        doc["_rrf_score"] = round(rrf_scores[doc_id], 6)
        doc["_bm25_score"] = per_list_scores.get(doc_id, {}).get(0)
        doc["_dense_score"] = per_list_scores.get(doc_id, {}).get(1)
        merged.append(doc)

    return merged


# ─── Hybrid (BM25 + Dense + RRF) ─────────────────────────────────────────────

def hybrid_search(
    client,
    index: str,
    query_text: str,
    query_vector: List[float],
    top_k: int = 10,
    text_field: str = "content",
    vector_field: str = "content_vector",
    bm25_candidates: int = 30,
    dense_candidates: int = 30,
) -> List[Dict[str, Any]]:
    """
    Busca híbrida completa: BM25 + kNN → RRF → top_k.

    Parâmetros:
        bm25_candidates: quantos candidatos BM25 puxar antes de fundir
        dense_candidates: quantos candidatos kNN puxar antes de fundir
        top_k: número de resultados finais após fusão

    Retorna lista de dicts com campos:
        _rrf_score, _bm25_score, _dense_score, content, chunk_id, ...
    """
    bm25_results = bm25_search(
        client, index, query_text,
        top_k=bm25_candidates, text_field=text_field,
    )
    dense_results = dense_search(
        client, index, query_vector,
        top_k=dense_candidates, vector_field=vector_field,
    )

    logger.info(
        f"Hybrid search candidates — BM25: {len(bm25_results)}, Dense: {len(dense_results)}"
    )

    merged = reciprocal_rank_fusion(bm25_results, dense_results)
    return merged[:top_k]
