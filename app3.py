# app3.py (Análise de Cláusulas Contratuais lendo URLs da Sidebar)
import streamlit as st
import os
import uuid
import traceback
from rag_docintelligence import extrair_texto_documento
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_response_with_conditional_google_search,
    gerar_docx,
    AZURE_OPENAI_DEPLOYMENT_LLM,
    salvar_feedback_rag
)
# Importar utilitários Chroma
from chroma_utils import obter_contexto_relevante_de_url

# Carregar o prompt específico para este app
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file_path = os.path.join(current_dir, "..", "prompts", "system_prompt_app3_validacao.md")
    if not os.path.exists(prompt_file_path):
        prompt_file_path_alt = os.path.join(os.path.dirname(current_dir), "prompts", "system_prompt_app3_validacao.md")
        if os.path.exists(prompt_file_path_alt):
            prompt_file_path = prompt_file_path_alt
        else:
            prompt_file_path = os.path.join("prompts", "system_prompt_app3_validacao.md")
    SYSTEM_PROMPT_APP3_VALIDACAO = open(prompt_file_path, "r", encoding="utf-8").read()
    print(f"INFO APP3 (Validação): Prompt carregado de: {prompt_file_path}")
except FileNotFoundError:
    error_message = "Erro: Arquivo 'prompts/system_prompt_app3_validacao.md' não encontrado."
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP3_VALIDACAO = "Você é um assistente de IA para validar cláusulas."
except Exception as e:
    error_message = f"Erro ao carregar 'prompts/system_prompt_app3_validacao.md': {e}"
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP3_VALIDACAO = "Você é um assistente de IA."


def validacao_interface():
    # st.subheader("📑 Análise e Validação de Cláusulas Contratuais") # Título da tab
    st.markdown("Envie contratos, especifique a cláusula e, opcionalmente, utilize as URLs da barra lateral para enriquecer a análise.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_azure_search_client()
    if not client_openai or not search_client:
        st.error("Falha ao inicializar serviços de IA.")
        st.stop()

    uploaded_files = st.file_uploader(
        "1. Envie documentos com cláusulas a analisar (PDF, DOCX)",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        key="validacao_uploader_multi_app3_sidebar" # Chave única
    )

    # Sufixo para chaves de session_state desta aba
    sfx = "_app3_sidebar"
    if f'validacao_multi_texto_extraido{sfx}' not in st.session_state:
        st.session_state[f'validacao_multi_texto_extraido{sfx}'] = ""
    if f'validacao_rag_response{sfx}' not in st.session_state:
        st.session_state[f'validacao_rag_response{sfx}'] = ""
    if f'validacao_edited_response{sfx}' not in st.session_state:
        st.session_state[f'validacao_edited_response{sfx}'] = ""
    if f'validacao_final_version{sfx}' not in st.session_state:
        st.session_state[f'validacao_final_version{sfx}'] = None
    if f'geracao_em_andamento_validacao{sfx}' not in st.session_state:
        st.session_state[f'geracao_em_andamento_validacao{sfx}'] = False
    if f'last_retrieved_chunks_details_validacao{sfx}' not in st.session_state:
        st.session_state[f'last_retrieved_chunks_details_validacao{sfx}'] = []
    if f'last_user_urls_context_validacao{sfx}' not in st.session_state:
        st.session_state[f'last_user_urls_context_validacao{sfx}'] = ""
    if f'last_prompt_validacao{sfx}' not in st.session_state:
        st.session_state[f'last_prompt_validacao{sfx}'] = ""
    if f'last_response_text_validacao{sfx}' not in st.session_state:
        st.session_state[f'last_response_text_validacao{sfx}'] = ""

    if not st.session_state[f'geracao_em_andamento_validacao{sfx}']:
        st.session_state[f'last_retrieved_chunks_details_validacao{sfx}'] = []

    if uploaded_files and not st.session_state[f'validacao_multi_texto_extraido{sfx}']:
        textos = []
        st.session_state[f'geracao_em_andamento_validacao{sfx}'] = True
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_path = f"temp_validacao{sfx}_{uuid.uuid4().hex}{ext}"
            try:
                with open(temp_path, "wb") as f:
                    f.write(file.getvalue())
                with st.spinner(f"Extraindo texto de {file.name}..."):
                    texto = extrair_texto_documento(temp_path, ext)
                if texto:
                    textos.append(f"---\n**Documento: {file.name}**\n\n{texto}")
                else:
                    st.warning(f"Não foi possível extrair texto de {file.name}.")
            except Exception as e:
                st.error(f"Erro ao processar {file.name}: {e}")
                traceback.print_exc()
            finally:
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except Exception as e_rm: print(f"Aviso: Falha ao remover arquivo temporário {temp_path}: {e_rm}")
        
        if textos:
            st.session_state[f'validacao_multi_texto_extraido{sfx}'] = "\n\n".join(textos)
            st.success("Textos extraídos com sucesso.")
        else:
            st.session_state[f'validacao_multi_texto_extraido{sfx}'] = ""
            st.warning("Nenhum texto pôde ser extraído dos arquivos.")
        st.session_state[f'geracao_em_andamento_validacao{sfx}'] = False
        st.rerun()

    if True:
        if st.session_state[f'validacao_multi_texto_extraido{sfx}']:
            with st.expander("Ver Texto Extraído Consolidado", expanded=False):
                st.text_area(
                    "Texto Extraído:", 
                    st.session_state[f'validacao_multi_texto_extraido{sfx}'], 
                    height=200, 
                    disabled=True, 
                    key=f"validacao_texto_view{sfx}"
                )

        st.markdown("---")
        st.markdown("### 2. Instruções e URLs para Contexto Adicional")
        prompt_validacao_usuario = st.text_area(
            "Especifique a cláusula ou ponto para análise/validação:",
            placeholder="Ex: Analise a Cláusula 5 (Multa Contratual) e verifique sua conformidade com o CDC e jurisprudência recente.",
            height=100,
            key=f"prompt_validacao_input{sfx}"
        )

        # Lê as URLs da sidebar
        url1_sidebar = st.session_state.get('sidebar_url1', "")
        url2_sidebar = st.session_state.get('sidebar_url2', "")
        url3_sidebar = st.session_state.get('sidebar_url3', "")
        user_urls_from_sidebar = [url for url in [url1_sidebar, url2_sidebar, url3_sidebar] if url.strip()]

        if user_urls_from_sidebar:
            st.info(f"Utilizando {len(user_urls_from_sidebar)} URL(s) de contexto da barra lateral para esta análise.")

        enable_google_search_validacao = st.checkbox("Habilitar busca complementar na Web (Google)?", value=True, key=f"validacao_enable_google_search{sfx}_checkbox")

        if st.button("Analisar/Validar Cláusulas", key=f"validacao_gerar_btn{sfx}_button"):
            if not prompt_validacao_usuario.strip():
                st.warning("Por favor, digite a instrução para a análise.")
            elif not st.session_state[f'validacao_multi_texto_extraido{sfx}'].strip() and not user_urls_from_sidebar:
                 st.warning("Forneça documentos ou URLs (na barra lateral) para contextualizar a análise.")
            else:
                st.session_state[f'geracao_em_andamento_validacao{sfx}'] = True
                st.session_state[f'last_retrieved_chunks_details_validacao{sfx}'] = []
                st.session_state[f'last_user_urls_context_validacao{sfx}'] = ""

                prompt_base_para_contexto_urls = prompt_validacao_usuario.strip()
                if not prompt_base_para_contexto_urls and st.session_state[f'validacao_multi_texto_extraido{sfx}']:
                    preview_texto_doc = st.session_state[f'validacao_multi_texto_extraido{sfx}'][:500]
                    prompt_base_para_contexto_urls = f"Analisar cláusulas e encontrar jurisprudência sobre os temas em: {preview_texto_doc}..."
                elif not prompt_base_para_contexto_urls:
                     prompt_base_para_contexto_urls = "Análise de cláusula contratual e jurisprudência relevante."

                contexto_urls_agregado_para_prompt = ""
                contexto_urls_agregado_para_exibir = ""

                if user_urls_from_sidebar:
                    num_urls_para_consultar = len(user_urls_from_sidebar)
                    spinner_message_urls = f"Consultando {num_urls_para_consultar} URL(s) da barra lateral..."
                    with st.spinner(spinner_message_urls):
                        for i, url_item in enumerate(user_urls_from_sidebar, 1):
                            print(f"INFO APP3 (Validação): Obtendo contexto Chroma da URL {i} (sidebar): {url_item} para a consulta: '{prompt_base_para_contexto_urls}'")
                            contexto_url_individual = obter_contexto_relevante_de_url(
                                url_item,
                                prompt_base_para_contexto_urls,
                                top_k_chunks=2 
                            )
                            if contexto_url_individual and "Nenhum conteúdo relevante" not in contexto_url_individual and "Falha ao carregar" not in contexto_url_individual:
                                contexto_urls_agregado_para_prompt += f"\n--- Contexto da URL {i} ({url_item}) ---\n{contexto_url_individual}\n--- Fim do Contexto da URL {i} ---\n\n"
                                contexto_urls_agregado_para_exibir += f"<b>Contexto da URL {i} ({url_item}):</b><br>{contexto_url_individual}<hr>"
                                print(f"INFO APP3 (Validação): Contexto da URL {i} (sidebar) adicionado.")
                            else:
                                aviso_url = f"<i>Nenhum contexto útil obtido da URL {i} ({url_item}) da barra lateral.</i><br>"
                                contexto_urls_agregado_para_exibir += aviso_url
                                print(f"AVISO APP3 (Validação): {aviso_url}")
                
                st.session_state[f'last_user_urls_context_validacao{sfx}'] = contexto_urls_agregado_para_exibir if contexto_urls_agregado_para_exibir else "Nenhuma URL fornecida na barra lateral ou nenhum contexto relevante extraído."
                
                user_instruction_para_llm = prompt_validacao_usuario.strip()
                
                if contexto_urls_agregado_para_prompt:
                    user_instruction_para_llm = (
                        f"{contexto_urls_agregado_para_prompt}"
                        f"Considerando os contextos acima extraídos das URLs fornecidas pelo usuário na barra lateral, "
                        f"e o(s) documento(s) também fornecido(s) (se houver), siga a instrução abaixo:\n\n"
                        f"Instrução do Usuário para Análise/Validação: \"{user_instruction_para_llm}\""
                    )
                
                with st.spinner("Analisando cláusulas com todas as fontes..."):
                    try:
                        resposta = generate_response_with_conditional_google_search(
                            system_message_base=SYSTEM_PROMPT_APP3_VALIDACAO,
                            user_instruction=user_instruction_para_llm,
                            context_document_text=st.session_state[f'validacao_multi_texto_extraido{sfx}'],
                            search_client=search_client,
                            client_openai=client_openai,
                            azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,
                            azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM,
                            top_k_initial_search_azure=7,
                            top_k_rerank_azure=3,
                            use_semantic_search_azure=True,
                            enable_google_search_trigger=enable_google_search_validacao,
                            min_azure_results_for_google_trigger=1,
                            num_google_results=2,
                            temperature=0.1,
                            max_tokens=3500
                        )
                        
                        resposta_str = str(resposta).strip() if resposta is not None else ""
                        st.session_state[f'validacao_rag_response{sfx}'] = resposta_str
                        st.session_state[f'validacao_edited_response{sfx}'] = resposta_str
                        st.session_state[f'validacao_final_version{sfx}'] = None
                        st.session_state[f'last_retrieved_chunks_details_validacao{sfx}'] = st.session_state.get('last_retrieved_chunks_details', [])
                        
                        st.session_state[f'last_prompt_validacao{sfx}'] = user_instruction_para_llm
                        st.session_state[f'last_response_text_validacao{sfx}'] = resposta_str

                        st.success("Rascunho da análise gerado. Revise e edite abaixo.")
                    except Exception as e:
                        st.error(f"Ocorreu um erro ao realizar a análise: {e}")
                        st.session_state[f'validacao_rag_response{sfx}'] = ""
                        st.session_state[f'validacao_edited_response{sfx}'] = ""
                        traceback.print_exc()
                    finally:
                        st.session_state[f'geracao_em_andamento_validacao{sfx}'] = False
                        st.rerun()

    texto_preview_validacao = st.session_state.get(f'validacao_edited_response{sfx}', "").strip()
    if texto_preview_validacao:
        st.markdown("---")
        st.markdown("### 3. Revisão, Edição e Exportação")

        if st.session_state.get(f'last_user_urls_context_validacao{sfx}') and ("Contexto da URL" in st.session_state.get(f'last_user_urls_context_validacao{sfx}')):
            with st.expander("Contexto das URLs da Barra Lateral Utilizado", expanded=False):
                st.markdown(st.session_state[f'last_user_urls_context_validacao{sfx}'], unsafe_allow_html=True)

        st.markdown("#### Pré-visualização da Análise Formatada:")
        with st.container(border=True):
            st.markdown(texto_preview_validacao, unsafe_allow_html=True)

        edited_text_validacao = st.text_area(
            "Edite a análise gerada (use `**texto**` para negrito):",
            value=texto_preview_validacao,
            height=400,
            key=f"validacao_editor_multi{sfx}"
        )

        if edited_text_validacao != st.session_state.get(f'validacao_edited_response{sfx}', ""):
            st.session_state[f'validacao_edited_response{sfx}'] = edited_text_validacao
            st.session_state[f'validacao_final_version{sfx}'] = None

        if st.button("Salvar Versão Editada", key=f"validacao_salvar_btn{sfx}_button"):
            st.session_state[f'validacao_final_version{sfx}'] = st.session_state[f'validacao_edited_response{sfx}']
            st.success("Versão editada salva.")

        if st.session_state[f'validacao_final_version{sfx}'] is not None:
            st.markdown("**Exportar Versão Salva:**")
            try:
                docx_data = gerar_docx(st.session_state[f'validacao_final_version{sfx}'])
                st.download_button(
                    label="Exportar para DOCX",
                    data=docx_data,
                    file_name="LexAutomate_Analise_Clausulas_Juris.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"validacao_export_docx_btn{sfx}_button"
                )
            except Exception as e:
                st.error(f"Erro ao gerar DOCX: {e}")
                traceback.print_exc()
    
    if f'last_response_text_validacao{sfx}' in st.session_state and st.session_state[f'last_response_text_validacao{sfx}']:
        with st.expander("💬 Sua opinião nos ajuda a melhorar esta funcionalidade de análise"):
            feedback_opcao_app3 = st.radio(
                "Esta análise gerada foi útil?",
                ["👍 Sim", "👎 Não"],
                key=f"feedback_radio_validacao{sfx}_{st.session_state.get(f'last_prompt_validacao{sfx}', uuid.uuid4().hex)}"
            )
            comentario_app3 = st.text_area(
                "Comentário sobre a análise (opcional):",
                placeholder="Diga o que achou da análise ou o que faltou.",
                key=f"feedback_comment_validacao{sfx}_{st.session_state.get(f'last_prompt_validacao{sfx}', uuid.uuid4().hex)}"
            )
            if st.button("Enviar Feedback da Análise", key=f"feedback_submit_validacao{sfx}_{st.session_state.get(f'last_prompt_validacao{sfx}', uuid.uuid4().hex)}"):
                salvar_feedback_rag(
                    pergunta=st.session_state.get(f'last_prompt_validacao{sfx}', "Instrução não registrada"),
                    resposta=st.session_state.get(f'last_response_text_validacao{sfx}', ""),
                    feedback=feedback_opcao_app3,
                    comentario=comentario_app3,
                )
                st.success("Feedback sobre a análise enviado com sucesso. Obrigado!")
                if f'last_response_text_validacao{sfx}' in st.session_state: del st.session_state[f'last_response_text_validacao{sfx}']
                if f'last_prompt_validacao{sfx}' in st.session_state: del st.session_state[f'last_prompt_validacao{sfx}']
                st.rerun()

    retrieved_chunks_display_validacao = st.session_state.get(f'last_retrieved_chunks_details_validacao{sfx}', [])
    if retrieved_chunks_display_validacao:
        st.markdown("---")
        with st.expander("🔎 Detalhes dos Documentos Recuperados pelo RAG (Azure AI Search)", expanded=False):
            for i, chunk_info in enumerate(retrieved_chunks_display_validacao):
                arquivo_origem = chunk_info.get('arquivo_origem', 'N/A')
                score = chunk_info.get('score', None)
                reranker_score = chunk_info.get('reranker_score', None)
                semantic_caption = chunk_info.get('semantic_caption', None)
                content_preview = chunk_info.get('content_preview', 'Conteúdo não disponível.')
                chunk_id = chunk_info.get('chunk_id', f"chunk_display_validacao_expander{sfx}_key_{i}")

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
                    key=f"chunk_preview_validacao_expander{sfx}_unique_key_{chunk_id}"
                )
                st.markdown("---")

# if __name__ == "__main__":
#     if 'main_script_path' not in st.session_state:
#         st.session_state.main_script_path = os.path.abspath(__file__)
#     validacao_interface()
