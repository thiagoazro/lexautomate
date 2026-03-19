"""
rag_utils.py
Pipeline RAG principal: busca híbrida + reranking + GraphRAG + geração LLM.

LLM:       Anthropic Claude
Embeddings: OpenAI (Anthropic não oferece API de embeddings)
Busca:     Qdrant Cloud (dense OpenAI + sparse BM25 + RRF nativo)
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
from qdrant_client import QdrantClient

from hybrid_search import hybrid_search as _hybrid_search
from reranker import rerank as _rerank

load_dotenv()
logger = logging.getLogger(__name__)

# ─── Configuração ─────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
ANTHROPIC_MODEL = (os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_EMBEDDING_MODEL = (os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small").strip()

QDRANT_URL = (os.getenv("QDRANT_URL") or "http://localhost:6333").strip()
QDRANT_API_KEY = (os.getenv("QDRANT_API_KEY") or "").strip()
QDRANT_COLLECTION = (os.getenv("QDRANT_COLLECTION") or "docs-index").strip()
CONTENT_FIELD = "content"

TAVILY_API_KEY = (os.getenv("TAVILY_API_KEY") or "").strip()

RAG_FEEDBACK_PATH = (os.getenv("RAG_FEEDBACK_PATH") or "feedback_rag.jsonl").strip()
GRAPH_VIZ_DIR = (os.getenv("GRAPH_VIZ_DIR") or "/tmp/graph_visualizations").strip()
os.makedirs(GRAPH_VIZ_DIR, exist_ok=True)


# ─── System Prompt Jurídico Especializado ────────────────────────────────────

SYSTEM_PROMPT_JURIDICO = """Você é um consultor jurídico especializado em legislação brasileira, com profundo conhecimento em todas as áreas do Direito nacional.

## REGRAS DE CITAÇÃO (OBRIGATÓRIAS)
1. CITE SEMPRE a fonte: "Art. XX da Lei nº XXXX/XXXX", "Súmula XXX do STJ", "REsp nº XXXX".
2. NUNCA invente números de artigos, súmulas, leis ou processos. Se não encontrou nos documentos recuperados, diga explicitamente "não localizei referência específica nos documentos disponíveis".
3. Diferencie claramente entre: legislação vigente, jurisprudência e doutrina.

## HIERARQUIA DE PRECEDENTES
- Constituição Federal > Leis Complementares > Leis Ordinárias > Decretos
- STF (Supremo) > STJ (Superior) > TST/TSE/STM > TRF/TJ (Regionais) > Varas
- Súmula Vinculante > Súmula Comum > Jurisprudência Pacífica > Decisão Isolada
- Sempre que possível, indique se a jurisprudência é pacífica ou se há divergência.

## CONTRADIÇÕES
Se encontrar interpretações conflitantes nos documentos:
- Apresente AMBAS as posições com suas respectivas fontes
- Indique qual é majoritária ou mais recente
- Cite os casos/artigos divergentes

## ESTRUTURA DA RESPOSTA
1. **Resumo executivo** (2-3 linhas com a resposta direta)
2. **Fundamentação jurídica** (artigos, súmulas, jurisprudência — sempre com citação)
3. **Análise e aplicação** (como se aplica ao caso concreto)
4. **Ressalvas e exceções** (quando houver)

## CONTEXTO RECUPERADO
Os trechos abaixo foram recuperados automaticamente da base de documentos jurídicos. Use-os como fonte primária, mas NÃO copie parágrafos inteiros — sintetize e cite.
Se o contexto for insuficiente para responder, diga claramente e ofereça orientação geral com a ressalva de que é baseada em conhecimento geral, não nos documentos da base.

## IDIOMA
Responda sempre em português brasileiro, com linguagem técnica jurídica adequada mas acessível."""


# ─── Clientes (singletons) ────────────────────────────────────────────────────

_anthropic_client: Optional[anthropic.Anthropic] = None
_openai_client: Optional[OpenAI] = None
_qdrant_client: Optional[QdrantClient] = None


def get_anthropic_client() -> Optional[anthropic.Anthropic]:
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
    """Apenas para embeddings — Anthropic não tem API de embeddings."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY não configurada (necessária para embeddings)")
        return None
    try:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        return _openai_client
    except Exception as exc:
        logger.error(f"Falha ao iniciar cliente OpenAI (embeddings): {exc}")
        return None


def get_qdrant_client() -> Optional[QdrantClient]:
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
    try:
        from qdrant_utils import get_qdrant_client as _get_client, ping
        client = _get_client()
        if not ping(client):
            logger.error(f"Qdrant indisponível em {QDRANT_URL}")
            return None
        _qdrant_client = client
        return client
    except Exception as exc:
        logger.error(f"Falha ao conectar ao Qdrant: {exc}")
        return None


# ─── Feedback ────────────────────────────────────────────────────────────────

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


# ─── DOCX ────────────────────────────────────────────────────────────────────

def gerar_docx(texto: str, nome_arquivo: str = "resposta.docx") -> str:
    from docx import Document

    if not nome_arquivo.lower().endswith(".docx"):
        nome_arquivo += ".docx"

    output_dir = os.getenv("DOCX_OUTPUT_DIR", "/tmp").strip() or "/tmp"
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
    results: List[Optional[List[float]]] = [None] * len(texts)
    cleaned = [" ".join(t.replace("\n", " ").split())[:8000] for t in texts]

    for start in range(0, len(cleaned), batch_size):
        batch = cleaned[start: start + batch_size]
        try:
            res = client_openai.embeddings.create(
                model=OPENAI_EMBEDDING_MODEL,
                input=batch,
            )
            for item in res.data:
                results[start + item.index] = item.embedding
        except Exception as exc:
            logger.error(f"Erro em lote de embeddings [{start}:{start+batch_size}]: {exc}")

    return results


# ─── Query Expansion (expansão de consulta jurídica) ─────────────────────────

# Mapeamento de termos jurídicos comuns para seus equivalentes legais
_QUERY_EXPANSIONS: Dict[str, List[str]] = {
    "rescisão indireta": ["art. 483 clt", "falta grave do empregador"],
    "justa causa": ["art. 482 clt", "falta grave do empregado"],
    "horas extras": ["art. 59 clt", "jornada extraordinária", "sobrejornada"],
    "dano moral": ["art. 186 código civil", "indenização por dano extrapatrimonial"],
    "estabilidade gestante": ["art. 10 adct", "estabilidade provisória gestante"],
    "acidente de trabalho": ["art. 19 lei 8213", "nexo causal", "responsabilidade do empregador"],
    "adicional de insalubridade": ["art. 189 clt", "nr-15", "agente insalubre"],
    "adicional de periculosidade": ["art. 193 clt", "nr-16", "atividade perigosa"],
    "aviso prévio": ["art. 487 clt", "aviso prévio proporcional"],
    "fgts": ["fundo de garantia", "lei 8036", "multa 40%"],
    "prescrição trabalhista": ["art. 7 xxix constituição", "prescrição quinquenal", "prescrição bienal"],
    "assédio moral": ["dano moral no trabalho", "ambiente de trabalho hostil"],
    "equiparação salarial": ["art. 461 clt", "trabalho de igual valor"],
    "terceirização": ["lei 13429", "responsabilidade subsidiária", "atividade-fim"],
    "contrato de experiência": ["art. 443 clt", "contrato por prazo determinado"],
    "férias": ["art. 129 clt", "período aquisitivo", "período concessivo"],
    "mandado de segurança": ["art. 5 lxix constituição", "lei 12016", "direito líquido e certo"],
    "habeas corpus": ["art. 5 lxviii constituição", "liberdade de locomoção"],
    "usucapião": ["art. 1238 código civil", "posse ad usucapionem", "prescrição aquisitiva"],
    "pensão alimentícia": ["art. 1694 código civil", "alimentos", "necessidade e possibilidade"],
    "guarda compartilhada": ["art. 1583 código civil", "lei 13058", "melhor interesse da criança"],
    "divórcio": ["art. 226 constituição", "dissolução do casamento", "partilha de bens"],
    "despejo": ["lei 8245", "lei do inquilinato", "retomada do imóvel"],
    "execução fiscal": ["lei 6830", "certidão de dívida ativa", "cda"],
    "improbidade administrativa": ["lei 8429", "enriquecimento ilícito", "dano ao erário"],
    "licitação": ["lei 14133", "pregão", "concorrência pública"],
    "consumidor": ["cdc", "lei 8078", "relação de consumo", "vício do produto"],
}


def expand_query(query: str) -> str:
    """
    Expande a query do usuário com termos jurídicos equivalentes.
    Ex: "rescisão indireta" → "rescisão indireta art. 483 clt falta grave do empregador"
    """
    query_lower = query.lower()
    expansions = []

    for term, equivalents in _QUERY_EXPANSIONS.items():
        if term in query_lower:
            for eq in equivalents:
                if eq.lower() not in query_lower:
                    expansions.append(eq)

    if expansions:
        expanded = f"{query} ({' '.join(expansions)})"
        logger.info(f"Query expandida: '{query}' → adicionados {len(expansions)} termos")
        return expanded

    return query


# ─── Deduplicação de contextos ───────────────────────────────────────────────

def _simple_hash(text: str) -> str:
    """Hash normalizado para comparação rápida."""
    normalized = " ".join(text.lower().split())
    return hashlib.md5(normalized[:500].encode()).hexdigest()


def deduplicate_contexts(
    details: List[Dict[str, Any]],
    similarity_threshold: float = 0.85,
) -> List[Dict[str, Any]]:
    """
    Remove contextos quase duplicados.
    Usa comparação de overlap de palavras (Jaccard similarity).
    """
    if len(details) <= 1:
        return details

    seen_hashes: set = set()
    seen_word_sets: List[set] = []
    unique: List[Dict[str, Any]] = []

    for d in details:
        content = (d.get(CONTENT_FIELD) or "").strip()
        if not content:
            continue

        # Check 1: hash exato (textos idênticos)
        h = _simple_hash(content)
        if h in seen_hashes:
            logger.debug(f"Dedup: removendo duplicata exata de {d.get('chunk_id', '?')}")
            continue
        seen_hashes.add(h)

        # Check 2: Jaccard similarity (textos muito parecidos)
        words = set(content.lower().split())
        is_dup = False
        for seen_words in seen_word_sets:
            if not words or not seen_words:
                continue
            intersection = len(words & seen_words)
            union = len(words | seen_words)
            jaccard = intersection / union if union > 0 else 0
            if jaccard >= similarity_threshold:
                is_dup = True
                logger.debug(f"Dedup: removendo chunk similar (jaccard={jaccard:.2f})")
                break

        if not is_dup:
            seen_word_sets.append(words)
            unique.append(d)

    removed = len(details) - len(unique)
    if removed > 0:
        logger.info(f"Deduplicação: {removed} chunks removidos, {len(unique)} únicos mantidos")

    return unique


# ─── Formatação rica de contexto ─────────────────────────────────────────────

def format_contexts_for_llm(details: List[Dict[str, Any]]) -> str:
    """
    Formata os contextos recuperados com metadados para o LLM.
    Inclui: fonte, tipo de documento, área do direito, score de relevância.
    """
    if not details:
        return ""

    blocks = []
    for i, d in enumerate(details, 1):
        content = (d.get(CONTENT_FIELD) or "").strip()
        if not content:
            continue

        source = d.get("arquivo_origem", "desconhecido")
        tipo = d.get("tipo_documento", "")
        area = d.get("area_direito", "")
        score = d.get("_rerank_score") or d.get("_rrf_score")

        header_parts = [f"[Fonte {i}: {source}"]
        if tipo:
            header_parts.append(f"Tipo: {tipo}")
        if area:
            header_parts.append(f"Área: {area}")
        if score is not None:
            header_parts.append(f"Relevância: {float(score):.2f}")
        header = " | ".join(header_parts) + "]"

        blocks.append(f"{header}\n{content}")

    return "\n\n---\n\n".join(blocks)


# ─── Recuperação de contexto ──────────────────────────────────────────────────

def retrieve_context(
    query_text: str,
    qdrant_client: QdrantClient,
    client_openai: OpenAI,
    top_k: int = 10,
    bm25_candidates: int = 30,
    dense_candidates: int = 30,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Recupera contextos via Qdrant hybrid search (dense + BM25 + RRF).
    Aplica query expansion antes da busca.
    Retorna (texts, details).
    """
    # Query expansion: adiciona termos jurídicos equivalentes
    expanded_query = expand_query(query_text)

    vec = get_embedding(expanded_query, client_openai)
    if vec is None:
        logger.warning("Embedding falhou — sem resultados de busca semântica.")
        return [], []

    hits = _hybrid_search(
        qdrant_client,
        QDRANT_COLLECTION,
        expanded_query,
        vec,
        top_k=top_k,
        bm25_candidates=bm25_candidates,
        dense_candidates=dense_candidates,
    )

    texts: List[str] = []
    details: List[Dict[str, Any]] = []
    for h in hits:
        content = (h.get(CONTENT_FIELD) or "").strip()
        if content:
            texts.append(content)
            details.append(h)

    return texts, details


# ─── Web search (Tavily) ──────────────────────────────────────────────────────

def web_search(query: str, num_results: int = 3, search_depth: str = "advanced") -> List[Dict[str, str]]:
    """
    Busca na web via Tavily API.
    Retorna texto extraído das páginas (não só snippets).

    search_depth: "basic" (rápido) ou "advanced" (extrai conteúdo completo)
    """
    if not TAVILY_API_KEY:
        return []
    try:
        import requests
        payload = {
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": search_depth,
            "max_results": max(1, min(10, int(num_results))),
            "include_answer": False,
            "include_raw_content": False,
        }
        r = requests.post(
            "https://api.tavily.com/search",
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return [
            {
                "title": (it.get("title") or "").strip(),
                "snippet": (it.get("content") or "").strip(),  # Tavily retorna texto completo aqui
                "link": (it.get("url") or "").strip(),
            }
            for it in r.json().get("results", [])[:num_results]
        ]
    except Exception as exc:
        logger.error(f"Tavily search falhou: {exc}")
        return []


def format_web_results(results: List[Dict[str, str]]) -> str:
    if not results:
        return ""
    return "\n\n".join(
        f"[Fonte web {i}: {r.get('title', '')}]\n{r.get('snippet', '')}\nURL: {r.get('link', '')}"
        for i, r in enumerate(results, 1)
    ).strip()


# ─── GraphRAG ────────────────────────────────────────────────────────────────

def _looks_complex_query(q: str) -> bool:
    keywords = [
        "requisitos", "elementos", "cabimento", "competência", "prazo",
        "nulidade", "abusividade", "tese", "fundamentação", "ônus",
        "nexo", "responsabilidade", "prescrição", "decadência",
        "prova", "tutela", "liminar", "jurisprudência", "precedente",
        "contrato", "cláusula", "rescisão", "indenização", "dano", "multa",
        "substitui", "reforma", "julgado", "divergência", "conflito",
        "inconstitucional", "súmula", "vinculante", "repercussão geral",
        "recurso especial", "recurso extraordinário", "embargos",
    ]
    qn = (q or "").lower()
    return any(k in qn for k in keywords) or len(qn.split()) >= 14


def should_use_graph_rag(user_query: str, num_contexts: int, force: bool = False) -> bool:
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
    """Constrói grafo com PageRank + betweenness + comunidades. Retorna (summary, html_path)."""
    from graph_rag import GraphRAG

    docs_for_graph = [
        {
            "chunk_id": d.get("chunk_id") or "",
            "content": (d.get(CONTENT_FIELD) or "").strip(),
            "arquivo_origem": d.get("arquivo_origem") or "",
            "tipo_documento": d.get("tipo_documento") or "",
        }
        for d in retrieved_details or []
        if (d.get(CONTENT_FIELD) or "").strip()
    ]

    if len(docs_for_graph) < 2:
        return "", ""

    try:
        gr = GraphRAG(retrieved_documents=docs_for_graph, user_query=user_query)
        gr.process()
        summary = (gr.generate_textual_summary_for_llm() or "").strip()

        html_path = ""
        if save_html and summary:
            filename = _make_graph_filename(user_query)
            html_path = os.path.join(GRAPH_VIZ_DIR, filename)
            gr.visualize_graph(output_filename=html_path)

        return summary, html_path
    except Exception as exc:
        logger.error(f"GraphRAG falhou: {exc}")
        return "", ""


# ─── LLM helpers (Claude) ────────────────────────────────────────────────────

def _build_anthropic_messages(
    chat_history: Optional[List[Dict[str, str]]],
    user_instruction: str,
) -> List[Dict[str, str]]:
    msgs: List[Dict[str, str]] = []
    for m in chat_history or []:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": user_instruction})
    return msgs


def _call_llm(
    client_anthropic: anthropic.Anthropic,
    system_message: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 4096,
    retry_count: int = 2,
) -> str:
    """Chama Claude com retry automático."""
    for attempt in range(retry_count + 1):
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
            logger.error(f"Erro ao chamar Claude ({ANTHROPIC_MODEL}), tentativa {attempt+1}: {exc}")
            if attempt < retry_count:
                time.sleep(2 ** attempt)
            else:
                return ""


# ─── API principal ────────────────────────────────────────────────────────────

def generate_response_with_rag_and_web_fallback(
    user_query: str,
    system_message_base: str = "",
    chat_history: Optional[List[Dict[str, str]]] = None,
    qdrant_client: Optional[QdrantClient] = None,
    client_openai: Optional[OpenAI] = None,
    client_anthropic: Optional[anthropic.Anthropic] = None,
    # Busca
    top_k: int = 10,
    bm25_candidates: int = 30,
    dense_candidates: int = 30,
    # Web fallback
    use_web_fallback: bool = True,
    min_contexts_for_web_fallback: int = 1,
    num_web_results: int = 3,
    # LLM
    temperature: float = 0.2,
    max_tokens: int = 4096,
    # Reranking
    use_rerank: bool = True,
    top_k_rerank: int = 7,
    use_cross_encoder: bool = True,
    # GraphRAG
    use_graph_rag: str = "auto",
    max_details_for_graph: int = 12,
    save_graph_html: bool = True,
) -> Tuple[str, List[str], List[Dict[str, Any]], List[Dict[str, str]], str, str]:
    """
    Pipeline RAG completo com Claude + Qdrant.

    Melhorias aplicadas:
      - System prompt jurídico especializado
      - Query expansion (termos jurídicos equivalentes)
      - Deduplicação de contextos
      - Formatação rica com metadados
      - Retry automático no LLM

    Returns: (answer, contexts, details, web_results, graph_summary, graph_html_path)
    """
    if client_openai is None:
        client_openai = get_openai_client()
    if client_anthropic is None:
        client_anthropic = get_anthropic_client()
    if qdrant_client is None:
        qdrant_client = get_qdrant_client()

    if not client_openai:
        return "Erro: OpenAI (embeddings) não inicializado.", [], [], [], "", ""
    if not client_anthropic:
        return "Erro: Anthropic (Claude) não inicializado.", [], [], [], "", ""
    if not qdrant_client:
        return "Erro: Qdrant não inicializado.", [], [], [], "", ""

    # 1. Busca híbrida Qdrant (com query expansion)
    contexts, details = retrieve_context(
        user_query, qdrant_client, client_openai,
        top_k=int(top_k),
        bm25_candidates=int(bm25_candidates),
        dense_candidates=int(dense_candidates),
    )

    # 2. Reranking
    if use_rerank and details:
        try:
            details = _rerank(
                query=user_query,
                chunks=details,
                top_k=int(top_k_rerank),
                anthropic_client=client_anthropic,
                use_cross_encoder=bool(use_cross_encoder),
                content_field=CONTENT_FIELD,
            )
            contexts = [
                (h.get(CONTENT_FIELD) or "").strip()
                for h in details
                if (h.get(CONTENT_FIELD) or "").strip()
            ]
        except Exception as exc:
            logger.error(f"Reranking falhou: {exc}")

    # 3. Deduplicação de contextos
    if details:
        details = deduplicate_contexts(details, similarity_threshold=0.85)
        contexts = [
            (h.get(CONTENT_FIELD) or "").strip()
            for h in details
            if (h.get(CONTENT_FIELD) or "").strip()
        ]

    # 4. GraphRAG
    graph_summary, graph_html_path = "", ""
    use_gr = (use_graph_rag or "auto").strip().lower()
    should_gr = (
        len(details) >= 2 if use_gr == "on"
        else False if use_gr == "off"
        else should_use_graph_rag(user_query, len(contexts))
    )

    if should_gr:
        try:
            graph_summary, graph_html_path = build_graphrag_summary(
                details[: max(2, min(int(max_details_for_graph), len(details)))],
                user_query=user_query,
                save_html=bool(save_graph_html),
            )
        except Exception as exc:
            logger.error(f"GraphRAG build falhou: {exc}")

    # 5. Web fallback
    web_results: List[Dict[str, str]] = []
    web_block = ""
    if use_web_fallback and len(contexts) < int(min_contexts_for_web_fallback):
        web_results = web_search(user_query, num_results=int(num_web_results))
        web_block = format_web_results(web_results)

    # 6. Montar system prompt
    # Se o frontend enviou system_prompt customizado, usa ele como base + adiciona o jurídico
    if system_message_base and system_message_base.strip():
        system_prompt = f"{system_message_base.strip()}\n\n{SYSTEM_PROMPT_JURIDICO}"
    else:
        system_prompt = SYSTEM_PROMPT_JURIDICO

    # 7. Montar contexto formatado com metadados
    ctx_block = format_contexts_for_llm(details) if details else ""
    final_user = user_query

    if ctx_block:
        final_user += f"\n\n===== DOCUMENTOS RECUPERADOS DA BASE =====\n\n{ctx_block}"

    if graph_summary:
        final_user += f"\n\n===== MAPA ESTRUTURADO (GraphRAG) =====\n{graph_summary}"

    if web_block:
        final_user += (
            f"\n\n===== RESULTADOS DA WEB (use com cautela — verificar fontes) =====\n{web_block}"
        )

    messages = _build_anthropic_messages(chat_history, final_user)
    answer = _call_llm(
        client_anthropic,
        system_message=system_prompt,
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
) -> str:
    answer, *_ = generate_response_with_rag_and_web_fallback(
        user_query=user_instruction,
        system_message_base=system_message_base,
        chat_history=chat_history,
        top_k=top_k,
        use_web_fallback=use_web_fallback,
        use_rerank=use_rerank,
        use_cross_encoder=use_cross_encoder,
        use_graph_rag=use_graph_rag,
    )
    return answer
