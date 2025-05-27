# app4.py (Consultor Jurídico)
import streamlit as st
import os
import uuid
from rag_utils import (
    salvar_feedback_rag,
    get_openai_client,
    get_azure_search_client,
    generate_consultor_response_with_rag
)

# Carrega o prompt do consultor
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file_path = os.path.join(current_dir, "..", "prompts", "system_prompt_app4_consultor.md")
    if not os.path.exists(prompt_file_path):
        prompt_file_path = os.path.join("prompts", "system_prompt_app4_consultor.md")
    CONSULTOR_SYSTEM_PROMPT_BASE = open(prompt_file_path, "r", encoding="utf-8").read()
    print(f"INFO APP4: Prompt carregado de: {prompt_file_path}")
except Exception as e:
    st.error(f"Erro ao carregar o prompt: {e}")
    CONSULTOR_SYSTEM_PROMPT_BASE = "Você é LexConsult, um assistente jurídico virtual Sênior."

def consultor_juridico_interface():
    st.subheader("LexConsult: Seu Consultor Jurídico Virtual")
    st.markdown("Faça perguntas sobre Direito, legislação, jurisprudência ou teses jurídicas.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_azure_search_client()

    if not client_openai or not search_client:
        st.error("Erro ao inicializar serviços da IA.")
        st.stop()

    if "consultor_messages" not in st.session_state:
        st.session_state.consultor_messages = [
            {"role": "assistant", "content": "Olá! Sou LexConsult, seu assistente jurídico virtual. Como posso ajudar hoje?"}
        ]
    if "last_retrieved_chunks_details_consultor" not in st.session_state:
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
                    system_message_base=CONSULTOR_SYSTEM_PROMPT_BASE,
                    user_instruction=prompt,
                    chat_history=st.session_state.consultor_messages[:-1],
                    search_client=search_client,
                    client_openai=client_openai,
                    top_k_initial_chunks_consultor=15,
                    top_k_rerank_consultor=7,
                    use_semantic_search_in_consultor=True,
                    enable_google_search_trigger_consultor=True,
                    min_azure_results_for_google_trigger_consultor=1,
                    num_google_results_consultor=2,
                    use_reranker_consultor=True
                )
                response_text = assistant_response
            message_placeholder.markdown(response_text)
            st.session_state.consultor_messages.append({"role": "assistant", "content": response_text})

            # Armazena para feedback
            st.session_state.last_response_text = response_text
            st.session_state.last_prompt = prompt

        st.rerun()

    # Formulário de feedback pós-resposta
    if "last_response_text" in st.session_state:
        with st.expander("💬 Sua opinião nos ajuda a melhorar"):
            feedback_opcao = st.radio("Essa resposta foi útil?", ["👍 Sim", "👎 Não"], key=f"feedback_radio_{uuid.uuid4().hex}")
            comentario = st.text_area("Comentário (opcional):", placeholder="Diga o que achou da resposta ou o que faltou.")
            if st.button("Enviar Feedback"):
                salvar_feedback_rag(
                    pergunta=st.session_state.get("last_prompt", ""),
                    resposta=st.session_state.get("last_response_text", ""),
                    feedback=feedback_opcao,
                    comentario=comentario
                )
                st.success("Feedback enviado com sucesso. Obrigado!")
                del st.session_state["last_response_text"]
                del st.session_state["last_prompt"]

    if len(st.session_state.consultor_messages) > 1:
        if st.button("Limpar Histórico da Conversa"):
            st.session_state.consultor_messages = [
                {"role": "assistant", "content": "Olá! Sou LexConsult, seu assistente jurídico virtual. Como posso ajudar hoje?"}
            ]
            st.session_state.last_retrieved_chunks_details_consultor = []
            st.rerun()
