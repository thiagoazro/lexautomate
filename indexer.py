"""
indexer.py
Pipeline de indexação de documentos jurídicos no Qdrant Cloud.

Otimizado para grandes volumes (37k+ docs):
  - Embeddings com text-embedding-3-small (rápido, barato)
  - Batches grandes (até 2048 tokens por chamada OpenAI)
  - BM25 em lote (fastembed)
  - Processamento paralelo de documentos (extração de texto)
  - Barra de progresso

Uso:
    python indexer.py                          # indexa documentos_juridicos/
    python indexer.py --recreate               # apaga coleção e recria
    python indexer.py --skip-existing          # pula docs já indexados
    python indexer.py --dry-run                # mostra o que faria
    python indexer.py --folder outra/          # pasta customizada
    python indexer.py --workers 8              # threads para extração de texto
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
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
OPENAI_EMBEDDING_MODEL = (os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small").strip()
QDRANT_COLLECTION = (os.getenv("QDRANT_COLLECTION") or "docs-index").strip()

# text-embedding-3-small = 1536d, text-embedding-3-large = 3072d
EMBEDDING_DIM = 1536 if "small" in OPENAI_EMBEDDING_MODEL else 3072

DEFAULT_FOLDER = "documentos_juridicos"
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_EMBED_BATCH = 100    # OpenAI suporta até 2048 inputs por chamada
DEFAULT_UPSERT_BATCH = 100
DEFAULT_WORKERS = 4          # threads para extração de texto


# ─── Chunking ────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[str]:
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

    result = [raw[0]]
    for i in range(1, len(raw)):
        prev_tail = result[-1][-overlap:] if overlap > 0 else ""
        merged = (prev_tail + " " + raw[i]).strip()
        result.append(merged if len(merged) <= chunk_size + overlap else raw[i])

    return [c for c in result if c.strip()]


# ─── Classificação por pasta ─────────────────────────────────────────────────

def classify_document(rel_path: str) -> Tuple[str, str]:
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
        logger.debug(f"Falha ao extrair {file_path.name}: {exc}")
        return ""


def extract_and_chunk(meta: Dict[str, Any], chunk_size: int, chunk_overlap: int) -> Optional[Dict[str, Any]]:
    """Extrai texto e divide em chunks (roda em thread)."""
    file_path: Path = meta["file_path"]
    text = extract_text(file_path)
    if not text or len(text.strip()) < 30:
        return None

    chunks = chunk_text(text, chunk_size, chunk_overlap)
    if not chunks:
        return None

    return {"meta": meta, "chunks": chunks}


# ─── Embeddings ───────────────────────────────────────────────────────────────

def embed_batch_dense(texts: List[str], client: OpenAI, max_retries: int = 3) -> List[Optional[List[float]]]:
    """Gera embeddings densos em lote (até 2048 por chamada OpenAI)."""
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


def embed_batch_sparse(texts: List[str]) -> List[Optional[Any]]:
    """Gera vetores BM25 em lote via fastembed."""
    from qdrant_utils import get_bm25_model, SparseVector

    model = get_bm25_model()
    if model is None:
        return [None] * len(texts)

    try:
        results = []
        for emb in model.embed(texts):
            results.append(SparseVector(
                indices=emb.indices.tolist(),
                values=emb.values.tolist(),
            ))
        return results
    except Exception as exc:
        logger.error(f"Sparse batch falhou: {exc}")
        return [None] * len(texts)


# ─── Verificar existentes ────────────────────────────────────────────────────

def get_indexed_document_ids(qdrant_client, collection_name: str) -> set:
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


# ─── Iterator de documentos ─────────────────────────────────────────────────

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


def count_documents(folder: Path) -> int:
    """Conta rapidamente quantos arquivos serão processados."""
    count = 0
    for file_path in folder.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in {".pdf", ".docx", ".txt", ".md"} and not file_path.name.startswith("."):
            count += 1
    return count


# ─── Pipeline principal ─────────────────────────────────────────────────────

def index_folder(
    folder: str = DEFAULT_FOLDER,
    recreate: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    embed_batch: int = DEFAULT_EMBED_BATCH,
    upsert_batch: int = DEFAULT_UPSERT_BATCH,
    skip_existing: bool = False,
    dry_run: bool = False,
    workers: int = DEFAULT_WORKERS,
) -> Dict[str, int]:
    from qdrant_utils import get_qdrant_client, ensure_collection, upsert_points

    stats = {"files_processed": 0, "files_failed": 0, "chunks_indexed": 0, "chunks_failed": 0}

    folder_path = Path(folder)
    if not folder_path.is_dir():
        logger.error(f"Pasta não encontrada: {folder}")
        return stats

    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY não configurada.")
        return stats

    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    # Contar total de arquivos
    total_files = count_documents(folder_path)
    logger.info(f"Total de arquivos encontrados: {total_files}")
    logger.info(f"Modelo de embedding: {OPENAI_EMBEDDING_MODEL} ({EMBEDDING_DIM}d)")
    logger.info(f"Batch size: {embed_batch} chunks | Workers: {workers}")

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

    skip_ids: set = set()
    if skip_existing:
        skip_ids = get_indexed_document_ids(qdrant, QDRANT_COLLECTION)
        logger.info(f"Documentos já indexados: {len(skip_ids)}")

    # ── Coletar todos os documentos e extrair texto em paralelo ──────────────
    docs_meta = list(iter_documents(folder_path, skip_ids=skip_ids if skip_existing else None))
    logger.info(f"Documentos a processar: {len(docs_meta)}")

    # Acumular todos os chunks primeiro (extração paralela)
    all_chunks: List[Dict[str, Any]] = []  # cada item: {meta fields + content}
    t0 = time.time()
    processed = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(extract_and_chunk, meta, chunk_size, chunk_overlap): meta
            for meta in docs_meta
        }
        for future in as_completed(futures):
            processed += 1
            result = future.result()
            if result is None:
                failed += 1
            else:
                meta = result["meta"]
                chunks = result["chunks"]
                for idx, content in enumerate(chunks):
                    chunk_id = f"{meta['document_id']}_{idx}"
                    all_chunks.append({
                        "document_id": meta["document_id"],
                        "arquivo_origem": meta["arquivo_origem"],
                        "path_relativo": meta["path_relativo"],
                        "tipo_documento": meta["tipo_documento"],
                        "area_direito": meta["area_direito"],
                        "language_code": meta["language_code"],
                        "chunk_id": chunk_id,
                        "chunk_index": idx,
                        "total_chunks": len(chunks),
                        "content": content,
                    })

            if processed % 500 == 0 or processed == len(docs_meta):
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (len(docs_meta) - processed) / rate if rate > 0 else 0
                logger.info(
                    f"[Extração] {processed}/{len(docs_meta)} docs "
                    f"({processed*100//len(docs_meta)}%) | "
                    f"{len(all_chunks)} chunks | "
                    f"{rate:.1f} docs/s | ETA: {eta/60:.0f}min"
                )

    stats["files_processed"] = processed - failed
    stats["files_failed"] = failed
    logger.info(f"Extração concluída: {len(all_chunks)} chunks de {stats['files_processed']} docs em {time.time()-t0:.0f}s")

    if not all_chunks:
        logger.warning("Nenhum chunk para indexar.")
        return stats

    # ── Embeddings + upsert em mega-batches ──────────────────────────────────
    total_chunks = len(all_chunks)
    t1 = time.time()

    for batch_start in range(0, total_chunks, embed_batch):
        batch_end = min(batch_start + embed_batch, total_chunks)
        batch = all_chunks[batch_start:batch_end]
        batch_texts = [c["content"] for c in batch]

        # Dense embeddings (OpenAI)
        dense_vectors = embed_batch_dense(batch_texts, openai_client)

        # Sparse BM25 embeddings (fastembed) — em lote
        sparse_vectors = embed_batch_sparse(batch_texts)

        # Montar pontos para upsert
        points = []
        for i, chunk_data in enumerate(batch):
            if dense_vectors[i] is None:
                stats["chunks_failed"] += 1
                continue

            chunk_data["content_vector"] = dense_vectors[i]
            chunk_data["sparse_vector"] = sparse_vectors[i] if sparse_vectors[i] else None
            points.append(chunk_data)

        # Upsert no Qdrant
        if points:
            ok, err = upsert_points(qdrant, points, QDRANT_COLLECTION, batch_size=upsert_batch)
            stats["chunks_indexed"] += ok
            stats["chunks_failed"] += err

        # Progresso
        done = min(batch_end, total_chunks)
        elapsed = time.time() - t1
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total_chunks - done) / rate if rate > 0 else 0
        logger.info(
            f"[Embedding+Upsert] {done}/{total_chunks} chunks "
            f"({done*100//total_chunks}%) | "
            f"{rate:.0f} chunks/s | ETA: {eta/60:.0f}min"
        )

    total_time = time.time() - t0
    logger.info(
        f"\n{'='*52}\n"
        f"Indexação concluída em {total_time/60:.1f} minutos:\n"
        f"  Arquivos processados : {stats['files_processed']}\n"
        f"  Arquivos com falha   : {stats['files_failed']}\n"
        f"  Chunks indexados     : {stats['chunks_indexed']}\n"
        f"  Chunks com falha     : {stats['chunks_failed']}\n"
        f"  Modelo embedding     : {OPENAI_EMBEDDING_MODEL} ({EMBEDDING_DIM}d)\n"
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
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Threads para extração de texto")
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
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
