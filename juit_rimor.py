"""
juit_rimor.py
Integração com a API JuIT Rimor para busca de jurisprudência pública.

Ativação: basta definir JUIT_API_KEY no .env.
Se não definida, o módulo é desativado silenciosamente.

Documentação: https://docs.juit.dev
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

JUIT_API_KEY = (os.getenv("JUIT_API_KEY") or "").strip()
JUIT_BASE_URL = (os.getenv("JUIT_BASE_URL") or "https://api.juit.dev").strip()


def is_available() -> bool:
    """Retorna True se a API JuIT Rimor está configurada."""
    return bool(JUIT_API_KEY)


def buscar_jurisprudencias(
    query: str,
    search_on: str = "ementa,integra",
    top_k: int = 10,
    sort_by_field: Optional[List[str]] = None,
    sort_by_direction: Optional[List[str]] = None,
    tribunal: Optional[str] = None,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """
    Busca jurisprudências na API JuIT Rimor.

    Args:
        query: texto de busca
        search_on: campos para buscar ("ementa", "integra", "ementa,integra")
        top_k: número máximo de resultados
        sort_by_field: campos de ordenação (ex: ["score", "date"])
        sort_by_direction: direção da ordenação (ex: ["desc", "desc"])
        tribunal: filtrar por tribunal (ex: "STF", "STJ", "TST")
        timeout: timeout em segundos

    Returns:
        Lista de dicts com campos padronizados para o pipeline RAG.
    """
    if not JUIT_API_KEY:
        return []

    if sort_by_field is None:
        sort_by_field = ["score", "date"]
    if sort_by_direction is None:
        sort_by_direction = ["desc", "desc"]

    params: Dict[str, Any] = {
        "query": query,
        "search_on": search_on,
        "sort_by_field": sort_by_field,
        "sort_by_direction": sort_by_direction,
        "limit": top_k,
    }

    if tribunal:
        params["tribunal"] = tribunal

    headers = {
        "Authorization": f"Bearer {JUIT_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(
            f"{JUIT_BASE_URL}/jurisprudence",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

        # Normalizar resultados para o formato do pipeline RAG
        results = []
        items = data if isinstance(data, list) else data.get("results", data.get("data", []))

        for item in items[:top_k]:
            result = normalize_juit_result(item)
            if result:
                results.append(result)

        logger.info(f"JuIT Rimor: {len(results)} jurisprudências encontradas para '{query[:50]}...'")
        return results

    except requests.exceptions.Timeout:
        logger.warning(f"JuIT Rimor: timeout após {timeout}s")
        return []
    except requests.exceptions.HTTPError as exc:
        logger.error(f"JuIT Rimor HTTP error: {exc}")
        return []
    except Exception as exc:
        logger.error(f"JuIT Rimor falhou: {exc}")
        return []


def normalize_juit_result(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Converte um resultado da JuIT Rimor para o formato padrão do pipeline RAG.
    Assim os resultados podem ser mesclados com os do Qdrant.
    """
    # Tentar extrair campos comuns da API JuIT
    ementa = (
        item.get("headnote")
        or item.get("ementa")
        or item.get("summary")
        or ""
    ).strip()

    if not ementa:
        return None

    # Extrair metadados
    tribunal = (
        item.get("court")
        or item.get("tribunal")
        or ""
    ).strip()

    numero_processo = (
        item.get("case_number")
        or item.get("numero_processo")
        or item.get("number")
        or ""
    ).strip()

    relator = (
        item.get("rapporteur")
        or item.get("relator")
        or ""
    ).strip()

    data_julgamento = (
        item.get("judgment_date")
        or item.get("data_julgamento")
        or item.get("date")
        or ""
    ).strip()

    orgao_julgador = (
        item.get("judging_body")
        or item.get("orgao_julgador")
        or ""
    ).strip()

    # Montar o content com metadados relevantes
    content_parts = []
    if tribunal and numero_processo:
        content_parts.append(f"{tribunal} - {numero_processo}")
    elif tribunal:
        content_parts.append(tribunal)
    if relator:
        content_parts.append(f"Relator: {relator}")
    if orgao_julgador:
        content_parts.append(f"Órgão: {orgao_julgador}")
    if data_julgamento:
        content_parts.append(f"Data: {data_julgamento}")

    header = " | ".join(content_parts)
    content = f"{header}\n\n{ementa}" if header else ementa

    return {
        "content": content,
        "chunk_id": f"juit_{numero_processo or id(item)}",
        "document_id": f"juit_{numero_processo or id(item)}",
        "arquivo_origem": f"JuIT Rimor - {tribunal} {numero_processo}".strip(),
        "tipo_documento": "jurisprudencia",
        "area_direito": "jurisprudencia",
        "language_code": "pt",
        "_source": "juit_rimor",
        "_juit_raw": item,  # preserva dados originais
    }
