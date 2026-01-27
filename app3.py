# app3.py (Validação de Cláusulas - com RAG + URLs Sidebar + GraphRAG HTML)
# OpenAI + OpenSearch + Serper + GraphRAG HTML (salva em graph_visualizations/)

import os
import uuid
import traceback
import streamlit as st
import streamlit.components.v1 as components

from rag_docintelligence import extrair_texto_documento
from rag_utils import (
    get_openai_client,
    get_opensearch_client,
    generate_response_with_rag_and_web_fallback,
    gerar_docx,
    OPENAI_LLM_MODEL,
    salvar_feedback_rag,
)
from chroma_utils import obter_contexto_relevante_de_url

# Prompt
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file_path = os.path.join(current_dir, ".", "prompts", "system_prompt_app3_validacao.md")
    if not os.path.exists(prompt_file_path):
        alt = os.path.join(os.path.dirname(current_dir), "prompts", "system_prompt_app3_validacao.md")
        prompt_file_path = alt if os.path.exists(alt) else os.path.join("prompts", "system_prompt_app3_validacao.md")
    SYSTEM_PROMPT_APP3_VALIDACAO = open(prompt_file_path, "r", encoding="utf-8").read()
    print(f"INFO APP3 (Validação): Prompt carregado de: {prompt_file_path}")
except Exception as e:
    st.error(f"Erro ao carregar o prompt do app3: {e}. Usando prompt padrão.")
    SYSTEM_PROMPT_APP3_VALIDACAO = "Você é um assistente de IA para validar cláusulas."

def _maybe_save_graphrag_html(details, user_query: str, filename_prefix: str):
    try:
        from graph_rag import GraphRAG
    except Exception:
        return None
    try:
        docs_for_graph = []
        for d in details or []:
            content = (d.get("content") or d.get("text") or "").strip()
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
            return None
        gr = GraphRAG(retrieved_documents=docs_for_graph, user_query=user_query)
        gr.process()
        return gr.visualize_graph(filename_prefix=filename_prefix, output_dir="graph_visualizations", show_buttons=True)
    except Exception:
        return None


def validacao_interface():
    st.subheader("📑 Validação / Análise de Cláusulas")
    st.caption(f"Modelo: {OPENAI_LLM_MODEL}")
    st.markdown("Envie contratos e indique a cláusula. Opcionalmente use URLs da sidebar.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_opensearch_client()
    if not client_openai or not search_client:
        st.error("Falha ao inicializar serviços de IA.")
        st.stop()

    sfx = "_app3_sidebar"
    if f"texto_extraido{sfx}" not in st.session_state:
        st.session_state[f"texto_extraido{sfx}"] = ""
    if f"resp{sfx}" not in st.session_state:
        st.session_state[f"resp{sfx}"] = ""
    if f"last_details{sfx}" not in st.session_state:
        st.session_state[f"last_details{sfx}"] = []
    if f"last_web{sfx}" not in st.session_state:
        st.session_state[f"last_web{sfx}"] = []
    if f"last_graph_html{sfx}" not in st.session_state:
        st.session_state[f"last_graph_html{sfx}"] = None
    if f"last_prompt{sfx}" not in st.session_state:
        st.session_state[f"last_prompt{sfx}"] = ""

    uploaded_files = st.file_uploader(
        "1. Envie documentos (PDF, DOCX) - opcional",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        key=f"uploader{sfx}",
    )

    if uploaded_files:
        textos = []
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_file_path = f"temp_validacao_{uuid.uuid4().hex}{ext}"
            try:
                with open(temp_file_path, "wb") as f:
                    f.write(file.getvalue())
                with st.spinner(f"Extraindo texto de {file.name}..."):
                    texto = extrair_texto_documento(temp_file_path, ext)
                if texto:
                    textos.append(f"---\n**Documento: {file.name}**\n\n{texto}")
            except Exception as e:
                st.error(f"Erro ao processar {file.name}: {e}")
                print(traceback.format_exc())
            finally:
                try:
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
                except Exception:
                    pass

        st.session_state[f"texto_extraido{sfx}"] = "\n\n".join(textos).strip()

    clausula = st.text_area("2. Cole a cláusula (ou descreva)", key=f"clausula{sfx}", height=160)
    objetivo = st.text_area("3. Objetivo da análise (opcional)", key=f"obj{sfx}", height=100)

    urls_contexto = [st.session_state.get("sidebar_url1",""), st.session_state.get("sidebar_url2",""), st.session_state.get("sidebar_url3","")]
    urls_contexto = [u for u in urls_contexto if (u or "").strip()]

    if st.button("Analisar Cláusula (RAG)", type="primary", key=f"btn{sfx}"):
        st.session_state[f"last_graph_html{sfx}"] = None

        urls_block_prompt = ""
        if urls_contexto:
            for i, url_item in enumerate(urls_contexto, start=1):
                ctx = obter_contexto_relevante_de_url(url_item, clausula, top_k_chunks=2) or ""
                if ctx.strip():
                    urls_block_prompt += f"\n--- Contexto da URL {i} ({url_item}) ---\n{ctx}\n--- Fim ---\n"

        user_query = (
            f"CLÁUSULA / TRECHO:\n{clausula.strip()}\n\n"
            f"OBJETIVO:\n{objetivo.strip()}\n\n"
            f"DOCUMENTOS (texto extraído):\n{st.session_state.get(f'texto_extraido{sfx}','')}\n\n"
            f"{urls_block_prompt}"
        ).strip()

        st.session_state[f"last_prompt{sfx}"] = user_query

        with st.spinner("Analisando com RAG..."):
            answer, _ctx, details, web_results, graph_summary = generate_response_with_rag_and_web_fallback(
                user_query=user_query,
                system_message_base=SYSTEM_PROMPT_APP3_VALIDACAO,
                chat_history=None,
                search_client=search_client,
                client_openai=client_openai,
                top_k=12,
                use_web_fallback=True,
                min_contexts_for_web_fallback=1,
                num_web_results=2,
                temperature=0.2,
                max_tokens=2500,
                use_llm_rerank=True,
                top_k_rerank=7,
                use_graph_rag="auto",
                app_hint="app3",
            )

        st.session_state[f"resp{sfx}"] = answer or ""
        st.session_state[f"last_details{sfx}"] = details or []
        st.session_state[f"last_web{sfx}"] = web_results or []

        html_path = _maybe_save_graphrag_html(details, user_query=user_query, filename_prefix="app3_validacao")
        st.session_state[f"last_graph_html{sfx}"] = html_path

    if st.session_state.get(f"resp{sfx}"):
        st.markdown("### Resultado")
        st.write(st.session_state[f"resp{sfx}"])

        if st.session_state.get(f"last_graph_html{sfx}"):
            with st.expander("🕸️ Ver visualização do GraphRAG (HTML)", expanded=False):
                st.caption(f"Arquivo: {st.session_state[f'last_graph_html{sfx}']}")
                try:
                    html = open(st.session_state[f"last_graph_html{sfx}"], "r", encoding="utf-8").read()
                    components.html(html, height=800, scrolling=True)
                except Exception as e:
                    st.warning(f"Não foi possível embutir o HTML. Erro: {e}")

        if st.button("Gerar DOCX", key=f"btn_docx{sfx}"):
            try:
                path = gerar_docx(st.session_state[f"resp{sfx}"], "validacao.docx")
                with open(path, "rb") as f:
                    st.download_button("Baixar DOCX", data=f, file_name="validacao.docx")
            except Exception as e:
                st.error(f"Erro ao gerar DOCX: {e}")

        with st.expander("💬 Feedback", expanded=False):
            fb = st.radio("Útil?", ["👍 Sim", "👎 Não"], key=f"fb_radio{sfx}")
            comentario = st.text_area("Comentário (opcional):", key=f"fb_comment{sfx}")
            if st.button("Enviar Feedback", key=f"fb_btn{sfx}"):
                salvar_feedback_rag(
                    pergunta=st.session_state.get(f"last_prompt{sfx}", ""),
                    resposta=st.session_state.get(f"resp{sfx}", ""),
                    feedback=fb,
                    comentario=comentario,
                )
                st.success("Feedback enviado!")
