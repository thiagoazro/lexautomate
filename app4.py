# app4.py (Consultor Jurídico)
import streamlit as st
import os
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_consultor_response_with_rag, 
    AZURE_OPENAI_DEPLOYMENT_LLM
)

# Carregar o prompt específico para o Consultor diretamente do arquivo
try:
    CONSULTOR_SYSTEM_PROMPT = open(os.path.join("prompts", "system_prompt_app4_consultor.md"), "r", encoding="utf-8").read()
except FileNotFoundError:
    error_message = "Erro: Arquivo 'prompts/system_prompt_app4_consultor.md' não encontrado. Verifique o caminho."
    print(error_message)
    st.error(error_message)
    CONSULTOR_SYSTEM_PROMPT = "Você é LexConsult, um assistente jurídico virtual Sênior." # Fallback
except Exception as e:
    error_message = f"Erro ao carregar 'prompts/system_prompt_app4_consultor.md': {e}"
    print(error_message)
    st.error(error_message)
    CONSULTOR_SYSTEM_PROMPT = "Você é LexConsult, um assistente jurídico virtual Sênior." # Fallback


def consultor_juridico_interface():
    st.subheader("LexConsult: Seu Consultor Jurídico Virtual")
    st.markdown("Faça perguntas sobre Direito, legislação, jurisprudência ou teses jurídicas.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_azure_search_client()

    if not client_openai or not search_client:
        st.error("Falha ao inicializar os serviços de IA para o Consultor. Verifique as configurações.")
        st.stop()

    if "consultor_messages" not in st.session_state:
        st.session_state.consultor_messages = [
            {"role": "assistant", "content": "Olá! Sou LexConsult, seu assistente jurídico virtual. Como posso ajudar hoje?"}
        ]
    if 'last_retrieved_chunks_details_consultor' not in st.session_state:
        st.session_state.last_retrieved_chunks_details_consultor = []


    for message in st.session_state.consultor_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Digite sua pergunta jurídica..."):
        st.session_state.consultor_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        st.session_state.last_retrieved_chunks_details_consultor = [] 

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            with st.spinner("LexConsult está pensando..."):
                assistant_response = generate_consultor_response_with_rag(
                    system_message=CONSULTOR_SYSTEM_PROMPT, 
                    user_instruction=prompt,
                    chat_history=st.session_state.consultor_messages[:-1],
                    search_client=search_client,
                    client_openai=client_openai,
                    # azure_openai_deployment já é o default em rag_utils para esta função
                    top_k_chunks=7, # <<-- AUMENTADO DE 5 PARA 7
                    use_semantic_search_in_consultor=True, 
                    enable_google_search=True, 
                    min_azure_results_for_google=1, # Se menos de 1 resultado interno, busca no Google
                    num_google_results_consultor=2
                )
                response_text = assistant_response

            message_placeholder.markdown(response_text)
        st.session_state.consultor_messages.append({"role": "assistant", "content": response_text})
        st.rerun()

    if len(st.session_state.consultor_messages) > 1:
        if st.button("Limpar Histórico da Conversa", key="clear_consultor_chat_app4"):
            st.session_state.consultor_messages = [
                {"role": "assistant", "content": "Olá! Sou LexConsult, seu assistente jurídico virtual. Como posso ajudar hoje?"}
            ]
            st.session_state.last_retrieved_chunks_details_consultor = []
            st.rerun()

    retrieved_chunks_display_consultor = st.session_state.get('last_retrieved_chunks_details_consultor', [])
    if retrieved_chunks_display_consultor:
        st.markdown("---")
        with st.expander("🔎 Detalhes dos Documentos Recuperados pelo RAG (para a última pergunta ao consultor)", expanded=False):
            for i, chunk_info in enumerate(retrieved_chunks_display_consultor):
                arquivo_origem = chunk_info.get('arquivo_origem', 'N/A')
                score = chunk_info.get('score', None)
                reranker_score = chunk_info.get('reranker_score', None)
                semantic_caption = chunk_info.get('semantic_caption', None)
                content_preview = chunk_info.get('content_preview', 'Conteúdo não disponível.')
                chunk_id = chunk_info.get('chunk_id', f"chunk_display_consultor_expander_app4_{i}")

                st.markdown(f"**Chunk {i+1} (Origem: `{arquivo_origem}`)**")
                score_text = f"{score:.4f}" if isinstance(score, (int, float)) else "N/A"
                reranker_text = f"{reranker_score:.4f}" if isinstance(reranker_score, (int, float)) else "N/A"
                details_md = f"> Score Busca: **{score_text}**"
                if reranker_score is not None and reranker_text != "N/A":
                    details_md += f" | Score Reclassificação: **{reranker_text}**"
                st.markdown(details_md)

                if semantic_caption:
                    st.markdown(f"> Caption Semântico: *{semantic_caption}*")
                st.text_area(
                    label=f"Conteúdo do Chunk {i+1} (preview):",
                    value=content_preview,
                    height=100,
                    disabled=True,
                    key=f"chunk_preview_consultor_expander_key_app4_{chunk_id}"
                )
                st.markdown("---")
