# app4.py (Consultor Jurídico lendo URLs da Sidebar Global - CORRIGIDO)
import streamlit as st
import os
import uuid # Para chaves únicas e feedback
from rag_utils import (
    salvar_feedback_rag,
    get_openai_client,
    get_azure_search_client,
    generate_consultor_response_with_rag
)
from chroma_utils import obter_contexto_relevante_de_url

# Carrega o prompt do consultor (mantido como no seu original)
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
    CONSULTOR_SYSTEM_PROMPT_BASE = "Você é LexConsult, um assistente jurídico virtual Sênior."


def consultor_juridico_interface():
    st.markdown("Faça perguntas sobre Direito, legislação ou teses jurídicas. Opcionalmente, utilize as URLs da barra lateral para enriquecer a consulta.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_azure_search_client()

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
    # Removido last_retrieved_chunks_details_consultor se não estiver sendo usado para exibição direta
    if f'last_prompt_consultor{sfx}' not in st.session_state:
        st.session_state[f'last_prompt_consultor{sfx}'] = ""
    if f'last_response_text_consultor{sfx}' not in st.session_state:
        st.session_state[f'last_response_text_consultor{sfx}'] = ""

    for message in st.session_state[f'consultor_messages{sfx}']:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            # Exibe o contexto da URL se existir na mensagem do assistente
            if message["role"] == "assistant" and message.get("user_urls_context_used"):
                 with st.expander("Detalhes do Contexto das URLs da Barra Lateral Utilizado:", expanded=False): # Título do expander ajustado
                    st.markdown(message["user_urls_context_used"], unsafe_allow_html=True)

    if prompt_usuario := st.chat_input("Digite sua pergunta jurídica..."):
        st.session_state[f'consultor_messages{sfx}'].append({"role": "user", "content": prompt_usuario})
        with st.chat_message("user"):
            st.markdown(prompt_usuario)

        st.session_state[f'geracao_em_andamento_consultor{sfx}'] = True
        st.session_state[f'last_user_urls_context_consultor{sfx}'] = "" # Reseta para a nova pergunta

        user_instruction_final_para_rag = prompt_usuario
        contexto_urls_agregado_para_prompt = ""
        contexto_urls_agregado_para_exibir = "" # Este conterá o HTML para o expander

        url1_sidebar = st.session_state.get('sidebar_url1', "")
        url2_sidebar = st.session_state.get('sidebar_url2', "")
        url3_sidebar = st.session_state.get('sidebar_url3', "")
        user_urls_from_sidebar = [url for url in [url1_sidebar, url2_sidebar, url3_sidebar] if url.strip()]

        with st.chat_message("assistant"):
            message_placeholder = st.empty() # Placeholder para a resposta do assistente

            # **MELHORIA A: Feedback visual imediato sobre URLs detectadas**
            if user_urls_from_sidebar:
                urls_detectadas_str = ", ".join([f"'{url}'" for url in user_urls_from_sidebar])
                message_placeholder.info(f"Consultando URLs da barra lateral: {urls_detectadas_str} para contexto adicional...")
            else:
                message_placeholder.info("Nenhuma URL da barra lateral fornecida. Prosseguindo com a consulta padrão...")


            if user_urls_from_sidebar:
                num_urls_para_consultar = len(user_urls_from_sidebar)
                spinner_message_urls = f"Processando {num_urls_para_consultar} URL(s) da barra lateral..."
                with st.spinner(spinner_message_urls): # Spinner para processamento de URLs
                    for i, url_item in enumerate(user_urls_from_sidebar, 1):
                        print(f"INFO APP4 (Consultor): Obtendo contexto Chroma da URL {i} (sidebar): {url_item} para a pergunta: '{prompt_usuario}'")
                        contexto_url_individual = obter_contexto_relevante_de_url(
                            url_item,
                            prompt_usuario,
                            top_k_chunks=2
                        )

                        # **MELHORIA B: Formatação consistente do contexto_urls_agregado_para_exibir**
                        if contexto_url_individual:
                            # chroma_utils já retorna uma string formatada que inclui "CONTEXTO DA URL"
                            # ou mensagens de erro/aviso também formatadas.
                            # Apenas precisamos garantir que algo seja adicionado se a URL foi processada.
                            contexto_urls_agregado_para_exibir += f"<b>Resultado para URL {i} ({url_item}):</b><br>{contexto_url_individual}<hr>"

                            # Adiciona ao prompt do LLM somente se não for uma mensagem de erro/aviso explícita de "Nenhum conteúdo" ou "Falha"
                            if "Nenhum conteúdo relevante encontrado nesta URL" not in contexto_url_individual and \
                               "Falha ao carregar ou processar o conteúdo da URL" not in contexto_url_individual and \
                               "Erro ao buscar informações na URL" not in contexto_url_individual:
                                contexto_urls_agregado_para_prompt += f"\n--- Contexto da URL {i} ({url_item}) (Conteúdo Útil) ---\n{contexto_url_individual}\n--- Fim do Contexto da URL {i} ---\n\n"
                                print(f"INFO APP4 (Consultor): Contexto útil da URL {i} (sidebar) adicionado ao prompt.")
                            else:
                                print(f"INFO APP4 (Consultor): URL {i} (sidebar) processada, mas sem conteúdo útil para o prompt do LLM ou houve erro.")
                        else: # Caso obter_contexto_relevante_de_url retorne string vazia ou None
                            contexto_urls_agregado_para_exibir += f"<b>Resultado para URL {i} ({url_item}):</b><br><i>Não foi possível obter informações desta URL.</i><hr>"
                            print(f"AVISO APP4 (Consultor): Não foi possível obter informações da URL {i} ({url_item}).")


                # Define o estado para o expander
                if contexto_urls_agregado_para_exibir:
                    st.session_state[f'last_user_urls_context_consultor{sfx}'] = contexto_urls_agregado_para_exibir
                else:
                    # Isso só aconteceria se user_urls_from_sidebar fosse true, mas o loop não adicionasse nada
                    # o que é improvável com a lógica acima. Mas por segurança:
                    st.session_state[f'last_user_urls_context_consultor{sfx}'] = "As URLs da barra lateral foram verificadas, mas nenhum detalhe de processamento para exibir."

            if contexto_urls_agregado_para_prompt:
                user_instruction_final_para_rag = (
                    f"Com base nos seguintes contextos extraídos de URLs fornecidas pelo usuário:\n"
                    f"{contexto_urls_agregado_para_prompt}"
                    f"Responda à pergunta do usuário abaixo. Se os contextos das URLs forem relevantes, utilize-os. Se não, responda com base no seu conhecimento geral e outras fontes disponíveis.\n\n"
                    f"Pergunta do Usuário: \"{prompt_usuario}\""
                )
                print(f"INFO APP4 (Consultor): Contexto das URLs da sidebar (se útil) adicionado ao prompt do LLM.")
            else:
                # Mantém a instrução original se nenhum contexto útil de URL foi encontrado para o prompt
                user_instruction_final_para_rag = prompt_usuario
                print(f"INFO APP4 (Consultor): Nenhuma URL forneceu contexto útil para o prompt do LLM, ou nenhuma URL foi fornecida.")


            # Limpa o placeholder do st.info e inicia o spinner principal
            message_placeholder.empty()
            with st.spinner("LexConsult está pensando com base em todas as fontes..."):
                assistant_response = generate_consultor_response_with_rag(
                    system_message_base=CONSULTOR_SYSTEM_PROMPT_BASE,
                    user_instruction=user_instruction_final_para_rag,
                    chat_history=st.session_state[f'consultor_messages{sfx}'][:-1], # Exclui a pergunta atual e a resposta pendente
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

            message_placeholder.markdown(response_text) # Exibe a resposta final do assistente

            assistant_message_data = {"role": "assistant", "content": response_text}
            # **MELHORIA B (Continuação): Condição para mostrar o expander**
            # Mostra o expander se URLs foram fornecidas e processadas,
            # independentemente se o contexto foi útil ou não para o prompt do LLM.
            # st.session_state[f'last_user_urls_context_consultor{sfx}'] já contém o HTML formatado
            # com os resultados do processamento de cada URL.
            if user_urls_from_sidebar and st.session_state.get(f'last_user_urls_context_consultor{sfx}'):
                assistant_message_data["user_urls_context_used"] = st.session_state[f'last_user_urls_context_consultor{sfx}']

            st.session_state[f'consultor_messages{sfx}'].append(assistant_message_data)

            st.session_state[f'last_prompt_consultor{sfx}'] = user_instruction_final_para_rag
            st.session_state[f'last_response_text_consultor{sfx}'] = response_text

        st.session_state[f'geracao_em_andamento_consultor{sfx}'] = False
        st.rerun()

    # Lógica de feedback e limpar histórico (mantida como no seu original)
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
                if f'last_response_text_consultor{sfx}' in st.session_state: del st.session_state[f'last_response_text_consultor{sfx}']
                if f'last_prompt_consultor{sfx}' in st.session_state: del st.session_state[f'last_prompt_consultor{sfx}']
                st.rerun()

    if len(st.session_state[f'consultor_messages{sfx}']) > 1: # Só mostra se houver mais que a mensagem inicial
        if st.button("Limpar Histórico da Conversa", key=f"clear_chat_consultor{sfx}_button"):
            st.session_state[f'consultor_messages{sfx}'] = [
                {"role": "assistant", "content": "Olá! Sou LexConsult, seu assistente jurídico virtual. Como posso ajudar hoje?"}
            ]
            st.session_state[f'last_user_urls_context_consultor{sfx}'] = ""
            if f'last_response_text_consultor{sfx}' in st.session_state: del st.session_state[f'last_response_text_consultor{sfx}']
            if f'last_prompt_consultor{sfx}' in st.session_state: del st.session_state[f'last_prompt_consultor{sfx}']
            st.rerun()