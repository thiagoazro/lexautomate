"""
reranker.py
Reranking de chunks recuperados para RAG jurídico.

Estratégia primária:  Cross-encoder multilingual (sentence-transformers — local, sem API)
Fallback:             LLM reranking via Anthropic Claude

O cross-encoder avalia cada par (query, trecho) em conjunto,
capturando interações semânticas que o bi-encoder não captura.
Modelo: cross-encoder/ms-marco-multilingual-MiniLM-L12-en
  – Treinado em dados multilíngues do MS MARCO
  – Funciona bem para português jurídico
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Dict, List, Optional

import anthropic

logger = logging.getLogger(__name__)

_CROSS_ENCODER_NAME = "cross-encoder/ms-marco-multilingual-MiniLM-L12-en"
_cross_encoder_model = None  # lazy-loaded singleton


# ─── Cross-encoder ────────────────────────────────────────────────────────────

def _load_cross_encoder():
    """Carrega o cross-encoder. Falha silenciosamente; retorna None se indisponível."""
    global _cross_encoder_model
    if _cross_encoder_model is not None:
        return _cross_encoder_model

    try:
        from sentence_transformers import CrossEncoder
        _cross_encoder_model = CrossEncoder(_CROSS_ENCODER_NAME, max_length=512)
        logger.info(f"Cross-encoder carregado: {_CROSS_ENCODER_NAME}")
    except Exception as exc:
        logger.warning(
            f"Não foi possível carregar cross-encoder ({exc}). "
            "Usando LLM reranking como fallback."
        )
        _cross_encoder_model = None

    return _cross_encoder_model


def cross_encoder_rerank(
    query: str,
    chunks: List[Dict[str, Any]],
    top_k: int = 7,
    content_field: str = "content",
) -> List[Dict[str, Any]]:
    """
    Reranka chunks com cross-encoder.

    Avalia cada par (query, chunk) e ordena por relevância.
    Adiciona campo `_rerank_score` em cada chunk retornado.

    Retorna: top_k chunks ordenados do mais para o menos relevante.
    """
    if not chunks:
        return chunks

    model = _load_cross_encoder()
    if model is None:
        logger.warning("Cross-encoder indisponível, retornando ordem original.")
        return chunks[:top_k]

    try:
        pairs = [
            (query, str(ch.get(content_field) or ch.get("text") or "")[:512])
            for ch in chunks
        ]
        scores = model.predict(pairs)

        scored = sorted(zip(chunks, scores), key=lambda x: float(x[1]), reverse=True)

        result = []
        for ch, score in scored[:top_k]:
            ch = dict(ch)
            ch["_rerank_score"] = float(score)
            result.append(ch)
        return result

    except Exception as exc:
        logger.error(f"Cross-encoder rerank falhou: {exc}")
        return chunks[:top_k]


# ─── LLM reranking (fallback) ────────────────────────────────────────────────

def llm_rerank(
    query: str,
    chunks: List[Dict[str, Any]],
    anthropic_client: anthropic.Anthropic,
    top_k: int = 7,
    pool_size: int = 15,
    max_chars: int = 1200,
    content_field: str = "content",
) -> List[Dict[str, Any]]:
    """
    Reranka chunks usando Anthropic Claude (haiku — rápido e barato).
    Usado quando cross-encoder não está disponível.
    """
    if not chunks or not anthropic_client:
        return chunks

    model_name = os.getenv("ANTHROPIC_MODEL_RERANK", "claude-haiku-4-5-20251001")
    pool = chunks[: max(1, min(pool_size, len(chunks)))]

    cards = []
    for i, ch in enumerate(pool, start=1):
        content = str(ch.get(content_field) or ch.get("text") or "")[:max_chars]
        source = str(ch.get("arquivo_origem") or ch.get("source") or "")[:120]
        raw_score = ch.get("_rrf_score") or ch.get("_score")
        cards.append({
            "id": i,
            "source": source,
            "score": float(raw_score) if isinstance(raw_score, (int, float)) and not math.isnan(float(raw_score)) else None,
            "content": content,
        })

    system = (
        "Você é um reranker especializado em documentos jurídicos brasileiros. "
        "Ordene os trechos pelo quanto ajudam a responder a pergunta. "
        "Responda SOMENTE com JSON válido, sem explicações adicionais."
    )
    user_payload = {
        "query": query,
        "instrucoes": (
            "Ordene os trechos do mais ao menos relevante para responder a query jurídica. "
            f"Retorne no máximo {min(top_k, len(cards))} ids. "
            'Formato exato: {"ranked_ids": [3, 1, 2]}'
        ),
        "chunks": cards,
    }

    try:
        resp = anthropic_client.messages.create(
            model=model_name,
            max_tokens=512,
            system=system,
            messages=[
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        )
        raw = (resp.content[0].text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        ranked_ids = [int(x) for x in data.get("ranked_ids", []) if 1 <= int(x) <= len(pool)]

        if not ranked_ids:
            return chunks

        id_to_chunk = {i + 1: pool[i] for i in range(len(pool))}
        used = set(ranked_ids)
        reranked = [id_to_chunk[i] for i in ranked_ids if i in id_to_chunk]
        remaining = [ch for idx, ch in id_to_chunk.items() if idx not in used]
        return reranked + remaining + chunks[len(pool):]

    except Exception as exc:
        logger.error(f"Claude rerank falhou: {exc}")
        return chunks


# ─── Unified entry point ──────────────────────────────────────────────────────

def rerank(
    query: str,
    chunks: List[Dict[str, Any]],
    top_k: int = 7,
    anthropic_client: Optional[anthropic.Anthropic] = None,
    use_cross_encoder: bool = True,
    content_field: str = "content",
) -> List[Dict[str, Any]]:
    """
    Ponto de entrada unificado para reranking.

    Fluxo:
      1. Se use_cross_encoder=True e o modelo estiver disponível → cross-encoder (local)
      2. Senão, se anthropic_client disponível → Claude reranking
      3. Senão → retorna top_k da ordem original

    Args:
        query: pergunta do usuário
        chunks: lista de chunks recuperados (dicts com content, chunk_id, etc.)
        top_k: número de chunks a retornar
        anthropic_client: instância Anthropic para fallback LLM
        use_cross_encoder: se deve tentar cross-encoder primeiro
        content_field: campo que contém o texto do chunk
    """
    if not chunks:
        return chunks

    if use_cross_encoder:
        model = _load_cross_encoder()
        if model is not None:
            return cross_encoder_rerank(query, chunks, top_k=top_k, content_field=content_field)

    if anthropic_client is not None:
        return llm_rerank(
            query, chunks,
            anthropic_client=anthropic_client,
            top_k=top_k,
            content_field=content_field,
        )

    logger.warning("Nenhum método de reranking disponível, retornando ordem original.")
    return chunks[:top_k]
