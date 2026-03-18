"""
opensearch_utils.py
Utilitários para OpenSearch: conexão, mapeamento de índice híbrido e indexação em lote.

Mapeamento:
  - BM25: analyzer português customizado (tokenização, stop words, stemmer light_portuguese, asciifolding)
  - kNN:  vetor HNSW (cosine similarity, nmslib) para dense retrieval
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from opensearchpy import OpenSearch, RequestsHttpConnection, helpers

DEFAULT_INDEX_NAME = os.getenv("OPENSEARCH_INDEX", "docs-index")


def get_opensearch_client(
    host: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    verify_certs: Optional[bool] = None,
    ca_certs: Optional[str] = None,
    timeout: int = 60,
) -> OpenSearch:
    """Cria e retorna um cliente OpenSearch."""
    host = host or os.getenv("OPENSEARCH_HOST", "http://localhost:9200")

    if verify_certs is None:
        v = os.getenv("OPENSEARCH_VERIFY_CERTS", "false").strip().lower()
        verify_certs = v in ("1", "true", "yes", "y")

    username = username if username is not None else os.getenv("OPENSEARCH_USERNAME", "").strip() or None
    password = password if password is not None else os.getenv("OPENSEARCH_PASSWORD", "").strip() or None
    ca_certs = ca_certs or os.getenv("OPENSEARCH_CA_CERTS", "").strip() or None

    http_auth = (username, password) if username and password else None

    return OpenSearch(
        hosts=[host],
        http_auth=http_auth,
        use_ssl=host.startswith("https://"),
        verify_certs=bool(verify_certs),
        ca_certs=ca_certs,
        connection_class=RequestsHttpConnection,
        timeout=timeout,
        max_retries=3,
        retry_on_timeout=True,
    )


def build_default_index_body(embedding_dim: int = 3072) -> Dict[str, Any]:
    """
    Mapeamento híbrido para RAG jurídico:

    BM25 (campo `content`):
      - Tokenizador padrão
      - Lowercase
      - Stop words portuguesas (_portuguese_)
      - Stemmer light_portuguese (menos agressivo, melhor para termos jurídicos)
      - Asciifolding (ação → acao, para buscas sem acento)

    Dense retrieval (campo `content_vector`):
      - knn_vector 3072 dims
      - HNSW cosine similarity (nmslib)
      - ef_construction=256, m=16 para boa qualidade de recall
    """
    return {
        "settings": {
            "index": {
                "knn": True,
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "analysis": {
                "analyzer": {
                    "pt_legal_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": [
                            "lowercase",
                            "pt_stop_filter",
                            "pt_stemmer_filter",
                            "asciifolding",
                        ],
                    }
                },
                "filter": {
                    "pt_stop_filter": {
                        "type": "stop",
                        "stopwords": "_portuguese_",
                    },
                    "pt_stemmer_filter": {
                        "type": "stemmer",
                        "language": "light_portuguese",
                    },
                },
            },
        },
        "mappings": {
            "properties": {
                # ── Identificação ──────────────────────────────────────────
                "chunk_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "arquivo_origem": {"type": "keyword"},
                "path_relativo": {"type": "keyword"},

                # ── Classificação ──────────────────────────────────────────
                "tipo_documento": {"type": "keyword"},
                "area_direito": {"type": "keyword"},
                "language_code": {"type": "keyword"},

                # ── Texto (BM25) ───────────────────────────────────────────
                "content": {
                    "type": "text",
                    "analyzer": "pt_legal_analyzer",
                    "search_analyzer": "pt_legal_analyzer",
                },

                # ── Vetor semântico (kNN dense retrieval) ──────────────────
                "content_vector": {
                    "type": "knn_vector",
                    "dimension": int(embedding_dim),
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                        "parameters": {
                            "ef_construction": 256,
                            "m": 16,
                        },
                    },
                },

                # ── Metadados extras ───────────────────────────────────────
                "chunk_index": {"type": "integer"},
                "total_chunks": {"type": "integer"},
            }
        },
    }


def ensure_index(
    client: OpenSearch,
    index_name: str = DEFAULT_INDEX_NAME,
    embedding_dim: int = 3072,
    recreate: bool = False,
) -> None:
    """Garante que o índice existe com o mapeamento correto."""
    exists = client.indices.exists(index=index_name)

    if exists and recreate:
        client.indices.delete(index=index_name)
        exists = False

    if not exists:
        body = build_default_index_body(embedding_dim=embedding_dim)
        client.indices.create(index=index_name, body=body)


def bulk_index_documents(
    client: OpenSearch,
    docs: Iterable[Dict[str, Any]],
    index_name: str = DEFAULT_INDEX_NAME,
    id_field: Optional[str] = "chunk_id",
    refresh: bool = False,
    chunk_size: int = 200,
    request_timeout: int = 120,
) -> Tuple[int, int]:
    """
    Indexa documentos em lote.
    Cada doc deve conter `content` (str) e `content_vector` (List[float]).
    Retorna (success_count, error_count).
    """
    actions = []
    for d in docs:
        _id = d.get(id_field) if id_field else None
        action: Dict[str, Any] = {
            "_op_type": "index",
            "_index": index_name,
            "_source": d,
        }
        if _id is not None:
            action["_id"] = str(_id)
        actions.append(action)

    if not actions:
        return 0, 0

    success, errors = helpers.bulk(
        client,
        actions,
        chunk_size=chunk_size,
        request_timeout=request_timeout,
        raise_on_error=False,
        raise_on_exception=False,
        refresh=refresh,
    )
    error_count = len(errors) if isinstance(errors, list) else int(bool(errors))
    return int(success), int(error_count)


def ping(client: OpenSearch) -> bool:
    try:
        return bool(client.ping())
    except Exception:
        return False
