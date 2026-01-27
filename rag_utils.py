# rag_utils.py
# OpenAI (LLM + embeddings) + OpenSearch (híbrido) + Web fallback (Serper)
# + LLM Rerank opcional + GraphRAG (auto por app) + SALVA HTML do grafo
# SEM qualquer referência a Azure

from __future__ import annotations

import os
import re
import json
import time
import math
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from opensearchpy import OpenSearch, RequestsHttpConnection

load_dotenv()

# =========================
# Config (.env)
# =========================
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_LLM_MODEL = (os.getenv("OPENAI_LLM_MODEL") or "gpt-5.2").strip()
OPENAI_EMBEDDING_MODEL = (os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-large").strip()

OPENSEARCH_HOST = (os.getenv("OPENSEARCH_HOST") or "http://localhost:9200").strip()
OPENSEARCH_INDEX = (os.getenv("OPENSEARCH_INDEX") or "docs-index").strip()
OPENSEARCH_TEXT_FIELD = os.getenv("OPENSEARCH_TEXT_FIELD", "content").strip()
OPENSEARCH_VECTOR_FIELD = os.getenv("OPENSEARCH_VECTOR_FIELD", "content_vector").strip()

# Serper
SERPER_API_KEY = (os.getenv("SERPER_API_KEY") or "").strip()
SERPER_ENDPOINT = (os.getenv("SERPER_ENDPOINT") or "https://google.serper.dev/search").strip()

# Feedback
RAG_FEEDBACK_PATH = (os.getenv("RAG_FEEDBACK_PATH") or "feedback_rag.jsonl").strip()

# Graph visualizations (HTML)
GRAPH_VIZ_DIR = (os.getenv("GRAPH_VIZ_DIR") or "graph_visualizations").strip()
os.makedirs(GRAPH_VIZ_DIR, exist_ok=True)


# =========================
# Clients
# =========================
@st.cache_resource
def get_openai_client() -> Optional[OpenAI]:
    if not OPENAI_API_KEY:
        st.error("OPENAI_API_KEY não definida no .env")
        return None
    try:
        return OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        st.error(f"Falha ao iniciar OpenAI client: {e}")
        return None


@st.cache_resource
def get_opensearch_client() -> Optional[OpenSearch]:
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
            st.error(f"OpenSearch indisponível em {OPENSEARCH_HOST}. Teste: curl {OPENSEARCH_HOST}")
            return None
        return client
    except Exception as e:
        st.error(f"Falha ao conectar no OpenSearch: {e}")
        return None


# =========================
# Feedback
# =========================
def salvar_feedback_rag(pergunta: str, resposta: str, feedback: str, comentario: str = "") -> None:
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


# =========================
# DOCX
# =========================
def gerar_docx(texto: str, nome_arquivo: str = "resposta.docx") -> str:
    try:
        from docx import Document
    except Exception as e:
        raise ImportError("python-docx não instalado. Rode: pip install python-docx") from e

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


# =========================
# Embeddings
# =========================
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
    except Exception as e:
        st.error(f"Erro ao gerar embedding: {e}")
        return None


# =========================
# OpenSearch (híbrida)
# =========================
def _opensearch_hybrid_search(
    os_client: OpenSearch,
    query_text: str,
    query_vector: List[float],
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    body = {
        "size": int(top_k),
        "_source": [
            "chunk_id",
            "document_id",
            "arquivo_origem",
            "tipo_documento",
            "language_code",
            OPENSEARCH_TEXT_FIELD,
        ],
        "query": {
            "bool": {
                "should": [
                    {"match": {OPENSEARCH_TEXT_FIELD: {"query": query_text, "operator": "and"}}},
                ],
                "minimum_should_match": 0,
            }
        },
        "knn": {
            "field": OPENSEARCH_VECTOR_FIELD,
            "query_vector": query_vector,
            "k": int(top_k),
            "num_candidates": max(50, int(top_k) * 10),
        },
    }

    try:
        res = os_client.search(index=OPENSEARCH_INDEX, body=body)
        hits = res.get("hits", {}).get("hits", []) or []
        out: List[Dict[str, Any]] = []
        for h in hits:
            src = h.get("_source", {}) or {}
            src["_score"] = h.get("_score", 0.0)
            out.append(src)
        return out
    except Exception:
        # Fallback: kNN-only (varia por versão)
        try:
            body_vec = {
                "size": int(top_k),
                "_source": [
                    "chunk_id",
                    "document_id",
                    "arquivo_origem",
                    "tipo_documento",
                    "language_code",
                    OPENSEARCH_TEXT_FIELD,
                ],
                "query": {
                    "knn": {
                        OPENSEARCH_VECTOR_FIELD: {
                            "vector": query_vector,
                            "k": int(top_k),
                        }
                    }
                },
            }
            res = os_client.search(index=OPENSEARCH_INDEX, body=body_vec)
            hits = res.get("hits", {}).get("hits", []) or []
            out: List[Dict[str, Any]] = []
            for h in hits:
                src = h.get("_source", {}) or {}
                src["_score"] = h.get("_score", 0.0)
                out.append(src)
            return out
        except Exception:
            return []


def retrieve_context(
    query_text: str,
    search_client: OpenSearch,
    client_openai: OpenAI,
    top_k: int = 8,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    vec = get_embedding(query_text, client_openai)
    if vec is None:
        return [], []

    hits = _opensearch_hybrid_search(search_client, query_text=query_text, query_vector=vec, top_k=top_k)
    contexts: List[str] = []
    details: List[Dict[str, Any]] = []

    for h in hits:
        content = (h.get(OPENSEARCH_TEXT_FIELD) or "").strip()
        if not content:
            continue
        contexts.append(content)
        details.append(h)

    return contexts, details


# =========================
# Serper (Web Search)
# =========================
def serper_search(query: str, num_results: int = 3) -> List[Dict[str, str]]:
    if not SERPER_API_KEY:
        return []

    try:
        import requests
    except Exception:
        st.warning("Para usar Serper, instale: pip install requests")
        return []

    try:
        payload = {"q": query, "num": max(1, min(10, int(num_results)))}
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        r = requests.post(SERPER_ENDPOINT, headers=headers, json=payload, timeout=25)
        r.raise_for_status()
        data = r.json() or {}
        organic = data.get("organic", []) or []

        out: List[Dict[str, str]] = []
        for it in organic[: payload["num"]]:
            out.append(
                {
                    "title": (it.get("title") or "").strip(),
                    "snippet": (it.get("snippet") or "").strip(),
                    "link": (it.get("link") or "").strip(),
                }
            )
        return out
    except Exception:
        return []


def format_web_results(results: List[Dict[str, str]]) -> str:
    if not results:
        return ""
    parts = []
    for i, r in enumerate(results, 1):
        title = (r.get("title") or "").strip()
        snippet = (r.get("snippet") or "").strip()
        link = (r.get("link") or "").strip()
        parts.append(f"[Fonte web {i}] {title}\n{snippet}\n{link}\n")
    return "\n".join(parts).strip()


# =========================
# URL context (usado em app4/app5)
# =========================
def processar_urls_contexto(urls: List[str], pergunta: str = "", top_k_chunks: int = 2) -> str:
    urls = [u for u in (urls or []) if (u or "").strip()]
    if not urls:
        return ""

    try:
        from chroma_utils import obter_contexto_relevante_de_url
    except Exception:
        return ""

    blocos: List[str] = []
    for i, url in enumerate(urls, start=1):
        try:
            ctx = obter_contexto_relevante_de_url(url, pergunta or "", top_k_chunks=top_k_chunks) or ""
            if not ctx.strip():
                continue
            blocos.append(f"--- Contexto da URL {i} ({url}) ---\n{ctx}\n--- Fim do Contexto da URL {i} ---\n")
        except Exception:
            continue

    if not blocos:
        return ""
    return "CONTEXTOS EXTRAÍDOS DE URLs (use se forem relevantes):\n\n" + "\n".join(blocos)


# =========================
# LLM helpers
# =========================
def _build_messages(
    system_message_base: str,
    chat_history: Optional[List[Dict[str, str]]],
    user_instruction: str,
) -> List[Dict[str, str]]:
    msgs: List[Dict[str, str]] = []
    if system_message_base:
        msgs.append({"role": "system", "content": system_message_base})

    for m in chat_history or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role in ("system", "user", "assistant") and content:
            msgs.append({"role": role, "content": content})

    msgs.append({"role": "user", "content": user_instruction})
    return msgs


def _call_llm(
    client_openai: OpenAI,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    try:
        kwargs: Dict[str, Any] = {
            "model": OPENAI_LLM_MODEL,
            "messages": messages,
            "temperature": float(temperature),
        }

        # GPT-5.x usa max_completion_tokens
        if max_tokens is not None:
            if OPENAI_LLM_MODEL.startswith("gpt-5"):
                kwargs["max_completion_tokens"] = int(max_tokens)
            else:
                kwargs["max_tokens"] = int(max_tokens)

        resp = client_openai.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()

    except Exception as e:
        st.error(f"Erro ao chamar LLM ({OPENAI_LLM_MODEL}): {e}")
        return ""


# =========================
# LLM Rerank
# =========================
def _safe_json_loads(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        return None


def _truncate(text: str, max_chars: int) -> str:
    if not text:
        return ""
    t = str(text)
    return t[:max_chars] + ("…" if len(t) > max_chars else "")


def llm_rerank_chunks(
    client_openai: OpenAI,
    query: str,
    chunks: List[Dict[str, Any]],
    top_k: int = 7,
    rerank_pool_size: int = 15,
    max_chars_per_chunk: int = 1200,
) -> List[Dict[str, Any]]:
    if not chunks or len(chunks) <= 1:
        return chunks

    pool = chunks[: max(1, min(int(rerank_pool_size), len(chunks)))]

    cards: List[Dict[str, Any]] = []
    for i, ch in enumerate(pool, start=1):
        content = ch.get(OPENSEARCH_TEXT_FIELD) or ch.get("content") or ch.get("text") or ""
        source = ch.get("arquivo_origem") or ch.get("source") or ch.get("url") or ch.get("path") or ""
        score = ch.get("_score") or ch.get("score")
        cards.append(
            {
                "id": i,
                "source": str(source)[:120],
                "score": float(score) if isinstance(score, (int, float)) and not math.isnan(score) else None,
                "content": _truncate(content, int(max_chars_per_chunk)),
            }
        )

    system = (
        "Você é um reranker de trechos para RAG jurídico. "
        "Sua tarefa é ordenar os trechos pelo quanto ajudam a responder a pergunta. "
        "Não invente fatos. Não explique: apenas devolva JSON."
    )

    user_payload = {
        "query": query,
        "instructions": (
            "Ordene os trechos mais relevantes para responder a query. "
            "Critérios: (1) pertinência direta, (2) detalhes concretos úteis, "
            "(3) clareza, (4) evitar redundância. "
            "Responda SOMENTE com JSON no formato: "
            '{"ranked_ids":[1,5,2], "notes":"opcional"} '
            "Use apenas ids existentes. Retorne no máximo "
            f"{min(int(top_k), len(cards))} ids."
        ),
        "chunks": cards,
    }

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]

    raw = _call_llm(client_openai, messages, temperature=0.0, max_tokens=800)
    data = _safe_json_loads(raw)

    if not isinstance(data, dict) or "ranked_ids" not in data:
        return chunks

    ranked_ids = data.get("ranked_ids")
    if not isinstance(ranked_ids, list) or not ranked_ids:
        return chunks

    ranked_ids_clean: List[int] = []
    for x in ranked_ids:
        try:
            xi = int(x)
            if 1 <= xi <= len(pool) and xi not in ranked_ids_clean:
                ranked_ids_clean.append(xi)
        except Exception:
            continue

    if not ranked_ids_clean:
        return chunks

    id_to_chunk = {i + 1: pool[i] for i in range(len(pool))}
    reranked_pool = [id_to_chunk[i] for i in ranked_ids_clean if i in id_to_chunk]
    remaining_pool = [ch for idx, ch in enumerate(pool, start=1) if idx not in ranked_ids_clean]
    tail = chunks[len(pool) :]

    return reranked_pool + remaining_pool + tail


# =========================
# GraphRAG (integração + heurística + salvar HTML)
# =========================
def _looks_complex_query(q: str) -> bool:
    qn = (q or "").lower()
    keywords = [
        "requisitos", "elementos", "cabimento", "competência", "prazo",
        "nulidade", "abusividade", "tese", "fundamentação", "ônus",
        "nexo", "responsabilidade", "prescrição", "decadência",
        "prova", "tutela", "liminar", "jurisprudência", "precedente",
        "contrato", "cláusula", "clausula", "rescisão", "rescisao",
        "indenização", "indenizacao", "dano", "multa",
    ]
    return any(k in qn for k in keywords) or len(qn.split()) >= 14


def should_use_graph_rag(app_hint: str, user_query: str, num_contexts: int) -> bool:
    app = (app_hint or "").strip().lower()

    if num_contexts < 2:
        return False

    if app in ("app2", "app3", "app5"):
        return True

    if app in ("app4", "", "consultor"):
        if num_contexts >= 8:
            return True
        if _looks_complex_query(user_query):
            return True
        return False

    if num_contexts >= 8:
        return True
    return _looks_complex_query(user_query)


def _make_graph_filename(user_query: str) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    h = hashlib.md5((user_query or "").encode("utf-8")).hexdigest()[:10]
    return f"graph_{ts}_{h}.html"


def build_graphrag_summary(
    retrieved_details: List[Dict[str, Any]],
    user_query: str,
    save_html: bool = True,
) -> Tuple[str, str]:
    """
    Retorna: (graph_summary, graph_html_path)
    - graph_summary: texto estrutural para o LLM
    - graph_html_path: caminho do HTML salvo (PyVis) ou "" se não gerou
    """
    try:
        from graph_rag import GraphRAG
    except Exception:
        return "", ""

    docs_for_graph: List[Dict[str, Any]] = []
    for d in retrieved_details or []:
        content = (d.get(OPENSEARCH_TEXT_FIELD) or d.get("content") or "").strip()
        if not content:
            continue
        docs_for_graph.append(
            {
                "chunk_id": d.get("chunk_id") or d.get("id") or "",
                "content": content,
                "arquivo_origem": d.get("arquivo_origem") or "",
                "tipo_documento": d.get("tipo_documento") or "",
            }
        )

    if len(docs_for_graph) < 2:
        return "", ""

    try:
        gr = GraphRAG(retrieved_documents=docs_for_graph, user_query=user_query)
        gr.process()

        summary = (gr.generate_textual_summary_for_llm() or "").strip()
        if not summary or "No significant structural relationships" in summary:
            summary = ""

        html_path = ""
        if save_html:
            filename = _make_graph_filename(user_query)
            html_path = os.path.join(GRAPH_VIZ_DIR, filename)
            # salva HTML
            gr.visualize_graph(output_filename=html_path)

        return summary, html_path
    except Exception:
        return "", ""


# =========================
# API principal: RAG + Serper fallback + rerank + GraphRAG auto + HTML path
# =========================
def generate_response_with_rag_and_web_fallback(
    user_query: str,
    system_message_base: str = "",
    chat_history: Optional[List[Dict[str, str]]] = None,
    search_client: Optional[OpenSearch] = None,
    client_openai: Optional[OpenAI] = None,
    top_k: int = 8,
    # Web fallback
    use_web_fallback: bool = True,
    min_contexts_for_web_fallback: int = 1,
    num_web_results: int = 3,
    # LLM params
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    # Rerank params
    use_llm_rerank: bool = False,
    top_k_rerank: int = 7,
    rerank_pool_size: int = 15,
    max_chars_per_chunk: int = 1200,
    # GraphRAG params
    app_hint: str = "app4",
    use_graph_rag: str = "auto",  # "auto" | "on" | "off"
    max_details_for_graphrag: int = 12,
    save_graph_html: bool = True,
) -> Tuple[str, List[str], List[Dict[str, Any]], List[Dict[str, str]], str, str]:
    """
    Retorna:
      (answer, contexts, context_details, web_results, graph_summary, graph_html_path)
    """
    if client_openai is None:
        client_openai = get_openai_client()
    if search_client is None:
        search_client = get_opensearch_client()

    if not client_openai or not search_client:
        return "Erro: serviços de IA não inicializados.", [], [], [], "", ""

    # 1) Recupera contexto
    contexts, details = retrieve_context(user_query, search_client, client_openai, top_k=int(top_k))

    # 2) Rerank opcional
    if use_llm_rerank and details:
        try:
            reranked_details = llm_rerank_chunks(
                client_openai=client_openai,
                query=user_query,
                chunks=details,
                top_k=int(top_k_rerank),
                rerank_pool_size=int(rerank_pool_size),
                max_chars_per_chunk=int(max_chars_per_chunk),
            )
            reranked_details = reranked_details[: int(top_k)]
            details = reranked_details

            new_contexts: List[str] = []
            for h in details:
                content = (h.get(OPENSEARCH_TEXT_FIELD) or "").strip()
                if content:
                    new_contexts.append(content)
            contexts = new_contexts
        except Exception:
            pass

    # 3) GraphRAG (auto por app) + salva HTML
    graph_summary = ""
    graph_html_path = ""

    use_gr = (use_graph_rag or "auto").strip().lower()
    if use_gr == "on":
        gr_should = True
    elif use_gr == "off":
        gr_should = False
    else:
        gr_should = should_use_graph_rag(app_hint=app_hint, user_query=user_query, num_contexts=len(contexts))

    if gr_should and details:
        try:
            details_for_graph = details[: max(2, min(int(max_details_for_graphrag), len(details)))]
            graph_summary, graph_html_path = build_graphrag_summary(
                details_for_graph,
                user_query=user_query,
                save_html=bool(save_graph_html),
            )
        except Exception:
            graph_summary, graph_html_path = "", ""

    # 4) Web fallback
    web_results: List[Dict[str, str]] = []
    web_block = ""
    if use_web_fallback and len(contexts) < int(min_contexts_for_web_fallback):
        web_results = serper_search(user_query, num_results=int(num_web_results))
        web_block = format_web_results(web_results)

    # 5) Prompt final
    ctx_block = "\n\n".join([f"- {c}" for c in contexts]) if contexts else ""
    final_user = f"{user_query}\n\nContexto recuperado (use se for relevante):\n{ctx_block}"

    if graph_summary:
        final_user += (
            "\n\nMAPA ESTRUTURADO (GraphRAG) — use para organizar raciocínio e evitar redundância:\n"
            f"{graph_summary}"
        )

    if web_block:
        final_user += (
            "\n\nContexto adicional da web (Serper). Use com cautela e identifique como 'Fonte web':\n"
            f"{web_block}"
        )

    messages = _build_messages(system_message_base, chat_history, final_user)
    answer = _call_llm(client_openai, messages, temperature=temperature, max_tokens=max_tokens)

    return answer, contexts, details, web_results, graph_summary, graph_html_path


# Conveniência: compatível com apps simples (retorna só resposta)
def generate_consultor_response_with_rag(
    system_message_base: str,
    user_instruction: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    top_k: int = 15,
    use_web_fallback: bool = True,
    min_contexts_for_web_fallback: int = 1,
    num_web_results: int = 2,
    # rerank (opcional)
    use_llm_rerank: bool = False,
    top_k_rerank: int = 7,
    # graph (auto)
    use_graph_rag: str = "auto",
    save_graph_html: bool = True,
) -> str:
    answer, _contexts, _details, _web, _graph, _graph_html = generate_response_with_rag_and_web_fallback(
        user_query=user_instruction,
        system_message_base=system_message_base,
        chat_history=chat_history,
        top_k=int(top_k),
        use_web_fallback=use_web_fallback,
        min_contexts_for_web_fallback=int(min_contexts_for_web_fallback),
        num_web_results=int(num_web_results),
        use_llm_rerank=use_llm_rerank,
        top_k_rerank=int(top_k_rerank),
        app_hint="app4",
        use_graph_rag=use_graph_rag,
        save_graph_html=save_graph_html,
    )
    return answer
