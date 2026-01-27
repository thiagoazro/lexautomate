# app2.py (Peça Jurídica Livre - com RAG + URLs Sidebar + GraphRAG HTML)
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
    prompt_file_path = os.path.join(current_dir, ".", "prompts", "system_prompt_app2_peticao.md")
    if not os.path.exists(prompt_file_path):
        alt = os.path.join(os.path.dirname(current_dir), "prompts", "system_prompt_app2_peticao.md")
        prompt_file_path = alt if os.path.exists(alt) else os.path.join("prompts", "system_prompt_app2_peticao.md")
    SYSTEM_PROMPT_APP2_PETICAO = open(prompt_file_path, "r", encoding="utf-8").read()
    print(f"INFO APP2 (Petição): Prompt carregado de: {prompt_file_path}")
except Exception as e:
    st.error(f"Erro ao carregar o prompt do app2: {e}. Usando prompt padrão.")
    SYSTEM_PROMPT_APP2_PETICAO = "Você é um assistente jurídico que redige peças."

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


def peticao_interface():
    st.subheader("✍️ Peça Jurídica Livre")
    st.caption(f"Modelo: {OPENAI_LLM_MODEL}")
    st.markdown("Envie documentos, descreva os fatos e peça a elaboração de uma peça. Use URLs da sidebar se quiser.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_opensearch_client()
    if not client_openai or not search_client:
        st.error("Falha ao inicializar serviços de IA.")
        st.stop()

    sfx = "_app2_sidebar"
    if f"peticao_texto_extraido{sfx}" not in st.session_state:
        st.session_state[f"peticao_texto_extraido{sfx}"] = ""
    if f"peticao_rag_response{sfx}" not in st.session_state:
        st.session_state[f"peticao_rag_response{sfx}"] = ""
    if f"last_retrieved_chunks_details_peticao{sfx}" not in st.session_state:
        st.session_state[f"last_retrieved_chunks_details_peticao{sfx}"] = []
    if f"last_web_results_peticao{sfx}" not in st.session_state:
        st.session_state[f"last_web_results_peticao{sfx}"] = []
    if f"last_graph_html_peticao{sfx}" not in st.session_state:
        st.session_state[f"last_graph_html_peticao{sfx}"] = None
    if f"last_prompt_peticao{sfx}" not in st.session_state:
        st.session_state[f"last_prompt_peticao{sfx}"] = ""
    if f"last_response_text_peticao{sfx}" not in st.session_state:
        st.session_state[f"last_response_text_peticao{sfx}"] = ""

    uploaded_files = st.file_uploader(
        "1. Envie documentos (PDF, DOCX) - opcional",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        key=f"peticao_uploader{sfx}",
    )

    if uploaded_files:
        textos = []
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_file_path = f"temp_peticao_{uuid.uuid4().hex}{ext}"
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

        st.session_state[f"peticao_texto_extraido{sfx}"] = "\n\n".join(textos).strip()

    fatos = st.text_area("2. Descreva os fatos", key=f"peticao_fatos{sfx}", height=160)
    pedido = st.text_area("3. Pedido / Objetivo", key=f"peticao_pedido{sfx}", height=120)

    # URLs da sidebar
    urls_contexto = [st.session_state.get("sidebar_url1",""), st.session_state.get("sidebar_url2",""), st.session_state.get("sidebar_url3","")]
    urls_contexto = [u for u in urls_contexto if (u or "").strip()]

    if st.button("Gerar Peça (RAG)", type="primary", key=f"btn_peticao{sfx}"):
        st.session_state[f"last_graph_html_peticao{sfx}"] = None

        urls_block_prompt = ""
        if urls_contexto:
            for i, url_item in enumerate(urls_contexto, start=1):
                ctx = obter_contexto_relevante_de_url(url_item, f"{fatos}\n{pedido}", top_k_chunks=2) or ""
                if ctx.strip():
                    urls_block_prompt += f"\n--- Contexto da URL {i} ({url_item}) ---\n{ctx}\n--- Fim ---\n"

        user_query = (
            f"FATOS:\n{fatos.strip()}\n\n"
            f"PEDIDO:\n{pedido.strip()}\n\n"
            f"DOCUMENTOS (texto extraído):\n{st.session_state.get(f'peticao_texto_extraido{sfx}','')}\n\n"
            f"{urls_block_prompt}"
        ).strip()

        st.session_state[f"last_prompt_peticao{sfx}"] = user_query

        with st.spinner("Gerando peça com RAG..."):
            answer, _ctx, details, web_results, graph_summary = generate_response_with_rag_and_web_fallback(
                user_query=user_query,
                system_message_base=SYSTEM_PROMPT_APP2_PETICAO,
                chat_history=None,
                search_client=search_client,
                client_openai=client_openai,
                top_k=12,
                use_web_fallback=False,  # peça mais determinística por padrão
                min_contexts_for_web_fallback=1,
                num_web_results=2,
                temperature=0.3,
                max_tokens=4000,
                use_llm_rerank=True,
                top_k_rerank=7,
                use_graph_rag="auto",
                app_hint="app2",
            )

        st.session_state[f"peticao_rag_response{sfx}"] = answer or ""
        st.session_state[f"last_response_text_peticao{sfx}"] = answer or ""
        st.session_state[f"last_retrieved_chunks_details_peticao{sfx}"] = details or []
        st.session_state[f"last_web_results_peticao{sfx}"] = web_results or []

        # Graph HTML
        html_path = _maybe_save_graphrag_html(details, user_query=user_query, filename_prefix="app2_peticao")
        st.session_state[f"last_graph_html_peticao{sfx}"] = html_path

    if st.session_state.get(f"peticao_rag_response{sfx}"):
        st.markdown("### Resultado")
        st.write(st.session_state[f"peticao_rag_response{sfx}"])

        if st.session_state.get(f"last_graph_html_peticao{sfx}"):
            with st.expander("🕸️ Ver visualização do GraphRAG (HTML)", expanded=False):
                st.caption(f"Arquivo: {st.session_state[f'last_graph_html_peticao{sfx}']}")
                try:
                    html = open(st.session_state[f"last_graph_html_peticao{sfx}"], "r", encoding="utf-8").read()
                    components.html(html, height=800, scrolling=True)
                except Exception as e:
                    st.warning(f"Não foi possível embutir o HTML. Erro: {e}")

        if st.button("Gerar DOCX", key=f"btn_docx_peticao{sfx}"):
            try:
                path = gerar_docx(st.session_state[f"peticao_rag_response{sfx}"], "peca.docx")
                with open(path, "rb") as f:
                    st.download_button("Baixar DOCX", data=f, file_name="peca.docx")
            except Exception as e:
                st.error(f"Erro ao gerar DOCX: {e}")

        with st.expander("💬 Feedback", expanded=False):
            fb = st.radio("Útil?", ["👍 Sim", "👎 Não"], key=f"fb_peticao_radio{sfx}")
            comentario = st.text_area("Comentário (opcional):", key=f"fb_peticao_comment{sfx}")
            if st.button("Enviar Feedback", key=f"fb_peticao_btn{sfx}"):
                salvar_feedback_rag(
                    pergunta=st.session_state.get(f"last_prompt_peticao{sfx}", ""),
                    resposta=st.session_state.get(f"last_response_text_peticao{sfx}", ""),
                    feedback=fb,
                    comentario=comentario,
                )
                st.success("Feedback enviado!")
