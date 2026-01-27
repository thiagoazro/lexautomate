# app.py (Resumo de Documento - sem URLs externas)
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

# Prompt
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file_path = os.path.join(current_dir, ".", "prompts", "system_prompt_app_resumo.md")
    if not os.path.exists(prompt_file_path):
        alt = os.path.join(os.path.dirname(current_dir), "prompts", "system_prompt_app_resumo.md")
        prompt_file_path = alt if os.path.exists(alt) else os.path.join("prompts", "system_prompt_app_resumo.md")
    SYSTEM_PROMPT_APP_RESUMO = open(prompt_file_path, "r", encoding="utf-8").read()
    print(f"INFO APP (Resumo): Prompt carregado de: {prompt_file_path}")
except Exception as e:
    st.error(f"Erro ao carregar o prompt do resumo: {e}. Usando prompt padrão.")
    SYSTEM_PROMPT_APP_RESUMO = "Você é um assistente de IA. Seja breve e direto."


def _maybe_save_graphrag_html(details, user_query: str, filename_prefix: str):
    """
    Gera e salva HTML do GraphRAG em graph_visualizations/.
    Retorna o caminho do arquivo HTML (ou None).
    """
    try:
        from graph_rag import GraphRAG
    except Exception:
        return None

    try:
        docs_for_graph = []
        for d in details or []:
            content = (d.get("content") or d.get("OPENSEARCH_TEXT_FIELD") or d.get("text") or "").strip()
            if not content:
                content = (d.get("content") or "").strip()
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
        html_path = gr.visualize_graph(filename_prefix=filename_prefix, output_dir="graph_visualizations", show_buttons=True)
        return html_path
    except Exception:
        return None


def resumo_interface():
    st.subheader("📄 Resumo de Documento Jurídico")
    st.caption(f"Modelo: {OPENAI_LLM_MODEL}")
    st.markdown("Envie documentos e forneça instruções para gerar um resumo conciso e informativo.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_opensearch_client()
    if not client_openai or not search_client:
        st.error("Falha ao inicializar serviços de IA. Verifique OPENAI_API_KEY e OpenSearch.")
        st.stop()

    uploaded_files = st.file_uploader(
        "1. Envie um ou mais documentos (PDF, DOCX)",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        key="resumo_multi_uploader_app_no_url",
    )

    # Session state
    if "resumo_multi_texto_extraido_app_no_url" not in st.session_state:
        st.session_state.resumo_multi_texto_extraido_app_no_url = ""
    if "resumo_rag_response_app_no_url" not in st.session_state:
        st.session_state.resumo_rag_response_app_no_url = ""
    if "resumo_edited_response_app_no_url" not in st.session_state:
        st.session_state.resumo_edited_response_app_no_url = ""
    if "resumo_final_version_app_no_url" not in st.session_state:
        st.session_state.resumo_final_version_app_no_url = None
    if "geracao_em_andamento_resumo_app_no_url" not in st.session_state:
        st.session_state.geracao_em_andamento_resumo_app_no_url = False

    if "last_retrieved_chunks_details_resumo_app_no_url" not in st.session_state:
        st.session_state.last_retrieved_chunks_details_resumo_app_no_url = []
    if "last_web_results_resumo_app_no_url" not in st.session_state:
        st.session_state.last_web_results_resumo_app_no_url = []
    if "last_graph_html_resumo_app_no_url" not in st.session_state:
        st.session_state.last_graph_html_resumo_app_no_url = None

    if "last_prompt_resumo_app_no_url" not in st.session_state:
        st.session_state.last_prompt_resumo_app_no_url = ""
    if "last_response_text_resumo_app_no_url" not in st.session_state:
        st.session_state.last_response_text_resumo_app_no_url = ""

    if not st.session_state.geracao_em_andamento_resumo_app_no_url:
        st.session_state.last_retrieved_chunks_details_resumo_app_no_url = []
        st.session_state.last_web_results_resumo_app_no_url = []
        st.session_state.last_graph_html_resumo_app_no_url = None

    # Extração de texto
    if uploaded_files and not st.session_state.resumo_multi_texto_extraido_app_no_url:
        textos = []
        st.session_state.geracao_em_andamento_resumo_app_no_url = True

        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_file_path = f"temp_resumo_app_no_url_{uuid.uuid4().hex}{ext}"
            try:
                with open(temp_file_path, "wb") as f:
                    f.write(file.getvalue())
                with st.spinner(f"Extraindo texto de {file.name}..."):
                    texto = extrair_texto_documento(temp_file_path, ext)
                if texto:
                    textos.append(f"---\n**Documento: {file.name}**\n\n{texto}")
                else:
                    st.warning(f"Nenhum texto extraído de {file.name}.")
            except Exception as e:
                st.error(f"Erro ao processar {file.name}: {e}")
                print(traceback.format_exc())
            finally:
                try:
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
                except Exception:
                    pass

        st.session_state.resumo_multi_texto_extraido_app_no_url = "\n\n".join(textos).strip()
        st.session_state.geracao_em_andamento_resumo_app_no_url = False

    instrucoes = st.text_area(
        "2. Direcione o resumo (opcional)",
        placeholder="Ex.: destaque prazos, valores, obrigações, riscos, pedidos etc.",
        key="resumo_instrucoes_app_no_url",
    )

    if st.session_state.resumo_multi_texto_extraido_app_no_url:
        st.text_area(
            "Texto extraído (somente leitura)",
            value=st.session_state.resumo_multi_texto_extraido_app_no_url,
            height=220,
            disabled=True,
        )

    if st.button("Gerar Resumo com RAG", type="primary", key="btn_gerar_resumo_app_no_url"):
        if not st.session_state.resumo_multi_texto_extraido_app_no_url.strip():
            st.warning("Envie pelo menos um documento para resumir.")
        else:
            st.session_state.geracao_em_andamento_resumo_app_no_url = True
            st.session_state.last_graph_html_resumo_app_no_url = None

            user_query = (
                f"INSTRUÇÕES DO USUÁRIO:\n{instrucoes.strip()}\n\n"
                f"DOCUMENTOS (texto extraído):\n{st.session_state.resumo_multi_texto_extraido_app_no_url}"
            ).strip()

            st.session_state.last_prompt_resumo_app_no_url = user_query

            with st.spinner("Gerando resumo com RAG..."):
                answer, _ctx, details, web_results, graph_summary = generate_response_with_rag_and_web_fallback(
                    user_query=user_query,
                    system_message_base=SYSTEM_PROMPT_APP_RESUMO,
                    chat_history=None,
                    search_client=search_client,
                    client_openai=client_openai,
                    top_k=10,
                    use_web_fallback=True,
                    min_contexts_for_web_fallback=1,
                    num_web_results=2,
                    temperature=0.2,
                    max_tokens=1800,
                    use_llm_rerank=True,
                    top_k_rerank=7,
                    use_graph_rag="auto",
                    app_hint="app1",
                )

            st.session_state.resumo_rag_response_app_no_url = answer or ""
            st.session_state.last_response_text_resumo_app_no_url = answer or ""
            st.session_state.last_retrieved_chunks_details_resumo_app_no_url = details or []
            st.session_state.last_web_results_resumo_app_no_url = web_results or []

            # Salva Graph HTML (se houver material)
            html_path = _maybe_save_graphrag_html(details, user_query=user_query, filename_prefix="app1_resumo")
            st.session_state.last_graph_html_resumo_app_no_url = html_path

            st.session_state.geracao_em_andamento_resumo_app_no_url = False

    # Mostra resposta
    if st.session_state.resumo_rag_response_app_no_url:
        st.markdown("### Resultado")
        st.write(st.session_state.resumo_rag_response_app_no_url)

        # Visualização GraphRAG
        if st.session_state.last_graph_html_resumo_app_no_url:
            with st.expander("🕸️ Ver visualização do GraphRAG (HTML)", expanded=False):
                st.caption(f"Arquivo: {st.session_state.last_graph_html_resumo_app_no_url}")
                try:
                    html = open(st.session_state.last_graph_html_resumo_app_no_url, "r", encoding="utf-8").read()
                    components.html(html, height=800, scrolling=True)
                except Exception as e:
                    st.warning(f"Não foi possível embutir o HTML aqui. Erro: {e}")

        # Download DOCX
        if st.button("Gerar DOCX", key="btn_docx_resumo"):
            try:
                path = gerar_docx(st.session_state.resumo_rag_response_app_no_url, "resumo.docx")
                with open(path, "rb") as f:
                    st.download_button("Baixar DOCX", data=f, file_name="resumo.docx")
            except Exception as e:
                st.error(f"Erro ao gerar DOCX: {e}")

    # Feedback
    if st.session_state.get("last_response_text_resumo_app_no_url"):
        with st.expander("💬 Sua opinião nos ajuda a melhorar", expanded=False):
            fb = st.radio("Essa resposta foi útil?", ["👍 Sim", "👎 Não"], key="fb_resumo_radio")
            comentario = st.text_area("Comentário (opcional):", key="fb_resumo_comment")
            if st.button("Enviar Feedback", key="fb_resumo_btn"):
                salvar_feedback_rag(
                    pergunta=st.session_state.get("last_prompt_resumo_app_no_url", ""),
                    resposta=st.session_state.get("last_response_text_resumo_app_no_url", ""),
                    feedback=fb,
                    comentario=comentario,
                )
                st.success("Feedback enviado. Obrigado!")
