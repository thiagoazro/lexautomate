# app4.py
import streamlit as st
from rag_utils import generate_consultor_response_with_rag 

from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_consultor_response_with_rag # A nova função que você adicionou/adicionará ao rag_utils.py
)

# System Prompt para o Consultor Jurídico
CONSULTOR_SYSTEM_PROMPT = """
Você é LexConsult, um assistente jurídico virtual Sênior, especializado no Direito Brasileiro.
Sua base de conhecimento é vasta, incluindo legislação, jurisprudência e doutrina processual e material.
Seu objetivo é fornecer informações jurídicas claras, concisas e bem fundamentadas, respondendo às perguntas dos usuários.
Sempre que possível, cite as fontes (leis, artigos, ementas de jurisprudência) com base no CONTEXTO RECUPERADO da base de conhecimento que lhe será fornecido junto com a pergunta do usuário.
Mantenha um tom profissional, didático e prestativo.
Se uma pergunta for muito complexa, envolver análise de caso concreto com documentos específicos, ou pedir conselho legal direto (que você não pode fornecer),
sugira que o usuário procure um advogado ou utilize as outras funcionalidades da plataforma LexAutomate que permitem o upload de documentos para análises mais detalhadas.
Não invente informações. Se o contexto fornecido não for suficiente para responder ou se você não souber a resposta, admita isso honestamente.
Não responda perguntas que não sejam de natureza jurídica ou que não estejam relacionadas ao Direito Brasileiro.
Se a pergunta não for clara, peça esclarecimentos ao usuário.
Se o usuário fizer perguntas repetidas ou semelhantes, forneça uma resposta diferente ou mais detalhada, se possível.
Responda em Markdown.
"""

def consultor_juridico_interface():
    st.subheader("LexConsult: Seu Consultor Jurídico Virtual")
    st.markdown("Faça perguntas sobre Direito, legislação, jurisprudência ou teses jurídicas.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_azure_search_client()

    if not client_openai or not search_client:
        st.error("Falha ao inicializar os serviços de IA para o Consultor. Verifique as configurações.")
        st.stop()

    # Inicializar histórico do chat para o consultor
    if "consultor_messages" not in st.session_state:
        st.session_state.consultor_messages = [
            {"role": "assistant", "content": "Olá! Sou LexConsult, seu assistente jurídico virtual. Como posso ajudar hoje?"}
        ]

    # Exibir mensagens do chat
    for message in st.session_state.consultor_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Entrada do usuário via chat
    if prompt := st.chat_input("Digite sua pergunta jurídica..."):
        # Adicionar mensagem do usuário ao histórico e exibir
        st.session_state.consultor_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Gerar e exibir resposta do assistente
        with st.chat_message("assistant"):
            message_placeholder = st.empty() # Para streaming, se implementado depois
            with st.spinner("LexConsult está pensando..."):
                # Passa o histórico de chat para a função de geração
                assistant_response = generate_consultor_response_with_rag(
                    system_message=CONSULTOR_SYSTEM_PROMPT,
                    user_instruction=prompt,
                    chat_history=st.session_state.consultor_messages[:-1], # Envia o histórico ANTES da pergunta atual do usuário
                    search_client=search_client,
                    client_openai=client_openai,
                    top_k_chunks=3 # Ajuste conforme necessário para o chat
                )
            message_placeholder.markdown(assistant_response)
        st.session_state.consultor_messages.append({"role": "assistant", "content": assistant_response})
        st.rerun() # Garante que a interface atualize com a nova mensagem

    # Botão para limpar o histórico do chat
    if len(st.session_state.consultor_messages) > 1: # Mostra apenas se houver conversa
        if st.button("Limpar Histórico da Conversa", key="clear_consultor_chat"):
            st.session_state.consultor_messages = [
                {"role": "assistant", "content": "Olá! Sou LexConsult, seu assistente jurídico virtual. Como posso ajudar hoje?"}
            ]
            st.rerun()