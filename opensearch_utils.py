"""
opensearch_utils.py
Utilities to connect to OpenSearch, create an index mapping for hybrid (BM25 + kNN),
and bulk index documents with vectors.

Requirements:
  pip install opensearch-py

Environment variables (recommended):
  OPENSEARCH_HOST=http://localhost:9200
  OPENSEARCH_USERNAME=          (optional)
  OPENSEARCH_PASSWORD=          (optional)
  OPENSEARCH_VERIFY_CERTS=false (optional)
  OPENSEARCH_CA_CERTS=          (optional)
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
    """
    Creates an OpenSearch client.
    Supports local dev with DISABLE_SECURITY_PLUGIN=true (no auth) or secured clusters (basic auth).
    """
    host = host or os.getenv("OPENSEARCH_HOST", "http://localhost:9200")

    # If verify_certs not set, infer from env
    if verify_certs is None:
        v = os.getenv("OPENSEARCH_VERIFY_CERTS", "false").strip().lower()
        verify_certs = v in ("1", "true", "yes", "y")

    username = username if username is not None else os.getenv("OPENSEARCH_USERNAME", "").strip() or None
    password = password if password is not None else os.getenv("OPENSEARCH_PASSWORD", "").strip() or None
    ca_certs = ca_certs or os.getenv("OPENSEARCH_CA_CERTS", "").strip() or None

    http_auth = (username, password) if username and password else None

    client = OpenSearch(
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
    return client


def build_default_index_body(embedding_dim: int = 3072) -> Dict[str, Any]:
    """
    Default mapping/settings aligned with the existing codebase fields:
      chunk_id, document_id, arquivo_origem, tipo_documento, language_code, content, content_vector
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
                    # You can customize this later (e.g., brazilian analyzer if you install plugins)
                    "pt_analyzer": {"type": "standard"}
                }
            },
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "arquivo_origem": {"type": "keyword"},
                "tipo_documento": {"type": "keyword"},
                "language_code": {"type": "keyword"},
                "content": {"type": "text", "analyzer": "pt_analyzer"},
                "content_vector": {
                    "type": "knn_vector",
                    "dimension": int(embedding_dim),
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                        "parameters": {"ef_construction": 128, "m": 16},
                    },
                },
            }
        },
    }


def ensure_index(
    client: OpenSearch,
    index_name: str = DEFAULT_INDEX_NAME,
    embedding_dim: int = 3072,
    recreate: bool = False,
) -> None:
    """
    Ensures index exists with the expected mapping. If recreate=True, deletes and recreates.
    """
    exists = client.indices.exists(index=index_name)
    if exists and recreate:
        client.indices.delete(index=index_name)

    if not client.indices.exists(index=index_name):
        body = build_default_index_body(embedding_dim=embedding_dim)
        client.indices.create(index=index_name, body=body)


def bulk_index_documents(
    client: OpenSearch,
    docs: Iterable[Dict[str, Any]],
    index_name: str = DEFAULT_INDEX_NAME,
    id_field: Optional[str] = "chunk_id",
    refresh: bool = False,
    chunk_size: int = 500,
    request_timeout: int = 120,
) -> Tuple[int, int]:
    """
    Bulk indexes docs. Each doc must already include content_vector (list[float]) and content.
    Returns (success_count, error_count).
    """
    actions = []
    for d in docs:
        _id = d.get(id_field) if id_field else None
        action = {"_op_type": "index", "_index": index_name, "_source": d}
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
    # helpers.bulk returns (successes, errors) where errors is list if raise_on_error=False
    error_count = len(errors) if isinstance(errors, list) else int(bool(errors))
    return int(success), int(error_count)


def ping(client: OpenSearch) -> bool:
    try:
        return bool(client.ping())
    except Exception:
        return False
