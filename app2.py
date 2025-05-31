# app2.py (Geração de Peça Processual lendo URLs da Sidebar)
import streamlit as st
import os
import uuid # Para chaves únicas e feedback
import traceback # Para imprimir o traceback em caso de erro
from rag_docintelligence import extrair_texto_documento # Funções para extrair texto de documentos
from rag_utils import (
    get_openai_client, # Cliente OpenAI do Azure
    get_azure_search_client, # Cliente do Azure AI Search
    generate_response_with_conditional_google_search, # Função principal de RAG - CORRIGIDO O NOME
    gerar_docx, # Função para gerar arquivos DOCX
    AZURE_OPENAI_DEPLOYMENT_LLM, # Nome do deployment do LLM
    salvar_feedback_rag # Adicionado para a funcionalidade de feedback
)
# Importar utilitários Chroma
from chroma_utils import obter_contexto_relevante_de_url # Certifique-se que o nome do arquivo é chroma_utils.py

# Carregar o prompt específico para este app diretamente do arquivo
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file_path = os.path.join(current_dir, "..", "prompts", "system_prompt_app2_peticao.md")
    if not os.path.exists(prompt_file_path):
        prompt_file_path_alt = os.path.join(os.path.dirname(current_dir), "prompts", "system_prompt_app2_peticao.md")
        if os.path.exists(prompt_file_path_alt):
            prompt_file_path = prompt_file_path_alt
        else:
            prompt_file_path = os.path.join("prompts", "system_prompt_app2_peticao.md")
    SYSTEM_PROMPT_APP2_PETICAO = open(prompt_file_path, "r", encoding="utf-8").read()
    print(f"INFO APP2: Prompt carregado de: {prompt_file_path}")
except FileNotFoundError:
    error_message = "Erro: Arquivo 'prompts/system_prompt_app2_peticao.md' não encontrado. Verifique o caminho."
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP2_PETICAO = "Você é um assistente de IA para gerar peças jurídicas." # Prompt de fallback
except Exception as e:
    error_message = f"Erro ao carregar 'prompts/system_prompt_app2_peticao.md': {e}"
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP2_PETICAO = "Você é um assistente de IA." # Prompt de fallback genérico

def peticao_interface():
    # st.subheader("✍️ Geração de Peça Processual com Base em Documentos") # Subheader já está na tab
    st.markdown("Envie os documentos do cliente, instruções e, opcionalmente, URLs de jurisprudência (na barra lateral) para gerar um rascunho da peça processual.")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_azure_search_client()
    if not client_openai or not search_client:
        st.error("Falha ao inicializar serviços de IA. Verifique as configurações e logs.")
        st.stop()

    uploaded_files = st.file_uploader(
        "1. Envie documentos com a situação do cliente (PDF, DOCX)",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        key="peticao_multi_uploader_app2_sidebar_urls" # Chave atualizada
    )

    # Sufixo _sidebar_urls para diferenciar chaves de session_state
    sfx = "_sidebar_urls" 
    if f'peticao_multi_texto_extraido_app2{sfx}' not in st.session_state:
        st.session_state[f'peticao_multi_texto_extraido_app2{sfx}'] = ""
    if f'peticao_rag_response_app2{sfx}' not in st.session_state:
        st.session_state[f'peticao_rag_response_app2{sfx}'] = ""
    if f'peticao_edited_response_app2{sfx}' not in st.session_state:
        st.session_state[f'peticao_edited_response_app2{sfx}'] = ""
    if f'peticao_final_version_app2{sfx}' not in st.session_state:
        st.session_state[f'peticao_final_version_app2{sfx}'] = None
    if f'geracao_em_andamento_peticao_app2{sfx}' not in st.session_state:
        st.session_state[f'geracao_em_andamento_peticao_app2{sfx}'] = False
    if f'last_retrieved_chunks_details_peticao_app2{sfx}' not in st.session_state:
        st.session_state[f'last_retrieved_chunks_details_peticao_app2{sfx}'] = []
    if f'last_user_urls_context_peticao_app2{sfx}' not in st.session_state:
        st.session_state[f'last_user_urls_context_peticao_app2{sfx}'] = ""
    if f'last_prompt_peticao_app2{sfx}' not in st.session_state:
        st.session_state[f'last_prompt_peticao_app2{sfx}'] = ""
    if f'last_response_text_peticao_app2{sfx}' not in st.session_state:
        st.session_state[f'last_response_text_peticao_app2{sfx}'] = ""

    if not st.session_state[f'geracao_em_andamento_peticao_app2{sfx}']:
        st.session_state[f'last_retrieved_chunks_details_peticao_app2{sfx}'] = []

    if uploaded_files and not st.session_state[f'peticao_multi_texto_extraido_app2{sfx}']:
        textos = []
        st.session_state[f'geracao_em_andamento_peticao_app2{sfx}'] = True
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_path = f"temp_peticao_app2_sidebar_urls_{uuid.uuid4().hex}{ext}"
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
            st.session_state[f'peticao_multi_texto_extraido_app2{sfx}'] = "\n\n".join(textos)
            st.success("Textos extraídos com sucesso.")
        else:
            st.session_state[f'peticao_multi_texto_extraido_app2{sfx}'] = ""
            st.warning("Nenhum texto pôde ser extraído dos arquivos.")
        st.session_state[f'geracao_em_andamento_peticao_app2{sfx}'] = False
        st.rerun()

    if st.session_state[f'peticao_multi_texto_extraido_app2{sfx}'] or True:
        if st.session_state[f'peticao_multi_texto_extraido_app2{sfx}']:
            with st.expander("Ver Texto Extraído Consolidado", expanded=False):
                st.text_area(
                    "Texto Extraído:", 
                    st.session_state[f'peticao_multi_texto_extraido_app2{sfx}'], 
                    height=200, 
                    disabled=True, 
                    key=f"peticao_texto_extraido_display_app2{sfx}"
                )

        st.markdown("---")
        st.markdown("### 2. Instruções para a Peça")

        prompt_from_user_text_area = st.text_area(
            "Instruções para a IA (tipo de peça, área do Direito, pontos a destacar, etc.):",
            placeholder=(
                "Ex: Elabore uma petição inicial trabalhista com base nos fatos descritos nos documentos. "
                "Destaque a questão do adicional de periculosidade e horas extras não pagas."
            ),
            height=150, 
            key=f"peticao_user_instruction_text_area_app2{sfx}"
        )

        # CAMPOS DE URL AGORA ESTÃO NA SIDEBAR (main.py) E SERÃO LIDOS DO SESSION_STATE
        # O st.expander para URLs foi removido daqui.
        
        # Lê as URLs da sidebar (definidas em main.py)
        url1_sidebar = st.session_state.get('sidebar_url1', "")
        url2_sidebar = st.session_state.get('sidebar_url2', "")
        url3_sidebar = st.session_state.get('sidebar_url3', "")
        user_urls_from_sidebar = [url for url in [url1_sidebar, url2_sidebar, url3_sidebar] if url.strip()]

        if user_urls_from_sidebar:
            st.info(f"Utilizando {len(user_urls_from_sidebar)} URL(s) de contexto da barra lateral.")


        enable_google_search_peticao = st.checkbox("Habilitar busca complementar na Web (Google)?", value=True, key=f"peticao_enable_google_search_app2{sfx}_checkbox")

        if st.button("Gerar Peça Processual", key=f"peticao_gerar_button_key_app2{sfx}_button"):
            if not st.session_state[f'peticao_multi_texto_extraido_app2{sfx}'].strip() and not prompt_from_user_text_area.strip() and not user_urls_from_sidebar:
                 st.warning("Forneça documentos, instruções detalhadas ou URLs (na barra lateral) para a IA.")
            else:
                st.session_state[f'geracao_em_andamento_peticao_app2{sfx}'] = True
                st.session_state[f'last_retrieved_chunks_details_peticao_app2{sfx}'] = []
                st.session_state[f'last_user_urls_context_peticao_app2{sfx}'] = ""
                
                prompt_base_para_contexto_urls = prompt_from_user_text_area.strip()
                if not prompt_base_para_contexto_urls and st.session_state[f'peticao_multi_texto_extraido_app2{sfx}']:
                    preview_texto_doc = st.session_state[f'peticao_multi_texto_extraido_app2{sfx}'][:500]
                    prompt_base_para_contexto_urls = f"Informações relevantes nos documentos sobre: {preview_texto_doc}..."
                elif not prompt_base_para_contexto_urls:
                    prompt_base_para_contexto_urls = "Jurisprudência e informações relevantes para o caso."

                contexto_urls_agregado_para_prompt = ""
                contexto_urls_agregado_para_exibir = ""

                if user_urls_from_sidebar:
                    num_urls_para_consultar = len(user_urls_from_sidebar)
                    spinner_message_urls = f"Consultando {num_urls_para_consultar} URL(s) da barra lateral..."
                    with st.spinner(spinner_message_urls):
                        for i, url_item in enumerate(user_urls_from_sidebar, 1):
                            print(f"INFO APP2 (Peça): Obtendo contexto Chroma da URL {i} (sidebar): {url_item} para a consulta: '{prompt_base_para_contexto_urls}'")
                            contexto_url_individual = obter_contexto_relevante_de_url(
                                url_item,
                                prompt_base_para_contexto_urls,
                                top_k_chunks=2 
                            )
                            if contexto_url_individual and "Nenhum conteúdo relevante" not in contexto_url_individual and "Falha ao carregar" not in contexto_url_individual:
                                contexto_urls_agregado_para_prompt += f"\n--- Contexto da URL {i} ({url_item}) ---\n{contexto_url_individual}\n--- Fim do Contexto da URL {i} ---\n\n"
                                contexto_urls_agregado_para_exibir += f"<b>Contexto da URL {i} ({url_item}):</b><br>{contexto_url_individual}<hr>"
                                print(f"INFO APP2 (Peça): Contexto da URL {i} (sidebar) adicionado.")
                            else:
                                aviso_url = f"<i>Nenhum contexto útil obtido da URL {i} ({url_item}) da barra lateral.</i><br>"
                                contexto_urls_agregado_para_exibir += aviso_url
                                print(f"AVISO APP2 (Peça): {aviso_url}")
                
                st.session_state[f'last_user_urls_context_peticao_app2{sfx}'] = contexto_urls_agregado_para_exibir if contexto_urls_agregado_para_exibir else "Nenhuma URL fornecida na barra lateral ou nenhum contexto relevante extraído."
                
                instrucao_usuario_para_llm = prompt_from_user_text_area.strip() if prompt_from_user_text_area.strip() else "Elabore a peça jurídica mais adequada com base nos documentos e fatos fornecidos, e no contexto das URLs, se houver."
                
                if contexto_urls_agregado_para_prompt:
                    instrucao_usuario_para_llm = (
                        f"{contexto_urls_agregado_para_prompt}"
                        f"Considerando os contextos acima extraídos das URLs fornecidas pelo usuário na barra lateral, "
                        f"e o(s) documento(s) também fornecido(s) (se houver), siga a instrução abaixo:\n\n"
                        f"Instrução do Usuário para Peça Processual: \"{instrucao_usuario_para_llm}\""
                    )
                
                with st.spinner("LexAutomate está redigindo a peça... Por favor, aguarde."):
                    try:
                        # Corrigido o nome da função aqui
                        resposta = generate_response_with_conditional_google_search(
                            system_message_base=SYSTEM_PROMPT_APP2_PETICAO,
                            user_instruction=instrucao_usuario_para_llm,
                            context_document_text=st.session_state[f'peticao_multi_texto_extraido_app2{sfx}'],
                            search_client=search_client,
                            client_openai=client_openai,
                            azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,
                            azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM,
                            top_k_initial_search_azure=7,
                            top_k_rerank_azure=3,
                            use_semantic_search_azure=True,
                            enable_google_search_trigger=enable_google_search_peticao, # Nome da variável corrigido
                            min_azure_results_for_google_trigger=2,
                            num_google_results=3,
                            temperature=0.2,
                            max_tokens=4000 
                        )
                        
                        resposta_str = str(resposta).strip() if resposta is not None else ""
                        st.session_state[f'peticao_rag_response_app2{sfx}'] = resposta_str
                        st.session_state[f'peticao_edited_response_app2{sfx}'] = resposta_str
                        st.session_state[f'peticao_final_version_app2{sfx}'] = None
                        st.session_state[f'last_retrieved_chunks_details_peticao_app2{sfx}'] = st.session_state.get('last_retrieved_chunks_details', [])
                        
                        st.session_state[f'last_prompt_peticao_app2{sfx}'] = instrucao_usuario_para_llm
                        st.session_state[f'last_response_text_peticao_app2{sfx}'] = resposta_str

                        st.success("Peça gerada com sucesso!")
                    except Exception as e:
                        st.error(f"Ocorreu um erro durante a geração da peça: {e}")
                        st.session_state[f'peticao_rag_response_app2{sfx}'] = ""
                        st.session_state[f'peticao_edited_response_app2{sfx}'] = ""
                        print(f"DEBUG APP2 (Peça): Erro na geração da peça: {e}")
                        traceback.print_exc()
                    finally:
                        st.session_state[f'geracao_em_andamento_peticao_app2{sfx}'] = False
                        st.rerun()

    texto_preview_peticao = st.session_state.get(f'peticao_edited_response_app2{sfx}', "").strip()
    if texto_preview_peticao:
        st.markdown("---")
        st.markdown("### 3. Revisão, Edição e Exportação")

        if st.session_state.get(f'last_user_urls_context_peticao_app2{sfx}') and ("Contexto da URL" in st.session_state.get(f'last_user_urls_context_peticao_app2{sfx}')):
            with st.expander("Contexto das URLs da Barra Lateral Utilizado", expanded=False):
                st.markdown(st.session_state[f'last_user_urls_context_peticao_app2{sfx}'], unsafe_allow_html=True)

        st.markdown("#### Pré-visualização da Peça:")
        with st.container(border=True):
            st.markdown(texto_preview_peticao, unsafe_allow_html=True)

        st.markdown("---")
        texto_editado_peticao = st.text_area(
            "Edite a peça gerada (Markdown):",
            value=texto_preview_peticao,
            height=600,
            key=f"peticao_multi_editor_app2{sfx}_key"
        )

        if texto_editado_peticao != st.session_state.get(f'peticao_edited_response_app2{sfx}', ""):
            st.session_state[f'peticao_edited_response_app2{sfx}'] = texto_editado_peticao
            st.session_state[f'peticao_final_version_app2{sfx}'] = None

        col_btn1_save_peticao, col_btn2_download_peticao = st.columns(2)
        with col_btn1_save_peticao:
            if st.button("Salvar Versão Editada", key=f"peticao_save_edited_btn_key_app2{sfx}_button"):
                st.session_state[f'peticao_final_version_app2{sfx}'] = st.session_state[f'peticao_edited_response_app2{sfx}']
                st.success("Versão salva.")

        if st.session_state[f'peticao_final_version_app2{sfx}'] is not None:
             with col_btn2_download_peticao:
                try:
                    docx_data = gerar_docx(st.session_state[f'peticao_final_version_app2{sfx}'])
                    st.download_button(
                        label="Baixar Peça em DOCX",
                        data=docx_data,
                        file_name="LexAutomate_Peticao_Juris_Usuario.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"peticao_download_docx_final_key_app2{sfx}_button"
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar DOCX: {e}")
                    print(f"DEBUG APP2 (Peça): Erro ao gerar DOCX para petição: {e}")
                    traceback.print_exc()

    if f'last_response_text_peticao_app2{sfx}' in st.session_state and st.session_state[f'last_response_text_peticao_app2{sfx}']:
        with st.expander("💬 Sua opinião nos ajuda a melhorar esta funcionalidade"):
            feedback_opcao_app2 = st.radio(
                "Essa peça gerada foi útil?",
                ["👍 Sim", "👎 Não"],
                key=f"feedback_radio_app2{sfx}_{st.session_state.get(f'last_prompt_peticao_app2{sfx}', uuid.uuid4().hex)}"
            )
            comentario_app2 = st.text_area(
                "Comentário sobre a peça (opcional):",
                placeholder="Diga o que achou da peça ou o que faltou.",
                key=f"feedback_comment_app2{sfx}_{st.session_state.get(f'last_prompt_peticao_app2{sfx}', uuid.uuid4().hex)}"
            )
            if st.button("Enviar Feedback da Peça", key=f"feedback_submit_app2{sfx}_{st.session_state.get(f'last_prompt_peticao_app2{sfx}', uuid.uuid4().hex)}"):
                salvar_feedback_rag(
                    pergunta=st.session_state.get(f'last_prompt_peticao_app2{sfx}', "Instrução não registrada"),
                    resposta=st.session_state.get(f'last_response_text_peticao_app2{sfx}', ""),
                    feedback=feedback_opcao_app2,
                    comentario=comentario_app2,
                )
                st.success("Feedback sobre a peça enviado com sucesso. Obrigado!")
                if f'last_response_text_peticao_app2{sfx}' in st.session_state: del st.session_state[f'last_response_text_peticao_app2{sfx}']
                if f'last_prompt_peticao_app2{sfx}' in st.session_state: del st.session_state[f'last_prompt_peticao_app2{sfx}']
                st.rerun()

    retrieved_chunks_display_peticao = st.session_state.get(f'last_retrieved_chunks_details_peticao_app2{sfx}', [])
    if retrieved_chunks_display_peticao:
        st.markdown("---")
        with st.expander("🔎 Detalhes dos Documentos Recuperados pelo RAG (Azure AI Search)", expanded=False):
            for i, chunk_info in enumerate(retrieved_chunks_display_peticao):
                arquivo_origem = chunk_info.get('arquivo_origem', 'N/A')
                score = chunk_info.get('score', None)
                reranker_score = chunk_info.get('reranker_score', None)
                semantic_caption = chunk_info.get('semantic_caption', None)
                content_preview = chunk_info.get('content_preview', 'Conteúdo não disponível.')
                chunk_id = chunk_info.get('chunk_id', f"chunk_display_peticao_expander_app2{sfx}_key_{i}")

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
                    key=f"chunk_preview_peticao_expander_app2{sfx}_unique_key_{chunk_id}"
                )
                st.markdown("---")

# if __name__ == "__main__":
#     if 'main_script_path' not in st.session_state:
#          st.session_state.main_script_path = os.path.abspath(__file__)
#     peticao_interface()
