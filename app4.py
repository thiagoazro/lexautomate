# app4.py (Consultor Jurídico lendo URLs da Sidebar Global) — COM GraphRAG + HTML salvo
import os
import uuid
import streamlit as st
import streamlit.components.v1 as components

from rag_utils import (
    salvar_feedback_rag,
    get_openai_client,
    get_opensearch_client,
    generate_response_with_rag_and_web_fallback,
    OPENAI_LLM_MODEL,
)
from chroma_utils import obter_contexto_relevante_de_url


# Carrega o prompt do consultor
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file_path = os.path.join(current_dir, "..", "prompts", "system_prompt_app4_consultor.md")
    if not os.path.exists(prompt_file_path):
        prompt_file_path_alt = os.path.join(os.path.dirname(current_dir), "prompts", "system_prompt_app4_consultor.md")
        if os.path.exists(prompt_file_path_alt):
            prompt_file_path = prompt_file_path_alt
        else:
            prompt_file_path = os.path.join("prompts", "system_prompt_app4_consultor.md")

    CONSULTOR_SYSTEM_PROMPT_BASE = open(prompt_file_path, "r", encoding="utf-8").read()
    print(f"INFO APP4 (Consultor): Prompt carregado de: {prompt_file_path}")
except Exception as e:
    st.error(f"Erro ao carregar o prompt do consultor: {e}. Usando prompt padrão.")
    CONSULTOR_SYSTEM_PROMPT_BASE = "Você é LexConsult, um assistente jurídico virtual Sênior especializado no Direito Brasileiro."


def _render_graph_html_if_exists(graph_html_path: str):
    """Renderiza o HTML do GraphRAG dentro do Streamlit, se existir."""
    if not graph_html_path:
        return
    if not os.path.exists(graph_html_path):
        st.warning(f"Grafo salvo, mas o arquivo não foi encontrado: {graph_html_path}")
        return

    st.caption(f"📌 Grafo salvo em: `{graph_html_path}`")
    try:
        with open(graph_html_path, "r", encoding="utf-8") as f:
            html = f.read()
        components.html(html, height=720, scrolling=True)
    except Exception as e:
        st.warning(f"Não foi possível renderizar o HTML do grafo: {e}")


def consultor_juridico_interface():
    st.markdown("Faça perguntas sobre Direito, legislação ou teses jurídicas. Opcionalmente, utilize as URLs da barra lateral para enriquecer a consulta.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_opensearch_client()

    if not client_openai or not search_client:
        st.error("Erro ao inicializar serviços da IA. Verifique as credenciais e configurações.")
        st.stop()

    sfx = "_app4_sidebar"
    if f'consultor_messages{sfx}' not in st.session_state:
        st.session_state[f'consultor_messages{sfx}'] = [
            {"role": "assistant", "content": "Olá! Sou LexConsult, seu assistente jurídico virtual. Como posso ajudar hoje?"}
        ]
    if f'last_user_urls_context_consultor{sfx}' not in st.session_state:
        st.session_state[f'last_user_urls_context_consultor{sfx}'] = ""
    if f'geracao_em_andamento_consultor{sfx}' not in st.session_state:
        st.session_state[f'geracao_em_andamento_consultor{sfx}'] = False
    if f'last_prompt_consultor{sfx}' not in st.session_state:
        st.session_state[f'last_prompt_consultor{sfx}'] = ""
    if f'last_response_text_consultor{sfx}' not in st.session_state:
        st.session_state[f'last_response_text_consultor{sfx}'] = ""

    # Renderiza histórico
    for message in st.session_state[f'consultor_messages{sfx}']:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # Contexto de URLs (se houver)
            if message["role"] == "assistant" and message.get("user_urls_context_used"):
                with st.expander("Detalhes do Contexto das URLs da Barra Lateral Utilizado:", expanded=False):
                    st.markdown(message["user_urls_context_used"], unsafe_allow_html=True)

            # GraphRAG (se houver)
            if message["role"] == "assistant" and message.get("graph_html_path"):
                with st.expander("🕸️ Grafo (GraphRAG) — Visualização", expanded=False):
                    _render_graph_html_if_exists(message.get("graph_html_path", ""))
                if message.get("graph_summary"):
                    with st.expander("🧩 GraphRAG — Sumário estrutural", expanded=False):
                        st.markdown(message["graph_summary"])

    # Input
    if prompt_usuario := st.chat_input("Digite sua pergunta jurídica..."):
        st.session_state[f'consultor_messages{sfx}'].append({"role": "user", "content": prompt_usuario})
        with st.chat_message("user"):
            st.markdown(prompt_usuario)

        st.session_state[f'geracao_em_andamento_consultor{sfx}'] = True
        st.session_state[f'last_user_urls_context_consultor{sfx}'] = ""

        user_instruction_final_para_rag = prompt_usuario
        contexto_urls_agregado_para_prompt = ""
        contexto_urls_agregado_para_exibir = ""

        # URLs da sidebar global (main.py)
        url1_sidebar = st.session_state.get('sidebar_url1', "")
        url2_sidebar = st.session_state.get('sidebar_url2', "")
        url3_sidebar = st.session_state.get('sidebar_url3', "")
        user_urls_from_sidebar = [url for url in [url1_sidebar, url2_sidebar, url3_sidebar] if url.strip()]

        with st.chat_message("assistant"):
            message_placeholder = st.empty()

            if user_urls_from_sidebar:
                urls_detectadas_str = ", ".join([f"'{url}'" for url in user_urls_from_sidebar])
                message_placeholder.info(f"Consultando URLs da barra lateral: {urls_detectadas_str} para contexto adicional...")
            else:
                message_placeholder.info("Nenhuma URL da barra lateral fornecida. Prosseguindo com a consulta padrão...")

            # Processa URLs (Chroma/URL context)
            if user_urls_from_sidebar:
                spinner_message_urls = f"Processando {len(user_urls_from_sidebar)} URL(s) da barra lateral..."
                with st.spinner(spinner_message_urls):
                    for i, url_item in enumerate(user_urls_from_sidebar, 1):
                        contexto_url_individual = obter_contexto_relevante_de_url(
                            url_item,
                            prompt_usuario,
                            top_k_chunks=2
                        )

                        if contexto_url_individual:
                            contexto_urls_agregado_para_exibir += f"<b>Resultado para URL {i} ({url_item}):</b><br>{contexto_url_individual}<hr>"

                            # Só adiciona ao prompt se não for erro/aviso
                            if (
                                "Nenhum conteúdo relevante encontrado nesta URL" not in contexto_url_individual and
                                "Falha ao carregar ou processar o conteúdo da URL" not in contexto_url_individual and
                                "Erro ao buscar informações na URL" not in contexto_url_individual
                            ):
                                contexto_urls_agregado_para_prompt += (
                                    f"\n--- Contexto da URL {i} ({url_item}) ---\n"
                                    f"{contexto_url_individual}\n"
                                    f"--- Fim do Contexto da URL {i} ---\n\n"
                                )

                if contexto_urls_agregado_para_exibir:
                    st.session_state[f'last_user_urls_context_consultor{sfx}'] = contexto_urls_agregado_para_exibir
                else:
                    st.session_state[f'last_user_urls_context_consultor{sfx}'] = (
                        "As URLs da barra lateral foram verificadas, mas não houve conteúdo utilizável para exibir."
                    )

            # Injeta URL context no user_instruction, se útil
            if contexto_urls_agregado_para_prompt:
                user_instruction_final_para_rag = (
                    f"Contextos extraídos de URLs fornecidas pelo usuário (use se relevantes):\n"
                    f"{contexto_urls_agregado_para_prompt}\n"
                    f"Pergunta do usuário: \"{prompt_usuario}\""
                )
            else:
                user_instruction_final_para_rag = prompt_usuario

            # Chamada RAG principal (com GraphRAG auto e salvando HTML)
            message_placeholder.empty()
            with st.spinner("LexConsult está pensando com base em todas as fontes..."):
                resposta, _ctx, _details, _web, graph_summary, graph_html_path = generate_response_with_rag_and_web_fallback(
                    user_query=user_instruction_final_para_rag,
                    system_message_base=CONSULTOR_SYSTEM_PROMPT_BASE,
                    chat_history=st.session_state[f'consultor_messages{sfx}'][:-1],
                    search_client=search_client,
                    client_openai=client_openai,
                    top_k=15,
                    use_web_fallback=True,
                    min_contexts_for_web_fallback=1,
                    num_web_results=2,
                    temperature=0.2,
                    max_tokens=2200,
                    # no consultor, rerank geralmente off (pode ligar se quiser)
                    use_llm_rerank=False,
                    # GraphRAG: auto + hint app4 + salva html
                    use_graph_rag="auto",
                    app_hint="app4",
                    save_graph_html=True,
                )

            response_text = (resposta or "").strip() or "Não consegui gerar uma resposta no momento."
            message_placeholder.markdown(response_text)

            assistant_message_data = {"role": "assistant", "content": response_text}

            # Contexto de URL para expander
            if user_urls_from_sidebar and st.session_state.get(f'last_user_urls_context_consultor{sfx}'):
                assistant_message_data["user_urls_context_used"] = st.session_state[f'last_user_urls_context_consultor{sfx}']

            # GraphRAG (se gerou)
            if graph_html_path:
                assistant_message_data["graph_html_path"] = graph_html_path
            if graph_summary:
                assistant_message_data["graph_summary"] = graph_summary

            st.session_state[f'consultor_messages{sfx}'].append(assistant_message_data)

            st.session_state[f'last_prompt_consultor{sfx}'] = user_instruction_final_para_rag
            st.session_state[f'last_response_text_consultor{sfx}'] = response_text

        st.session_state[f'geracao_em_andamento_consultor{sfx}'] = False
        st.rerun()

    # Feedback
    if f'last_response_text_consultor{sfx}' in st.session_state and st.session_state[f'last_response_text_consultor{sfx}']:
        with st.expander("💬 Sua opinião nos ajuda a melhorar"):
            feedback_opcao_app4 = st.radio(
                "Essa resposta foi útil?",
                ["👍 Sim", "👎 Não"],
                key=f"feedback_radio_consultor{sfx}_{st.session_state.get(f'last_prompt_consultor{sfx}', uuid.uuid4().hex)}"
            )
            comentario_app4 = st.text_area(
                "Comentário (opcional):",
                placeholder="Diga o que achou da resposta ou o que faltou.",
                key=f"feedback_comment_consultor{sfx}_{st.session_state.get(f'last_prompt_consultor{sfx}', uuid.uuid4().hex)}"
            )
            if st.button("Enviar Feedback", key=f"feedback_submit_consultor{sfx}_{st.session_state.get(f'last_prompt_consultor{sfx}', uuid.uuid4().hex)}"):
                salvar_feedback_rag(
                    pergunta=st.session_state.get(f'last_prompt_consultor{sfx}', "Pergunta não registrada"),
                    resposta=st.session_state.get(f'last_response_text_consultor{sfx}', ""),
                    feedback=feedback_opcao_app4,
                    comentario=comentario_app4,
                )
                st.success("Feedback enviado com sucesso. Obrigado!")
                if f'last_response_text_consultor{sfx}' in st.session_state:
                    del st.session_state[f'last_response_text_consultor{sfx}']
                if f'last_prompt_consultor{sfx}' in st.session_state:
                    del st.session_state[f'last_prompt_consultor{sfx}']
                st.rerun()

    # Limpar histórico
    if len(st.session_state[f'consultor_messages{sfx}']) > 1:
        if st.button("Limpar Histórico da Conversa", key=f"clear_chat_consultor{sfx}_button"):
            st.session_state[f'consultor_messages{sfx}'] = [
                {"role": "assistant", "content": "Olá! Sou LexConsult, seu assistente jurídico virtual. Como posso ajudar hoje?"}
            ]
            st.session_state[f'last_user_urls_context_consultor{sfx}'] = ""
            if f'last_response_text_consultor{sfx}' in st.session_state:
                del st.session_state[f'last_response_text_consultor{sfx}']
            if f'last_prompt_consultor{sfx}' in st.session_state:
                del st.session_state[f'last_prompt_consultor{sfx}']
            st.rerun()
