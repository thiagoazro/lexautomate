"""
indexer.py
Pipeline de indexação de documentos jurídicos no OpenSearch.

Lê todos os documentos de `documentos_juridicos/`, extrai texto,
divide em chunks, gera embeddings (OpenAI) e indexa no OpenSearch.

Uso:
    python indexer.py
    python indexer.py --recreate          # apaga e recria o índice
    python indexer.py --folder minha_pasta
    python indexer.py --chunk-size 800 --chunk-overlap 100
    python indexer.py --skip-existing     # pula documentos já indexados
    python indexer.py --dry-run           # mostra o que seria indexado, sem indexar

Suporte a formatos: .pdf, .docx, .txt, .md
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Configuração ─────────────────────────────────────────────────────────────

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_EMBEDDING_MODEL = (os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-large").strip()
OPENSEARCH_HOST = (os.getenv("OPENSEARCH_HOST") or "http://localhost:9200").strip()
OPENSEARCH_INDEX = (os.getenv("OPENSEARCH_INDEX") or "docs-index").strip()
EMBEDDING_DIM = 3072

DEFAULT_FOLDER = "documentos_juridicos"
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_BATCH_SIZE = 20   # chunks por chamada de embedding API
DEFAULT_INDEX_BATCH = 100  # docs por bulk index


# ─── Chunking ────────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """
    Divide o texto em chunks com sobreposição.

    Estratégia hierárquica:
      1. Tenta dividir por parágrafos duplos (\\n\\n)
      2. Senão por parágrafo simples (\\n)
      3. Senão por sentença (". ")
      4. Senão por espaço
      5. Senão por caractere

    Garante que nenhum chunk excede chunk_size (exceto se uma unidade
    indivisível já for maior).
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    separators = ["\n\n", "\n", ". ", ", ", " ", ""]
    chunks: List[str] = []

    def _split(t: str, sep_idx: int) -> List[str]:
        if len(t) <= chunk_size or sep_idx >= len(separators):
            return [t] if t.strip() else []
        sep = separators[sep_idx]
        if not sep:
            # Character-level split as last resort
            return [t[i: i + chunk_size] for i in range(0, len(t), chunk_size - overlap)]
        parts = t.split(sep)
        result = []
        current = ""
        for part in parts:
            candidate = (current + sep + part).strip() if current else part.strip()
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    result.append(current)
                if len(part) > chunk_size:
                    # Recursively split the oversized part
                    result.extend(_split(part, sep_idx + 1))
                    current = ""
                else:
                    current = part.strip()
        if current:
            result.append(current)
        return result

    raw_chunks = _split(text, sep_idx=0)

    # Apply overlap: each chunk starts overlap chars before where the previous ended
    if len(raw_chunks) <= 1:
        return raw_chunks

    result = [raw_chunks[0]]
    for i in range(1, len(raw_chunks)):
        prev_tail = result[-1][-overlap:] if overlap > 0 else ""
        merged = (prev_tail + " " + raw_chunks[i]).strip()
        # Don't add overlap if it makes the chunk too big
        if len(merged) <= chunk_size + overlap:
            result.append(merged)
        else:
            result.append(raw_chunks[i])

    return [c for c in result if c.strip()]


# ─── Classificação de tipo de documento ──────────────────────────────────────

def _classify_tipo_documento(rel_path: str) -> Tuple[str, str]:
    """
    Classifica o documento com base no caminho relativo dentro de documentos_juridicos/.

    Returns:
        (tipo_documento, area_direito)
    """
    parts = Path(rel_path).parts

    # Remove o arquivo do final
    dirs = parts[:-1] if len(parts) > 1 else parts

    if not dirs:
        return "documento", "geral"

    top = dirs[0].upper().strip().replace("-", "").strip()

    area_map = {
        "LEGISLAÇÃO": "legislacao",
        "LEGISLACAO": "legislacao",
        "JURISPRUDENCIA": "jurisprudencia",
        "JURISPRUDÊNCIA": "jurisprudencia",
        "DOUTRINA": "doutrina",
        "PECAS": "peca",
        "PEÇAS": "peca",
    }

    area = area_map.get(top, top.lower())

    # Tipo mais específico: subdirectório
    if len(dirs) >= 2:
        sub = dirs[1].lstrip("- ").upper().strip()
        tipo = re.sub(r"[^\w\s]", "", sub).strip().replace(" ", "_").lower()
    else:
        tipo = area

    return tipo, area


# ─── Extração de texto ────────────────────────────────────────────────────────

def extract_text(file_path: Path) -> str:
    """Extrai texto de PDF, DOCX, TXT ou MD."""
    try:
        from rag_docintelligence import extrair_texto_documento
        return extrair_texto_documento(str(file_path), file_path.suffix)
    except Exception as exc:
        logger.error(f"Falha ao extrair texto de {file_path}: {exc}")
        return ""


# ─── Embeddings em lote ───────────────────────────────────────────────────────

def embed_batch(
    texts: List[str],
    client: OpenAI,
    max_retries: int = 3,
) -> List[Optional[List[float]]]:
    """Gera embeddings para uma lista de textos. Retorna None onde falhou."""
    results: List[Optional[List[float]]] = [None] * len(texts)
    cleaned = [" ".join(t.replace("\n", " ").split())[:8000] for t in texts]

    for attempt in range(max_retries):
        try:
            resp = client.embeddings.create(
                model=OPENAI_EMBEDDING_MODEL,
                input=cleaned,
            )
            for item in resp.data:
                results[item.index] = item.embedding
            return results
        except Exception as exc:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Embedding batch failed (attempt {attempt+1}): {exc}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Embedding batch failed permanently: {exc}")

    return results


# ─── Verificar documentos já indexados ───────────────────────────────────────

def get_indexed_document_ids(client, index: str) -> set:
    """Retorna o conjunto de document_ids já indexados."""
    try:
        resp = client.search(
            index=index,
            body={
                "size": 0,
                "aggs": {"doc_ids": {"terms": {"field": "document_id", "size": 100000}}},
            },
        )
        buckets = resp.get("aggregations", {}).get("doc_ids", {}).get("buckets", [])
        return {b["key"] for b in buckets}
    except Exception as exc:
        logger.warning(f"Não foi possível verificar documentos existentes: {exc}")
        return set()


# ─── Pipeline de indexação ────────────────────────────────────────────────────

def make_document_id(file_path: Path, base_folder: Path) -> str:
    """Gera um document_id determinístico a partir do caminho relativo."""
    rel = str(file_path.relative_to(base_folder))
    return hashlib.md5(rel.encode()).hexdigest()


def iter_documents(
    folder: Path,
    skip_existing: Optional[set] = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Itera recursivamente sobre os arquivos de documentos suportados.
    Yield: dict com metadados (sem embedding ainda).
    """
    supported = {".pdf", ".docx", ".txt", ".md"}

    for file_path in sorted(folder.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in supported:
            continue
        if file_path.name.startswith("."):
            continue

        rel_path = str(file_path.relative_to(folder))
        doc_id = make_document_id(file_path, folder)

        if skip_existing and doc_id in skip_existing:
            logger.debug(f"Pulando (já indexado): {rel_path}")
            continue

        tipo, area = _classify_tipo_documento(rel_path)

        yield {
            "file_path": file_path,
            "document_id": doc_id,
            "arquivo_origem": file_path.name,
            "path_relativo": rel_path,
            "tipo_documento": tipo,
            "area_direito": area,
            "language_code": "pt",
        }


def index_folder(
    folder: str = DEFAULT_FOLDER,
    recreate: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    batch_size: int = DEFAULT_BATCH_SIZE,
    index_batch: int = DEFAULT_INDEX_BATCH,
    skip_existing: bool = False,
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Indexa todos os documentos da pasta no OpenSearch.

    Returns:
        dict com estatísticas: files_processed, chunks_indexed, chunks_failed, files_failed
    """
    from opensearch_utils import (
        get_opensearch_client, ensure_index, bulk_index_documents
    )

    stats = {
        "files_processed": 0,
        "files_skipped": 0,
        "files_failed": 0,
        "chunks_indexed": 0,
        "chunks_failed": 0,
    }

    folder_path = Path(folder)
    if not folder_path.is_dir():
        logger.error(f"Pasta não encontrada: {folder}")
        return stats

    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY não configurada.")
        return stats

    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    if dry_run:
        logger.info("=== DRY RUN — nenhum dado será indexado ===")
        for meta in iter_documents(folder_path):
            text = extract_text(meta["file_path"])
            if text:
                chunks = chunk_text(text, chunk_size, chunk_overlap)
                logger.info(
                    f"[DRY] {meta['path_relativo']}  →  {len(chunks)} chunks  "
                    f"(tipo={meta['tipo_documento']}, area={meta['area_direito']})"
                )
                stats["files_processed"] += 1
                stats["chunks_indexed"] += len(chunks)
            else:
                stats["files_failed"] += 1
        return stats

    os_client = get_opensearch_client()
    if not os_client.ping():
        logger.error(f"OpenSearch indisponível em {OPENSEARCH_HOST}")
        return stats

    ensure_index(os_client, OPENSEARCH_INDEX, embedding_dim=EMBEDDING_DIM, recreate=recreate)
    logger.info(f"Índice '{OPENSEARCH_INDEX}' pronto.")

    # Documentos já indexados (para --skip-existing)
    indexed_ids: set = set()
    if skip_existing:
        indexed_ids = get_indexed_document_ids(os_client, OPENSEARCH_INDEX)
        logger.info(f"Documentos já indexados: {len(indexed_ids)}")

    # Buffer para indexação em lote
    pending_docs: List[Dict[str, Any]] = []

    def flush_pending():
        if not pending_docs:
            return
        success, errors = bulk_index_documents(os_client, pending_docs, OPENSEARCH_INDEX)
        stats["chunks_indexed"] += success
        stats["chunks_failed"] += errors
        pending_docs.clear()
        if errors:
            logger.warning(f"  {errors} chunks falharam no bulk index")

    for meta in iter_documents(folder_path, skip_existing=indexed_ids if skip_existing else None):
        file_path: Path = meta.pop("file_path")
        rel_path = meta["path_relativo"]

        logger.info(f"Processando: {rel_path}")

        text = extract_text(file_path)
        if not text or len(text.strip()) < 30:
            logger.warning(f"  Sem texto extraível. Pulando.")
            stats["files_failed"] += 1
            continue

        chunks = chunk_text(text, chunk_size, chunk_overlap)
        if not chunks:
            logger.warning(f"  Sem chunks gerados. Pulando.")
            stats["files_failed"] += 1
            continue

        logger.info(f"  {len(chunks)} chunks")
        stats["files_processed"] += 1

        # Processa em sub-lotes para os embeddings
        for batch_start in range(0, len(chunks), batch_size):
            batch_texts = chunks[batch_start: batch_start + batch_size]
            embeddings = embed_batch(batch_texts, openai_client)

            for i, (chunk_text_val, emb) in enumerate(zip(batch_texts, embeddings)):
                if emb is None:
                    logger.warning(f"    Chunk {batch_start + i} sem embedding — pulando")
                    stats["chunks_failed"] += 1
                    continue

                chunk_idx = batch_start + i
                chunk_id = f"{meta['document_id']}_{chunk_idx}"

                doc = {
                    **meta,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                    "content": chunk_text_val,
                    "content_vector": emb,
                }
                pending_docs.append(doc)

            # Flush quando buffer atingir index_batch
            if len(pending_docs) >= index_batch:
                flush_pending()

        # Pequena pausa para evitar rate limit da API
        time.sleep(0.1)

    # Flush final
    flush_pending()

    logger.info(
        f"\n{'='*50}\n"
        f"Indexação concluída:\n"
        f"  Arquivos processados: {stats['files_processed']}\n"
        f"  Arquivos com falha:   {stats['files_failed']}\n"
        f"  Chunks indexados:     {stats['chunks_indexed']}\n"
        f"  Chunks com falha:     {stats['chunks_failed']}\n"
        f"{'='*50}"
    )

    return stats


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Indexa documentos jurídicos no OpenSearch para busca híbrida RAG."
    )
    parser.add_argument(
        "--folder",
        default=DEFAULT_FOLDER,
        help=f"Pasta com os documentos (padrão: {DEFAULT_FOLDER})",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Apaga e recria o índice antes de indexar",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Pula documentos cujo document_id já está no índice",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria indexado sem de fato indexar",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Tamanho de cada chunk em caracteres (padrão: {DEFAULT_CHUNK_SIZE})",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help=f"Sobreposição entre chunks (padrão: {DEFAULT_CHUNK_OVERLAP})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Chunks por chamada de embedding API (padrão: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Exibe logs de debug",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    index_folder(
        folder=args.folder,
        recreate=args.recreate,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        batch_size=args.batch_size,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
