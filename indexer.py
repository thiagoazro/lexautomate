"""
indexer.py
Pipeline de indexação de documentos jurídicos no Qdrant Cloud.

Para cada documento:
  1. Extrai texto (PDF/DOCX/TXT/MD)
  2. Divide em chunks com sobreposição
  3. Gera embedding denso (OpenAI text-embedding-3-large)
  4. Gera embedding esparso BM25 (fastembed Qdrant/bm25)
  5. Insere no Qdrant (coleção híbrida dense + sparse)

Uso:
    python indexer.py                    # indexa documentos_juridicos/
    python indexer.py --recreate         # apaga coleção e recria
    python indexer.py --skip-existing    # pula docs já indexados
    python indexer.py --dry-run          # mostra o que faria, sem indexar
    python indexer.py --folder outra/    # pasta customizada
    python indexer.py --chunk-size 800 --chunk-overlap 120
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

# ─── Config ───────────────────────────────────────────────────────────────────

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_EMBEDDING_MODEL = (os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-large").strip()
QDRANT_COLLECTION = (os.getenv("QDRANT_COLLECTION") or "docs-index").strip()
EMBEDDING_DIM = 3072

DEFAULT_FOLDER = "documentos_juridicos"
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_EMBED_BATCH = 20     # chunks por chamada embedding API
DEFAULT_UPSERT_BATCH = 100   # pontos por upsert Qdrant


# ─── Chunking ────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[str]:
    """Divide texto em chunks com sobreposição, usando estratégia hierárquica."""
    if not text or not text.strip():
        return []

    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    separators = ["\n\n", "\n", ". ", ", ", " ", ""]

    def _split(t: str, sep_idx: int) -> List[str]:
        if len(t) <= chunk_size or sep_idx >= len(separators):
            return [t] if t.strip() else []
        sep = separators[sep_idx]
        if not sep:
            return [t[i: i + chunk_size] for i in range(0, len(t), max(1, chunk_size - overlap))]
        parts = t.split(sep)
        result, current = [], ""
        for part in parts:
            candidate = (current + sep + part).strip() if current else part.strip()
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    result.append(current)
                if len(part) > chunk_size:
                    result.extend(_split(part, sep_idx + 1))
                    current = ""
                else:
                    current = part.strip()
        if current:
            result.append(current)
        return result

    raw = _split(text, 0)
    if len(raw) <= 1:
        return raw

    # Aplicar sobreposição
    result = [raw[0]]
    for i in range(1, len(raw)):
        prev_tail = result[-1][-overlap:] if overlap > 0 else ""
        merged = (prev_tail + " " + raw[i]).strip()
        result.append(merged if len(merged) <= chunk_size + overlap else raw[i])

    return [c for c in result if c.strip()]


# ─── Classificação por pasta ───────────────────────────────────────────────────

def classify_document(rel_path: str) -> Tuple[str, str]:
    """Retorna (tipo_documento, area_direito) a partir do caminho relativo."""
    parts = Path(rel_path).parts
    dirs = parts[:-1] if len(parts) > 1 else parts

    area_map = {
        "LEGISLAÇÃO": "legislacao", "LEGISLACAO": "legislacao",
        "JURISPRUDENCIA": "jurisprudencia", "JURISPRUDÊNCIA": "jurisprudencia",
        "DOUTRINA": "doutrina",
        "PECAS": "peca", "PEÇAS": "peca",
    }

    top = dirs[0].upper().strip() if dirs else ""
    area = area_map.get(top, top.lower() or "geral")

    if len(dirs) >= 2:
        sub = dirs[1].lstrip("- ").upper().strip()
        tipo = re.sub(r"[^\w\s]", "", sub).strip().replace(" ", "_").lower()
    else:
        tipo = area

    return tipo, area


# ─── Extração de texto ────────────────────────────────────────────────────────

def extract_text(file_path: Path) -> str:
    try:
        from rag_docintelligence import extrair_texto_documento
        return extrair_texto_documento(str(file_path), file_path.suffix)
    except Exception as exc:
        logger.error(f"Falha ao extrair {file_path.name}: {exc}")
        return ""


# ─── Embeddings ───────────────────────────────────────────────────────────────

def embed_batch_dense(texts: List[str], client: OpenAI, max_retries: int = 3) -> List[Optional[List[float]]]:
    """Gera embeddings densos em lote."""
    results: List[Optional[List[float]]] = [None] * len(texts)
    cleaned = [" ".join(t.replace("\n", " ").split())[:8000] for t in texts]

    for attempt in range(max_retries):
        try:
            resp = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=cleaned)
            for item in resp.data:
                results[item.index] = item.embedding
            return results
        except Exception as exc:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Embedding batch falhou (tentativa {attempt+1}): {exc}. Retry em {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Embedding batch falhou permanentemente: {exc}")

    return results


# ─── Verificar existentes ─────────────────────────────────────────────────────

def get_indexed_document_ids(qdrant_client, collection_name: str) -> set:
    """Retorna set de document_ids já indexados (via scroll)."""
    try:
        doc_ids = set()
        offset = None
        while True:
            result, offset = qdrant_client.scroll(
                collection_name=collection_name,
                scroll_filter=None,
                limit=1000,
                offset=offset,
                with_payload=["document_id"],
                with_vectors=False,
            )
            for point in result:
                did = (point.payload or {}).get("document_id")
                if did:
                    doc_ids.add(did)
            if offset is None:
                break
        return doc_ids
    except Exception as exc:
        logger.warning(f"Não foi possível verificar existentes: {exc}")
        return set()


# ─── Iterator de documentos ───────────────────────────────────────────────────

def make_document_id(file_path: Path, base: Path) -> str:
    rel = str(file_path.relative_to(base))
    return hashlib.md5(rel.encode()).hexdigest()


def iter_documents(folder: Path, skip_ids: Optional[set] = None) -> Generator[Dict[str, Any], None, None]:
    for file_path in sorted(folder.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".pdf", ".docx", ".txt", ".md"}:
            continue
        if file_path.name.startswith("."):
            continue

        rel_path = str(file_path.relative_to(folder))
        doc_id = make_document_id(file_path, folder)

        if skip_ids and doc_id in skip_ids:
            logger.debug(f"Pulando (já indexado): {rel_path}")
            continue

        tipo, area = classify_document(rel_path)
        yield {
            "file_path": file_path,
            "document_id": doc_id,
            "arquivo_origem": file_path.name,
            "path_relativo": rel_path,
            "tipo_documento": tipo,
            "area_direito": area,
            "language_code": "pt",
        }


# ─── Pipeline principal ───────────────────────────────────────────────────────

def index_folder(
    folder: str = DEFAULT_FOLDER,
    recreate: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    embed_batch: int = DEFAULT_EMBED_BATCH,
    upsert_batch: int = DEFAULT_UPSERT_BATCH,
    skip_existing: bool = False,
    dry_run: bool = False,
) -> Dict[str, int]:
    from qdrant_utils import get_qdrant_client, ensure_collection, upsert_points, embed_sparse

    stats = {"files_processed": 0, "files_failed": 0, "chunks_indexed": 0, "chunks_failed": 0}

    folder_path = Path(folder)
    if not folder_path.is_dir():
        logger.error(f"Pasta não encontrada: {folder}")
        return stats

    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY não configurada.")
        return stats

    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    if dry_run:
        logger.info("=== DRY RUN ===")
        for meta in iter_documents(folder_path):
            text = extract_text(meta["file_path"])
            if text:
                chunks = chunk_text(text, chunk_size, chunk_overlap)
                logger.info(f"[DRY] {meta['path_relativo']} → {len(chunks)} chunks ({meta['tipo_documento']})")
                stats["files_processed"] += 1
                stats["chunks_indexed"] += len(chunks)
            else:
                stats["files_failed"] += 1
        return stats

    qdrant = get_qdrant_client()
    ensure_collection(qdrant, QDRANT_COLLECTION, embedding_dim=EMBEDDING_DIM, recreate=recreate)
    logger.info(f"Coleção '{QDRANT_COLLECTION}' pronta.")

    skip_ids: set = set()
    if skip_existing:
        skip_ids = get_indexed_document_ids(qdrant, QDRANT_COLLECTION)
        logger.info(f"Documentos já indexados: {len(skip_ids)}")

    pending_points: List[Dict[str, Any]] = []

    def flush():
        if not pending_points:
            return
        ok, err = upsert_points(qdrant, pending_points, QDRANT_COLLECTION, batch_size=upsert_batch)
        stats["chunks_indexed"] += ok
        stats["chunks_failed"] += err
        pending_points.clear()
        if err:
            logger.warning(f"  {err} chunks falharam no upsert")

    for meta in iter_documents(folder_path, skip_ids=skip_ids if skip_existing else None):
        file_path: Path = meta.pop("file_path")
        rel_path = meta["path_relativo"]
        logger.info(f"Processando: {rel_path}")

        text = extract_text(file_path)
        if not text or len(text.strip()) < 30:
            logger.warning(f"  Sem texto. Pulando.")
            stats["files_failed"] += 1
            continue

        chunks = chunk_text(text, chunk_size, chunk_overlap)
        if not chunks:
            stats["files_failed"] += 1
            continue

        logger.info(f"  {len(chunks)} chunks")
        stats["files_processed"] += 1

        for batch_start in range(0, len(chunks), embed_batch):
            batch_texts = chunks[batch_start: batch_start + embed_batch]
            dense_embeddings = embed_batch_dense(batch_texts, openai_client)

            for i, (chunk_content, dense_emb) in enumerate(zip(batch_texts, dense_embeddings)):
                if dense_emb is None:
                    stats["chunks_failed"] += 1
                    continue

                chunk_idx = batch_start + i
                chunk_id = f"{meta['document_id']}_{chunk_idx}"

                # BM25 sparse embedding
                sparse_emb = embed_sparse(chunk_content)

                point = {
                    **meta,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                    "content": chunk_content,
                    "content_vector": dense_emb,
                    "sparse_vector": sparse_emb,  # None se BM25 indisponível
                }
                pending_points.append(point)

            if len(pending_points) >= upsert_batch:
                flush()

        time.sleep(0.05)  # evitar rate limit

    flush()

    logger.info(
        f"\n{'='*52}\n"
        f"Indexação concluída:\n"
        f"  Arquivos processados : {stats['files_processed']}\n"
        f"  Arquivos com falha   : {stats['files_failed']}\n"
        f"  Chunks indexados     : {stats['chunks_indexed']}\n"
        f"  Chunks com falha     : {stats['chunks_failed']}\n"
        f"{'='*52}"
    )
    return stats


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Indexa documentos jurídicos no Qdrant.")
    parser.add_argument("--folder", default=DEFAULT_FOLDER)
    parser.add_argument("--recreate", action="store_true", help="Apaga e recria a coleção")
    parser.add_argument("--skip-existing", action="store_true", help="Pula docs já indexados")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem indexar")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--embed-batch", type=int, default=DEFAULT_EMBED_BATCH)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    index_folder(
        folder=args.folder,
        recreate=args.recreate,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        embed_batch=args.embed_batch,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
