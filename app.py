# app.py (Resumo de Documento - sem consulta a URLs externas)
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
# A importação de chroma_utils não é mais necessária para esta versão do app.py
# from chroma_utils import obter_contexto_relevante_de_url

# Carregar o prompt específico para este app diretamente do arquivo
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file_path = os.path.join(current_dir, "..", "prompts", "system_prompt_app_resumo.md")
    if not os.path.exists(prompt_file_path):
        prompt_file_path_alt = os.path.join(os.path.dirname(current_dir), "prompts", "system_prompt_app_resumo.md")
        if os.path.exists(prompt_file_path_alt):
            prompt_file_path = prompt_file_path_alt
        else:
            prompt_file_path = os.path.join("prompts", "system_prompt_app_resumo.md")
    SYSTEM_PROMPT_APP_RESUMO = open(prompt_file_path, "r", encoding="utf-8").read()
    print(f"INFO APP (Resumo): Prompt carregado de: {prompt_file_path}")
except FileNotFoundError:
    error_message = "Erro: Arquivo 'prompts/system_prompt_app_resumo.md' não encontrado. Verifique o caminho."
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP_RESUMO = "Você é um assistente de IA. Por favor, seja breve e direto." # Fallback
except Exception as e:
    error_message = f"Erro ao carregar 'prompts/system_prompt_app_resumo.md': {e}"
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP_RESUMO = "Você é um assistente de IA." # Fallback genérico

def resumo_interface():
    st.subheader("📄 Resumo de Documento Jurídico")
    st.markdown("Envie documentos e forneça instruções para gerar um resumo conciso e informativo.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_azure_search_client()
    if not client_openai or not search_client:
        st.error("Falha ao inicializar serviços de IA. Verifique as configurações e logs.")
        st.stop()

    uploaded_files = st.file_uploader(
        "1. Envie um ou mais documentos (PDF, DOCX)",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        key="resumo_multi_uploader_app_no_url" # Chave atualizada para evitar conflitos
    )

    # Inicialização de session_state específica para esta aba/app
    if 'resumo_multi_texto_extraido_app_no_url' not in st.session_state:
        st.session_state.resumo_multi_texto_extraido_app_no_url = ""
    if 'resumo_rag_response_app_no_url' not in st.session_state:
        st.session_state.resumo_rag_response_app_no_url = ""
    if 'resumo_edited_response_app_no_url' not in st.session_state:
        st.session_state.resumo_edited_response_app_no_url = ""
    if 'resumo_final_version_app_no_url' not in st.session_state:
        st.session_state.resumo_final_version_app_no_url = None
    if 'geracao_em_andamento_resumo_app_no_url' not in st.session_state:
        st.session_state.geracao_em_andamento_resumo_app_no_url = False
    if 'last_retrieved_chunks_details_resumo_app_no_url' not in st.session_state:
        st.session_state.last_retrieved_chunks_details_resumo_app_no_url = []
    # Não precisamos mais de 'last_user_urls_context_resumo_app'
    if 'last_prompt_resumo_app_no_url' not in st.session_state:
        st.session_state.last_prompt_resumo_app_no_url = ""
    if 'last_response_text_resumo_app_no_url' not in st.session_state:
        st.session_state.last_response_text_resumo_app_no_url = ""


    if not st.session_state.geracao_em_andamento_resumo_app_no_url:
         st.session_state.last_retrieved_chunks_details_resumo_app_no_url = []

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
                    st.warning(f"Não foi possível extrair texto de {file.name}.")
            except Exception as e:
                st.error(f"Erro ao processar {file.name}: {e}")
                traceback.print_exc()
            finally:
                if os.path.exists(temp_file_path):
                    try: os.remove(temp_file_path)
                    except Exception as e_rm: print(f"Aviso: Falha ao remover arquivo temporário {temp_file_path}: {e_rm}")
        
        if textos:
            st.session_state.resumo_multi_texto_extraido_app_no_url = "\n\n".join(textos)
            st.success("Textos extraídos com sucesso.")
        else:
            st.session_state.resumo_multi_texto_extraido_app_no_url = "" 
            st.warning("Nenhum texto pôde ser extraído dos arquivos.")
        st.session_state.geracao_em_andamento_resumo_app_no_url = False
        st.rerun()

    if True: 
        if st.session_state.resumo_multi_texto_extraido_app_no_url:
            with st.expander("Ver Texto Extraído Consolidado", expanded=False):
                st.text_area(
                    "Texto Extraído:", 
                    st.session_state.resumo_multi_texto_extraido_app_no_url, 
                    height=200, 
                    disabled=True, 
                    key="resumo_texto_extraido_display_app_no_url"
                )

        st.markdown("---")
        st.markdown("### 2. Instruções para o Resumo")
        
        prompt_resumo_usuario = st.text_area (
            "Direcione o resumo (opcional - Deixe em branco para resumo padrão):",
            placeholder=(
                "Ex: Gere um resumo da cláusula de penalidades.\n"
                "Ex: Para cada contrato anexado, gere um resumo com o nome das partes e as obrigações principais."
            ),
            height=100,
            key="prompt_resumo_input_app_no_url"
        )

        # REMOVIDOS OS CAMPOS DE URL
        # st.markdown("Cole até 3 URLs de páginas de jurisprudência ou artigos relevantes para auxiliar na tarefa:")
        # url_placeholder = "URL de site de tribunal com pesquisa relevante ao tema"
        # user_url1_resumo = st.text_input("URL 1 (Opcional):", placeholder=url_placeholder, key="resumo_url1_app")
        # user_url2_resumo = st.text_input("URL 2 (Opcional):", placeholder=url_placeholder, key="resumo_url2_app")
        # user_url3_resumo = st.text_input("URL 3 (Opcional):", placeholder=url_placeholder, key="resumo_url3_app")
        # user_urls_resumo = [url for url in [user_url1_resumo, user_url2_resumo, user_url3_resumo] if url.strip()]

        enable_google_search_resumo = st.checkbox("Habilitar busca complementar na Web (Google) para este resumo?", value=True, key="resumo_enable_google_search_app_no_url_checkbox")

        if st.button("Gerar Resumo com RAG", key="resumo_gerar_btn_main_app_no_url_button"):
            if not st.session_state.resumo_multi_texto_extraido_app_no_url.strip() and not prompt_resumo_usuario.strip():
                st.warning("Forneça documentos ou instruções detalhadas para a IA.")
            else:
                st.session_state.geracao_em_andamento_resumo_app_no_url = True
                st.session_state.last_retrieved_chunks_details_resumo_app_no_url = []
                # Não há mais contexto de URL do usuário para limpar ou usar

                # A instrução para o LLM é simplesmente a instrução do usuário ou um padrão
                user_instruction_para_llm_resumo = prompt_resumo_usuario.strip() if prompt_resumo_usuario.strip() else "Gerar um resumo padrão do documento, destacando os pontos chave."
                
                with st.spinner("LexAutomate está resumindo... Por favor, aguarde."):
                    try:
                        resposta = generate_response_with_conditional_google_search(
                            system_message_base=SYSTEM_PROMPT_APP_RESUMO,
                            user_instruction=user_instruction_para_llm_resumo, # Instrução direta
                            context_document_text=st.session_state.resumo_multi_texto_extraido_app_no_url, # Texto dos DOCs/PDFs
                            search_client=search_client,
                            client_openai=client_openai,
                            azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,
                            azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM,
                            top_k_initial_search_azure=7,
                            top_k_rerank_azure=3,
                            use_semantic_search_azure=True,
                            enable_google_search_trigger=enable_google_search_resumo,
                            min_azure_results_for_google_trigger=2, 
                            num_google_results=3,
                            temperature=0.1,
                            max_tokens=3500
                        )
                        
                        resposta_str = str(resposta).strip() if resposta is not None else ""
                        st.session_state.resumo_rag_response_app_no_url = resposta_str
                        st.session_state.resumo_edited_response_app_no_url = resposta_str 
                        st.session_state.resumo_final_version_app_no_url = None
                        st.session_state.last_retrieved_chunks_details_resumo_app_no_url = st.session_state.get('last_retrieved_chunks_details', [])
                        
                        st.session_state.last_prompt_resumo_app_no_url = user_instruction_para_llm_resumo
                        st.session_state.last_response_text_resumo_app_no_url = resposta_str

                        st.success("Rascunho do resumo gerado com sucesso!")
                    except Exception as e:
                        st.error(f"Ocorreu um erro durante a geração do resumo: {e}")
                        st.session_state.resumo_rag_response_app_no_url = ""
                        st.session_state.resumo_edited_response_app_no_url = ""
                        print(f"DEBUG APP (Resumo): Erro na geração do resumo: {e}")
                        traceback.print_exc()
                    finally:
                        st.session_state.geracao_em_andamento_resumo_app_no_url = False
                        st.rerun() 

    texto_preview_resumo = st.session_state.get('resumo_edited_response_app_no_url', "")
    if not isinstance(texto_preview_resumo, str):
        texto_preview_resumo = str(texto_preview_resumo)
    texto_preview_resumo = texto_preview_resumo.strip()

    if texto_preview_resumo:
        st.markdown("---")
        st.markdown("### 3. Revisão, Edição e Exportação")

        # REMOVIDA A EXIBIÇÃO DO CONTEXTO DAS URLS
        # if st.session_state.get('last_user_urls_context_resumo_app') and ("Contexto da URL" in st.session_state.last_user_urls_context_resumo_app):
        #     with st.expander("Contexto das URLs Fornecidas Utilizado", expanded=False):
        #         st.markdown(st.session_state.last_user_urls_context_resumo_app, unsafe_allow_html=True)
        
        st.markdown("#### Pré-visualização do Resumo:")
        with st.container(border=True):
            st.markdown(texto_preview_resumo, unsafe_allow_html=True)

        st.markdown("---")
        texto_editado_resumo = st.text_area(
            "Edite o resumo gerado (Markdown):",
            value=texto_preview_resumo,
            height=600,
            key="resumo_editor_area_app_no_url_key"
        )

        if texto_editado_resumo != st.session_state.get('resumo_edited_response_app_no_url', ""):
            st.session_state.resumo_edited_response_app_no_url = texto_editado_resumo
            st.session_state.resumo_final_version_app_no_url = None

        col_btn_save_resumo, col_btn_download_resumo = st.columns(2)
        with col_btn_save_resumo:
            if st.button("Salvar Versão Editada do Resumo", key="resumo_save_edited_btn_app_no_url_key"):
                st.session_state.resumo_final_version_app_no_url = st.session_state.resumo_edited_response_app_no_url
                st.success("Versão do resumo salva.")

        if st.session_state.resumo_final_version_app_no_url is not None:
            with col_btn_download_resumo:
                try:
                    docx_data = gerar_docx(st.session_state.resumo_final_version_app_no_url)
                    st.download_button(
                        label="Baixar Resumo em DOCX",
                        data=docx_data,
                        file_name="LexAutomate_Resumo.docx", # Nome de arquivo simplificado
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="resumo_download_docx_btn_app_no_url_key"
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar DOCX para o resumo: {e}")
                    print(f"DEBUG APP (Resumo): Erro ao gerar DOCX para resumo: {e}")
                    traceback.print_exc()
    
    if "last_response_text_resumo_app_no_url" in st.session_state and st.session_state.last_response_text_resumo_app_no_url:
        with st.expander("💬 Sua opinião nos ajuda a melhorar esta funcionalidade de resumo"):
            feedback_opcao_app_resumo = st.radio(
                "Este resumo gerado foi útil?",
                ["👍 Sim", "👎 Não"],
                key=f"feedback_radio_app_resumo_no_url_{st.session_state.get('last_prompt_resumo_app_no_url', uuid.uuid4().hex)}"
            )
            comentario_app_resumo = st.text_area(
                "Comentário sobre o resumo (opcional):",
                placeholder="Diga o que achou do resumo ou o que faltou.",
                key=f"feedback_comment_app_resumo_no_url_{st.session_state.get('last_prompt_resumo_app_no_url', uuid.uuid4().hex)}"
            )
            if st.button("Enviar Feedback do Resumo", key=f"feedback_submit_app_resumo_no_url_{st.session_state.get('last_prompt_resumo_app_no_url', uuid.uuid4().hex)}"):
                salvar_feedback_rag(
                    pergunta=st.session_state.get("last_prompt_resumo_app_no_url", "Instrução não registrada"),
                    resposta=st.session_state.get("last_response_text_resumo_app_no_url", ""),
                    feedback=feedback_opcao_app_resumo,
                    comentario=comentario_app_resumo,
                )
                st.success("Feedback sobre o resumo enviado com sucesso. Obrigado!")
                if "last_response_text_resumo_app_no_url" in st.session_state: del st.session_state["last_response_text_resumo_app_no_url"]
                if "last_prompt_resumo_app_no_url" in st.session_state: del st.session_state["last_prompt_resumo_app_no_url"]
                st.rerun()

    retrieved_chunks_display_resumo = st.session_state.get('last_retrieved_chunks_details_resumo_app_no_url', [])
    if retrieved_chunks_display_resumo:
        st.markdown("---")
        with st.expander("🔎 Detalhes dos Documentos Recuperados pelo RAG (Azure AI Search)", expanded=False):
            for i, chunk_info in enumerate(retrieved_chunks_display_resumo):
                arquivo_origem = chunk_info.get('arquivo_origem', 'N/A')
                score = chunk_info.get('score', None)
                reranker_score = chunk_info.get('reranker_score', None)
                semantic_caption = chunk_info.get('semantic_caption', None)
                content_preview = chunk_info.get('content_preview', 'Conteúdo não disponível.')
                chunk_id = chunk_info.get('chunk_id', f"chunk_display_resumo_expander_app_no_url_key_{i}")

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
                    key=f"chunk_preview_resumo_expander_app_no_url_unique_key_{chunk_id}"
                )
                st.markdown("---")

# if __name__ == "__main__":
#     if 'main_script_path' not in st.session_state:
#         st.session_state.main_script_path = os.path.abspath(__file__)
#     resumo_interface()
