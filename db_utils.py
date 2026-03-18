# db_utils.py
# MongoDB integration for legal document template models.
# No Streamlit dependencies.

from __future__ import annotations

import datetime
import functools
import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure

load_dotenv()
logger = logging.getLogger(__name__)

MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "lexautomate").strip()
MONGODB_COLLECTION_MODELOS = os.getenv("MONGODB_COLLECTION_MODELOS", "modelos_pecas").strip()

# Module-level singleton
_mongodb_client: Optional[MongoClient] = None


def get_mongodb_client() -> Optional[MongoClient]:
    global _mongodb_client
    if _mongodb_client is not None:
        return _mongodb_client

    uri = MONGODB_URI
    if not uri:
        logger.error("MONGODB_URI not set in environment.")
        return None

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        logger.info("MongoDB connection established.")
        _mongodb_client = client
        return client
    except ConnectionFailure as exc:
        logger.error(f"MongoDB connection failed: {exc}")
        return None
    except Exception as exc:
        logger.error(f"Unexpected MongoDB error: {exc}")
        return None


def get_modelos_collection():
    client = get_mongodb_client()
    if client is None:
        return None
    return client[MONGODB_DB_NAME][MONGODB_COLLECTION_MODELOS]


@functools.lru_cache(maxsize=1)
def carregar_modelos_pecas_from_mongodb() -> Dict[str, Any]:
    """Load all model templates from MongoDB into a nested dict."""
    collection = get_modelos_collection()
    if collection is None:
        logger.warning("Models collection unavailable.")
        return {}

    modelos_data: Dict[str, Any] = {}
    try:
        for doc in collection.find({}):
            area = doc.get("area_direito")
            tipo_peca = doc.get("tipo_peca")
            nome_modelo = doc.get("nome_modelo")

            if area and tipo_peca and nome_modelo:
                modelos_data.setdefault(area, {}).setdefault(tipo_peca, {})[nome_modelo] = {
                    "descricao": doc.get("descricao", ""),
                    "reivindicacoes_comuns": doc.get("reivindicacoes_comuns", []),
                    "prompt_template": doc.get("prompt_template", ""),
                    "tags": doc.get("tags", []),
                    "legislacao_relevante": doc.get("legislacao_relevante", []),
                    "jurisprudencia_exemplar": doc.get("jurisprudencia_exemplar", []),
                    "requisitos_especificos": doc.get("requisitos_especificos", ""),
                    "complexidade": doc.get("complexidade", ""),
                    "autor_modelo": doc.get("autor_modelo", ""),
                }

        total = sum(len(v2) for v in modelos_data.values() for v2 in v.values())
        logger.info(f"Loaded {total} models from MongoDB.")
        return modelos_data

    except OperationFailure as exc:
        logger.error(f"MongoDB operation error: {exc.details}")
        return {}
    except Exception as exc:
        logger.error(f"Unexpected error loading models: {exc}")
        return {}


def inserir_modelo_peca(
    area: str,
    tipo_peca: str,
    nome_modelo: str,
    prompt_template: str,
    reivindicacoes_comuns: list,
    descricao: str = "",
    tags: list = None,
    legislacao_relevante: list = None,
    jurisprudencia_exemplar: list = None,
    requisitos_especificos: str = "",
    complexidade: str = "",
    autor_modelo: str = "",
) -> bool:
    collection = get_modelos_collection()
    if collection is None:
        return False

    try:
        doc = {
            "area_direito": area,
            "tipo_peca": tipo_peca,
            "nome_modelo": nome_modelo,
            "prompt_template": prompt_template,
            "reivindicacoes_comuns": reivindicacoes_comuns or [],
            "descricao": descricao,
            "tags": tags or [],
            "legislacao_relevante": legislacao_relevante or [],
            "jurisprudencia_exemplar": jurisprudencia_exemplar or [],
            "requisitos_especificos": requisitos_especificos,
            "complexidade": complexidade,
            "autor_modelo": autor_modelo,
            "data_atualizacao": datetime.datetime.now(),
        }
        result = collection.update_one(
            {"area_direito": area, "tipo_peca": tipo_peca, "nome_modelo": nome_modelo},
            {"$set": doc, "$setOnInsert": {"data_criacao": datetime.datetime.now()}},
            upsert=True,
        )
        # Invalidate cache
        carregar_modelos_pecas_from_mongodb.cache_clear()

        if result.upserted_id:
            logger.info(f"Model '{nome_modelo}' inserted.")
        elif result.modified_count > 0:
            logger.info(f"Model '{nome_modelo}' updated.")
        return True

    except Exception as exc:
        logger.error(f"Error inserting model '{nome_modelo}': {exc}")
        return False
