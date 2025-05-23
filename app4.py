# app4.py (Consultor Jurídico)
import streamlit as st
import os
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_consultor_response_with_rag, 
    AZURE_OPENAI_DEPLOYMENT_LLM # Mantido, se usado diretamente em app4.py, ou já é default em rag_utils
)

# Carregar o prompt específico para o Consultor diretamente do arquivo
try:
    # Tenta construir o caminho relativo ao diretório do script app4.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file_path = os.path.join(current_dir, "..", "prompts", "system_prompt_app4_consultor.md")

    # Fallback se a estrutura de pastas for diferente (ex: app4.py na raiz com prompts/)
    if not os.path.exists(prompt_file_path):
        prompt_file_path = os.path.join("prompts", "system_prompt_app4_consultor.md")

    CONSULTOR_SYSTEM_PROMPT_BASE = open(prompt_file_path, "r", encoding="utf-8").read()
    print(f"INFO APP4: Prompt do consultor carregado de: {prompt_file_path}")
except FileNotFoundError:
    error_message = f"Erro APP4: Arquivo 'system_prompt_app4_consultor.md' não encontrado nos caminhos verificados. Verifique o caminho. CWD: {os.getcwd()}"
    print(error_message)
    st.error(error_message)
    CONSULTOR_SYSTEM_PROMPT_BASE = "Você é LexConsult, um assistente jurídico virtual Sênior." # Fallback
except Exception as e:
    error_message = f"Erro APP4: Erro ao carregar 'system_prompt_app4_consultor.md': {e}"
    print(error_message)
    st.error(error_message)
    CONSULTOR_SYSTEM_PROMPT_BASE = "Você é LexConsult, um assistente jurídico virtual Sênior." # Fallback


def consultor_juridico_interface():
    st.subheader("LexConsult: Seu Consultor Jurídico Virtual")
    st.markdown("Faça perguntas sobre Direito, legislação, jurisprudência ou teses jurídicas.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_azure_search_client() # Usa o índice padrão definido em rag_utils

    if not client_openai or not search_client:
        st.error("Falha ao inicializar os serviços de IA para o Consultor. Verifique as configurações e os logs do console.")
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
        if 'last_retrieved_chunks_details_azure_raw' in st.session_state: # Limpa raw também
            st.session_state.last_retrieved_chunks_details_azure_raw = []


        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            with st.spinner("LexConsult está pensando e pesquisando..."):
                # Chamada CORRIGIDA para generate_consultor_response_with_rag
                assistant_response = generate_consultor_response_with_rag(
                    system_message_base=CONSULTOR_SYSTEM_PROMPT_BASE, # Nome do argumento corrigido
                    user_instruction=prompt,
                    chat_history=st.session_state.consultor_messages[:-1], # Passa o histórico sem a última msg do user
                    search_client=search_client,
                    client_openai=client_openai,
                    # azure_openai_deployment_llm e azure_openai_deployment_expansion usam os defaults de rag_utils
                    top_k_initial_chunks_consultor=15, # Ex: Buscar 15 chunks inicialmente
                    top_k_rerank_consultor=7,          # Ex: Manter os 7 melhores após reranking
                    use_semantic_search_in_consultor=True, 
                    enable_google_search_trigger_consultor=True, # Nome do argumento corrigido
                    min_azure_results_for_google_trigger_consultor=1, # Nome do argumento corrigido
                    num_google_results_consultor=2,
                    use_reranker_consultor=True # Novo argumento para habilitar/desabilitar reranking
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
            if 'last_retrieved_chunks_details_azure_raw' in st.session_state:
                st.session_state.last_retrieved_chunks_details_azure_raw = []
            st.rerun()

    # Exibição dos chunks recuperados (usando os chunks finais após reranking)
    retrieved_chunks_display_consultor = st.session_state.get('last_retrieved_chunks_details_consultor', [])
    if retrieved_chunks_display_consultor:
        st.markdown("---")
        with st.expander("🔎 Detalhes dos Documentos Recuperados pelo RAG (Consultor - Pós-Reranking)", expanded=False):
            for i, chunk_info in enumerate(retrieved_chunks_display_consultor):
                arquivo_origem = chunk_info.get('arquivo_origem', 'N/A')
                score_azure_original = chunk_info.get('score', None) # Score original da busca Azure
                reranker_score_azure_semantic = chunk_info.get('reranker_score', None) # Score semântico do Azure
                reranker_score_cross_encoder = chunk_info.get('rerank_score_cross_encoder', None) # Score do CrossEncoder
                semantic_caption_text = chunk_info.get('semantic_caption', None)
                content_preview = chunk_info.get('content_preview', 'Conteúdo não disponível.')
                chunk_id = chunk_info.get('chunk_id', f"chunk_display_consultor_expander_app4_{i}")

                st.markdown(f"**Chunk {i+1} (Origem: `{arquivo_origem}`)**")
                
                scores_parts = []
                if reranker_score_cross_encoder is not None:
                    scores_parts.append(f"Score Reranker: **{reranker_score_cross_encoder:.4f}** (Rank: {i+1})")
                if score_azure_original is not None:
                    scores_parts.append(f"Score Busca Inicial: {score_azure_original:.4f}")
                if reranker_score_azure_semantic is not None:
                     scores_parts.append(f"Score Semântico Azure: {reranker_score_azure_semantic:.4f}")
                
                if scores_parts:
                    st.markdown("> " + " | ".join(scores_parts))

                if semantic_caption_text:
                    st.markdown(f"> Destaque Semântico: *{semantic_caption_text}*")
                
                st.text_area(
                    label=f"Conteúdo do Chunk {i+1} (preview):",
                    value=content_preview,
                    height=100,
                    disabled=True,
                    key=f"chunk_preview_consultor_expander_key_app4_{chunk_id}"
                )
                st.markdown("---")
