"""
rag_utils.py
Pipeline RAG principal: busca híbrida + reranking + GraphRAG + geração LLM.

Sem dependências Streamlit. Usa logging padrão.
Integra:
  - hybrid_search.py  → BM25 + kNN + RRF
  - reranker.py       → cross-encoder / LLM reranking
  - graph_rag.py      → grafo de conhecimento jurídico com teoria dos grafos

LLM: Anthropic Claude
Embeddings: OpenAI (Anthropic não oferece API de embeddings)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import anthropic
from dotenv import load_dotenv
from openai import OpenAI
from opensearchpy import OpenSearch, RequestsHttpConnection

from hybrid_search import hybrid_search as _hybrid_search
from reranker import rerank as _rerank

load_dotenv()
logger = logging.getLogger(__name__)

# ─── Configuração ─────────────────────────────────────────────────────────────

# Anthropic — LLM (Claude)
ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
ANTHROPIC_MODEL = (os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()

# OpenAI — apenas embeddings (Anthropic não tem API de embeddings)
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_EMBEDDING_MODEL = (os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-large").strip()

OPENSEARCH_HOST = (os.getenv("OPENSEARCH_HOST") or "http://localhost:9200").strip()
OPENSEARCH_INDEX = (os.getenv("OPENSEARCH_INDEX") or "docs-index").strip()
OPENSEARCH_TEXT_FIELD = os.getenv("OPENSEARCH_TEXT_FIELD", "content").strip()
OPENSEARCH_VECTOR_FIELD = os.getenv("OPENSEARCH_VECTOR_FIELD", "content_vector").strip()

SERPER_API_KEY = (os.getenv("SERPER_API_KEY") or "").strip()
SERPER_ENDPOINT = (os.getenv("SERPER_ENDPOINT") or "https://google.serper.dev/search").strip()

RAG_FEEDBACK_PATH = (os.getenv("RAG_FEEDBACK_PATH") or "feedback_rag.jsonl").strip()
GRAPH_VIZ_DIR = (os.getenv("GRAPH_VIZ_DIR") or "graph_visualizations").strip()
os.makedirs(GRAPH_VIZ_DIR, exist_ok=True)

# ─── Clientes (singletons) ────────────────────────────────────────────────────

_anthropic_client: Optional[anthropic.Anthropic] = None
_openai_client: Optional[OpenAI] = None       # usado apenas para embeddings
_opensearch_client: Optional[OpenSearch] = None


def get_anthropic_client() -> Optional[anthropic.Anthropic]:
    """Cliente Anthropic para geração de texto (Claude)."""
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY não configurada no .env")
        return None
    try:
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        return _anthropic_client
    except Exception as exc:
        logger.error(f"Falha ao iniciar cliente Anthropic: {exc}")
        return None


def get_openai_client() -> Optional[OpenAI]:
    """Cliente OpenAI — usado SOMENTE para embeddings."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY não configurada no .env (necessária para embeddings)")
        return None
    try:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        return _openai_client
    except Exception as exc:
        logger.error(f"Falha ao iniciar cliente OpenAI (embeddings): {exc}")
        return None


def get_opensearch_client() -> Optional[OpenSearch]:
    global _opensearch_client
    if _opensearch_client is not None:
        return _opensearch_client
    try:
        client = OpenSearch(
            hosts=[OPENSEARCH_HOST],
            use_ssl=OPENSEARCH_HOST.startswith("https://"),
            verify_certs=False,
            connection_class=RequestsHttpConnection,
            timeout=60,
            max_retries=3,
            retry_on_timeout=True,
        )
        if not client.ping():
            logger.error(f"OpenSearch indisponível em {OPENSEARCH_HOST}")
            return None
        _opensearch_client = client
        return client
    except Exception as exc:
        logger.error(f"Falha ao conectar ao OpenSearch: {exc}")
        return None


# ─── Feedback ────────────────────────────────────────────────────────────────

def salvar_feedback_rag(
    pergunta: str,
    resposta: str,
    feedback: str,
    comentario: str = "",
) -> None:
    try:
        record = {
            "ts": time.time(),
            "pergunta": pergunta,
            "resposta": resposta,
            "feedback": feedback,
            "comentario": comentario,
        }
        with open(RAG_FEEDBACK_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ─── DOCX ─────────────────────────────────────────────────────────────────────

def gerar_docx(texto: str, nome_arquivo: str = "resposta.docx") -> str:
    from docx import Document

    if not nome_arquivo.lower().endswith(".docx"):
        nome_arquivo += ".docx"

    output_dir = os.getenv("DOCX_OUTPUT_DIR", ".").strip() or "."
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, nome_arquivo)

    doc = Document()
    for line in (texto or "").splitlines():
        doc.add_paragraph(line.rstrip() if line.strip() else "")
    doc.save(out_path)
    return out_path


# ─── Embeddings ───────────────────────────────────────────────────────────────

def get_embedding(text: str, client_openai: OpenAI) -> Optional[List[float]]:
    if not text or not text.strip():
        return None
    try:
        cleaned = " ".join(text.replace("\n", " ").split())
        res = client_openai.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=[cleaned],
        )
        return res.data[0].embedding
    except Exception as exc:
        logger.error(f"Erro ao gerar embedding: {exc}")
        return None


def get_embeddings_batch(
    texts: List[str],
    client_openai: OpenAI,
    batch_size: int = 20,
) -> List[Optional[List[float]]]:
    """Gera embeddings em lote para múltiplos textos."""
    results: List[Optional[List[float]]] = [None] * len(texts)
    cleaned = [" ".join(t.replace("\n", " ").split()) for t in texts]

    for start in range(0, len(cleaned), batch_size):
        batch = cleaned[start: start + batch_size]
        try:
            res = client_openai.embeddings.create(
                model=OPENAI_EMBEDDING_MODEL,
                input=batch,
            )
            for i, item in enumerate(res.data):
                results[start + i] = item.embedding
        except Exception as exc:
            logger.error(f"Erro em lote de embeddings [{start}:{start+batch_size}]: {exc}")

    return results


# ─── Recuperação de contexto ──────────────────────────────────────────────────

def retrieve_context(
    query_text: str,
    search_client: OpenSearch,
    client_openai: OpenAI,
    top_k: int = 10,
    bm25_candidates: int = 30,
    dense_candidates: int = 30,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Recupera contextos relevantes via busca híbrida (BM25 + kNN + RRF).

    Returns:
        (texts, details) onde texts é lista de strings e details é lista de dicts
        com metadados e scores (_rrf_score, _bm25_score, _dense_score).
    """
    vec = get_embedding(query_text, client_openai)
    if vec is None:
        logger.warning("Não foi possível gerar embedding. Usando apenas BM25.")
        from hybrid_search import bm25_search
        bm25_results = bm25_search(
            search_client, OPENSEARCH_INDEX, query_text,
            top_k=top_k, text_field=OPENSEARCH_TEXT_FIELD,
        )
        hits = [doc for doc, _ in bm25_results[:top_k]]
    else:
        hits = _hybrid_search(
            search_client,
            OPENSEARCH_INDEX,
            query_text,
            vec,
            top_k=top_k,
            text_field=OPENSEARCH_TEXT_FIELD,
            vector_field=OPENSEARCH_VECTOR_FIELD,
            bm25_candidates=bm25_candidates,
            dense_candidates=dense_candidates,
        )

    texts: List[str] = []
    details: List[Dict[str, Any]] = []
    for h in hits:
        content = (h.get(OPENSEARCH_TEXT_FIELD) or "").strip()
        if content:
            texts.append(content)
            details.append(h)

    return texts, details


# ─── Web search (Serper) ──────────────────────────────────────────────────────

def serper_search(query: str, num_results: int = 3) -> List[Dict[str, str]]:
    if not SERPER_API_KEY:
        return []
    try:
        import requests
        payload = {"q": query, "num": max(1, min(10, int(num_results)))}
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        r = requests.post(SERPER_ENDPOINT, headers=headers, json=payload, timeout=25)
        r.raise_for_status()
        organic = r.json().get("organic", [])
        return [
            {
                "title": (it.get("title") or "").strip(),
                "snippet": (it.get("snippet") or "").strip(),
                "link": (it.get("link") or "").strip(),
            }
            for it in organic[: payload["num"]]
        ]
    except Exception as exc:
        logger.error(f"Serper search failed: {exc}")
        return []


def format_web_results(results: List[Dict[str, str]]) -> str:
    if not results:
        return ""
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(
            f"[Fonte web {i}] {r.get('title', '')}\n"
            f"{r.get('snippet', '')}\n"
            f"{r.get('link', '')}\n"
        )
    return "\n".join(parts).strip()


# ─── GraphRAG ────────────────────────────────────────────────────────────────

def _looks_complex_query(q: str) -> bool:
    keywords = [
        "requisitos", "elementos", "cabimento", "competência", "prazo",
        "nulidade", "abusividade", "tese", "fundamentação", "ônus",
        "nexo", "responsabilidade", "prescrição", "decadência",
        "prova", "tutela", "liminar", "jurisprudência", "precedente",
        "contrato", "cláusula", "rescisão", "indenização", "dano", "multa",
    ]
    qn = (q or "").lower()
    return any(k in qn for k in keywords) or len(qn.split()) >= 14


def should_use_graph_rag(
    user_query: str,
    num_contexts: int,
    force: bool = False,
) -> bool:
    if force:
        return num_contexts >= 2
    if num_contexts < 2:
        return False
    return _looks_complex_query(user_query) or num_contexts >= 8


def _make_graph_filename(user_query: str) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    h = hashlib.md5((user_query or "").encode()).hexdigest()[:10]
    return f"graph_{ts}_{h}.html"


def build_graphrag_summary(
    retrieved_details: List[Dict[str, Any]],
    user_query: str,
    save_html: bool = True,
) -> Tuple[str, str]:
    """
    Constrói grafo de conhecimento e retorna (summary_text, html_path).
    Aplica PageRank, betweenness e detecção de comunidades.
    """
    from graph_rag import GraphRAG

    docs_for_graph = []
    for d in retrieved_details or []:
        content = (d.get(OPENSEARCH_TEXT_FIELD) or d.get("content") or "").strip()
        if not content:
            continue
        docs_for_graph.append({
            "chunk_id": d.get("chunk_id") or d.get("id") or "",
            "content": content,
            "arquivo_origem": d.get("arquivo_origem") or "",
            "tipo_documento": d.get("tipo_documento") or "",
        })

    if len(docs_for_graph) < 2:
        return "", ""

    try:
        gr = GraphRAG(retrieved_documents=docs_for_graph, user_query=user_query)
        gr.process()  # PageRank + betweenness + comunidades

        summary = (gr.generate_textual_summary_for_llm() or "").strip()
        if not summary:
            return "", ""

        html_path = ""
        if save_html:
            filename = _make_graph_filename(user_query)
            html_path = os.path.join(GRAPH_VIZ_DIR, filename)
            gr.visualize_graph(output_filename=html_path)

        return summary, html_path
    except Exception as exc:
        logger.error(f"GraphRAG falhou: {exc}")
        return "", ""


# ─── LLM helpers (Anthropic Claude) ──────────────────────────────────────────

def _build_anthropic_messages(
    chat_history: Optional[List[Dict[str, str]]],
    user_instruction: str,
) -> List[Dict[str, str]]:
    """
    Monta a lista de mensagens para a API Anthropic.
    Nota: a Anthropic não aceita role='system' na lista — o system prompt
    é passado como parâmetro separado em _call_llm.
    A lista deve começar sempre com role='user'.
    """
    msgs: List[Dict[str, str]] = []
    for m in chat_history or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_instruction})
    return msgs


def _call_llm(
    client_anthropic: anthropic.Anthropic,
    system_message: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """
    Chama o Claude via Anthropic API.
    Na API Anthropic:
      - system prompt é parâmetro separado (não dentro de messages)
      - max_tokens é obrigatório
      - messages deve começar com role='user'
    """
    try:
        kwargs: Dict[str, Any] = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": int(max_tokens) if max_tokens else 4096,
            "temperature": float(temperature),
            "messages": messages,
        }
        if system_message:
            kwargs["system"] = system_message

        resp = client_anthropic.messages.create(**kwargs)
        return (resp.content[0].text or "").strip()
    except Exception as exc:
        logger.error(f"Erro ao chamar Claude ({ANTHROPIC_MODEL}): {exc}")
        return ""


# ─── API principal ────────────────────────────────────────────────────────────

def generate_response_with_rag_and_web_fallback(
    user_query: str,
    system_message_base: str = "",
    chat_history: Optional[List[Dict[str, str]]] = None,
    search_client: Optional[OpenSearch] = None,
    client_openai: Optional[OpenAI] = None,          # embeddings
    client_anthropic: Optional[anthropic.Anthropic] = None,  # LLM
    # Busca
    top_k: int = 10,
    bm25_candidates: int = 30,
    dense_candidates: int = 30,
    # Web fallback
    use_web_fallback: bool = True,
    min_contexts_for_web_fallback: int = 1,
    num_web_results: int = 3,
    # LLM params
    temperature: float = 0.2,
    max_tokens: int = 4096,
    # Reranking
    use_rerank: bool = True,
    top_k_rerank: int = 7,
    use_cross_encoder: bool = True,
    # GraphRAG
    use_graph_rag: str = "auto",   # "auto" | "on" | "off"
    max_details_for_graph: int = 12,
    save_graph_html: bool = True,
) -> Tuple[str, List[str], List[Dict[str, Any]], List[Dict[str, str]], str, str]:
    """
    Pipeline RAG completo com Claude (Anthropic) como LLM.

    Fluxo:
      1. Recuperação híbrida (BM25 + kNN + RRF) — embeddings via OpenAI
      2. Reranking (cross-encoder ou Claude)
      3. GraphRAG (PageRank + betweenness + comunidades)
      4. Web fallback via Serper (se contextos insuficientes)
      5. Geração de resposta com Claude

    Returns:
        (answer, contexts, details, web_results, graph_summary, graph_html_path)
    """
    # Inicializa clientes se não fornecidos
    if client_openai is None:
        client_openai = get_openai_client()
    if client_anthropic is None:
        client_anthropic = get_anthropic_client()
    if search_client is None:
        search_client = get_opensearch_client()

    if not client_openai or not search_client:
        return "Erro: serviços de embedding/busca não inicializados.", [], [], [], "", ""
    if not client_anthropic:
        return "Erro: cliente Anthropic (Claude) não inicializado.", [], [], [], "", ""

    # 1. Busca híbrida (usa OpenAI só para embeddings)
    contexts, details = retrieve_context(
        user_query, search_client, client_openai,
        top_k=int(top_k),
        bm25_candidates=int(bm25_candidates),
        dense_candidates=int(dense_candidates),
    )

    # 2. Reranking (cross-encoder local ou Claude como fallback)
    if use_rerank and details:
        try:
            reranked = _rerank(
                query=user_query,
                chunks=details,
                top_k=int(top_k_rerank),
                anthropic_client=client_anthropic,
                use_cross_encoder=bool(use_cross_encoder),
                content_field=OPENSEARCH_TEXT_FIELD,
            )
            details = reranked
            contexts = [
                (h.get(OPENSEARCH_TEXT_FIELD) or "").strip()
                for h in details
                if (h.get(OPENSEARCH_TEXT_FIELD) or "").strip()
            ]
        except Exception as exc:
            logger.error(f"Reranking falhou: {exc}")

    # 3. GraphRAG
    graph_summary = ""
    graph_html_path = ""

    use_gr = (use_graph_rag or "auto").strip().lower()
    if use_gr == "on":
        gr_should = len(details) >= 2
    elif use_gr == "off":
        gr_should = False
    else:
        gr_should = should_use_graph_rag(user_query, len(contexts))

    if gr_should and details:
        try:
            details_for_graph = details[: max(2, min(int(max_details_for_graph), len(details)))]
            graph_summary, graph_html_path = build_graphrag_summary(
                details_for_graph,
                user_query=user_query,
                save_html=bool(save_graph_html),
            )
        except Exception as exc:
            logger.error(f"GraphRAG build falhou: {exc}")

    # 4. Web fallback
    web_results: List[Dict[str, str]] = []
    web_block = ""
    if use_web_fallback and len(contexts) < int(min_contexts_for_web_fallback):
        web_results = serper_search(user_query, num_results=int(num_web_results))
        web_block = format_web_results(web_results)

    # 5. Prompt final → Claude
    ctx_block = "\n\n".join([f"- {c}" for c in contexts]) if contexts else ""
    final_user = f"{user_query}\n\nContexto recuperado (use se for relevante):\n{ctx_block}"

    if graph_summary:
        final_user += (
            "\n\nMAPA ESTRUTURADO (GraphRAG — teoria dos grafos relacionais):\n"
            f"{graph_summary}"
        )

    if web_block:
        final_user += (
            "\n\nContexto adicional da web (Serper — use com cautela):\n"
            f"{web_block}"
        )

    messages = _build_anthropic_messages(chat_history, final_user)
    answer = _call_llm(
        client_anthropic,
        system_message=system_message_base,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return answer, contexts, details, web_results, graph_summary, graph_html_path


def generate_consultor_response_with_rag(
    system_message_base: str,
    user_instruction: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    top_k: int = 12,
    use_web_fallback: bool = True,
    use_rerank: bool = True,
    use_cross_encoder: bool = True,
    use_graph_rag: str = "auto",
    save_graph_html: bool = True,
) -> str:
    """Wrapper simplificado — retorna apenas a resposta."""
    answer, *_ = generate_response_with_rag_and_web_fallback(
        user_query=user_instruction,
        system_message_base=system_message_base,
        chat_history=chat_history,
        top_k=top_k,
        use_web_fallback=use_web_fallback,
        use_rerank=use_rerank,
        use_cross_encoder=use_cross_encoder,
        use_graph_rag=use_graph_rag,
        save_graph_html=save_graph_html,
    )
    return answer
