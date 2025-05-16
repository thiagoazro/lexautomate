# app.py (versão com múltiplos documentos para resumo jurídico)
import streamlit as st
import os
import uuid
import traceback
from rag_docintelligence import extrair_texto_documento
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_response_with_conditional_google_search, # Usando a função correta
    gerar_docx,
    AZURE_OPENAI_DEPLOYMENT_LLM
)

# Carregar o prompt específico para este app diretamente do arquivo
try:
    # Assumindo que a pasta 'prompts' está no mesmo nível do script principal executado
    SYSTEM_PROMPT_APP_RESUMO = open(os.path.join("prompts", "system_prompt_app_resumo.md"), "r", encoding="utf-8").read()
except FileNotFoundError:
    error_message = "Erro: Arquivo 'prompts/system_prompt_app_resumo.md' não encontrado. Verifique o caminho."
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP_RESUMO = "Você é um assistente de IA. Por favor, seja breve e direto." # Fallback
except Exception as e:
    error_message = f"Erro ao carregar 'prompts/system_prompt_app_resumo.md': {e}"
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP_RESUMO = "Você é um assistente de IA." # Fallback


def resumo_interface():
    st.subheader("Resumo de Documento Jurídico")
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
        key="resumo_multi_uploader"
    )

    # Inicialização de session_state
    if 'resumo_multi_texto_extraido' not in st.session_state:
        st.session_state.resumo_multi_texto_extraido = ""
    if 'resumo_rag_response' not in st.session_state:
        st.session_state.resumo_rag_response = None # Mantido como None para consistência
    if 'resumo_edited_response' not in st.session_state:
        st.session_state.resumo_edited_response = "" # Inicializado como string vazia
    if 'resumo_final_version' not in st.session_state:
        st.session_state.resumo_final_version = None
    if 'geracao_em_andamento_resumo' not in st.session_state:
        st.session_state.geracao_em_andamento_resumo = False
    if 'last_retrieved_chunks_details_resumo' not in st.session_state:
        st.session_state.last_retrieved_chunks_details_resumo = []


    # Limpar chunks de execuções anteriores desta aba específica
    if not st.session_state.geracao_em_andamento_resumo and st.session_state.get('last_retrieved_chunks_details_resumo'):
         st.session_state.last_retrieved_chunks_details_resumo = []


    if uploaded_files and not st.session_state.resumo_multi_texto_extraido: # Processa apenas se não houver texto extraído
        textos = []
        st.session_state.geracao_em_andamento_resumo = True
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            # Usando um nome de arquivo temporário mais robusto com UUID
            temp_file_path = f"temp_resumo_{uuid.uuid4().hex}{ext}"
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
                    try:
                        os.remove(temp_file_path)
                    except Exception as e_rm:
                        print(f"Aviso: Falha ao remover arquivo temporário {temp_file_path}: {e_rm}")
        
        if textos:
            st.session_state.resumo_multi_texto_extraido = "\n\n".join(textos)
            st.success("Textos extraídos com sucesso.")
        else:
            st.session_state.resumo_multi_texto_extraido = "" 
            st.warning("Nenhum texto pôde ser extraído dos arquivos.")
        st.session_state.geracao_em_andamento_resumo = False
        st.rerun() # Atualiza a UI após extração


    if st.session_state.resumo_multi_texto_extraido:
        with st.expander("Ver Texto Extraído Consolidado", expanded=False):
            st.text_area(
                "Texto Extraído:", 
                st.session_state.resumo_multi_texto_extraido, 
                height=200, 
                disabled=True, 
                key="resumo_texto_extraido_display"
            )

        st.markdown("---")
        st.markdown("### 2. Geração do Rascunho com IA")
        
        prompt_resumo_usuario = st.text_area (
            "Direcione o resumo (opcional - Deixe em branco para resumo padrão):",
            placeholder=(
                "Ex: Gere um resumo da cláusula de penalidades.\n"
                "Ex: Para cada contrato anexado, gere um resumo com o nome das partes e as obrigações principais."
            ),
            height=100,
            key="prompt_resumo_input"
        )

        enable_google_search_resumo = st.checkbox("Habilitar busca complementar na Web (Google) para este resumo?", value=True, key="resumo_enable_google_search_app")

        if st.button("Gerar Resumo com RAG", key="resumo_gerar_btn_main_app"):
            if not st.session_state.resumo_multi_texto_extraido.strip() and not prompt_resumo_usuario.strip():
                st.warning("Forneça documentos ou uma instrução detalhada para a IA.")
            else:
                st.session_state.geracao_em_andamento_resumo = True
                st.session_state.last_retrieved_chunks_details_resumo = [] # Limpa antes de nova busca

                user_instruction_final = prompt_resumo_usuario.strip() if prompt_resumo_usuario.strip() else "Gerar um resumo padrão do documento, destacando os pontos chave conforme a estrutura solicitada."
                
                with st.spinner("LexAutomate está resumindo... Por favor, aguarde."):
                    try:
                        resposta = generate_response_with_conditional_google_search(
                            system_message=SYSTEM_PROMPT_APP_RESUMO,
                            user_instruction=user_instruction_final,
                            context_document_text=st.session_state.resumo_multi_texto_extraido,
                            search_client=search_client,
                            client_openai=client_openai,
                            azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,       # <--- CORRIGIDO
                            azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM, # <--- CORRIGIDO/ADICIONADO
                            top_k_azure=5,
                            use_semantic_search_azure=True,
                            enable_google_search_fallback=enable_google_search_resumo,
                            min_azure_results_for_fallback=2, 
                            num_google_results=3,
                            temperature=0.1,
                            max_tokens=3500
                        )
                        
                        resposta_str = str(resposta).strip() if resposta is not None else ""
                        st.session_state.resumo_rag_response = resposta_str
                        st.session_state.resumo_edited_response = resposta_str 
                        st.session_state.resumo_final_version = None
                        st.session_state.last_retrieved_chunks_details_resumo = st.session_state.get('last_retrieved_chunks_details', [])
                        st.success("Rascunho do resumo gerado com sucesso!")
                    except Exception as e:
                        st.error(f"Ocorreu um erro durante a geração do resumo: {e}")
                        st.session_state.resumo_rag_response = ""
                        st.session_state.resumo_edited_response = ""
                        print(f"DEBUG: Erro na geração do resumo: {e}")
                        traceback.print_exc()
                    finally:
                        st.session_state.geracao_em_andamento_resumo = False
                        st.rerun() 

    # Garante que resumo_edited_response seja uma string para o editor
    texto_preview_resumo = st.session_state.get('resumo_edited_response', "")
    if not isinstance(texto_preview_resumo, str):
        texto_preview_resumo = str(texto_preview_resumo)
    texto_preview_resumo = texto_preview_resumo.strip()


    if texto_preview_resumo: # Mostra a seção de edição apenas se houver algo
        st.markdown("---")
        st.markdown("### 3. Revisão, Edição e Exportação")

        st.markdown("#### Pré-visualização do Resumo:")
        with st.container(border=True):
            st.markdown(texto_preview_resumo, unsafe_allow_html=True)

        st.markdown("---")
        texto_editado_resumo = st.text_area(
            "Edite o resumo gerado (Markdown):",
            value=texto_preview_resumo, # Usa o valor da sessão que pode ter sido atualizado
            height=600,
            key="resumo_editor_area_app"
        )

        # Atualiza o estado da sessão se o texto editado mudar
        if texto_editado_resumo != st.session_state.get('resumo_edited_response', ""):
            st.session_state.resumo_edited_response = texto_editado_resumo
            st.session_state.resumo_final_version = None # Reseta a versão final ao editar
            # st.rerun() # Pode causar loop se não gerenciado com cuidado, mas força atualização

        col_btn_save_resumo, col_btn_download_resumo = st.columns(2)

        with col_btn_save_resumo:
            if st.button("Salvar Versão Editada do Resumo", key="resumo_save_edited_btn_app"):
                st.session_state.resumo_final_version = st.session_state.resumo_edited_response # Salva o conteúdo atual do editor
                st.success("Versão do resumo salva.")
                st.rerun() # Para atualizar o estado do botão de download

        if st.session_state.resumo_final_version is not None:
            with col_btn_download_resumo:
                try:
                    docx_data = gerar_docx(st.session_state.resumo_final_version)
                    st.download_button(
                        label="Baixar Resumo em DOCX",
                        data=docx_data,
                        file_name="LexAutomate_Resumo.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="resumo_download_docx_btn_app"
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar DOCX para o resumo: {e}")
                    print(f"DEBUG: Erro ao gerar DOCX para resumo: {e}")
                    traceback.print_exc()
    
    retrieved_chunks_display = st.session_state.get('last_retrieved_chunks_details_resumo', [])

    if retrieved_chunks_display:
        st.markdown("---")
        with st.expander("🔎 Detalhes dos Documentos Recuperados pelo RAG (para a última geração de resumo)", expanded=False):
            for i, chunk_info in enumerate(retrieved_chunks_display):
                arquivo_origem = chunk_info.get('arquivo_origem', 'N/A')
                score = chunk_info.get('score', None)
                reranker_score = chunk_info.get('reranker_score', None)
                semantic_caption = chunk_info.get('semantic_caption', None)
                content_preview = chunk_info.get('content_preview', 'Conteúdo não disponível.')
                chunk_id = chunk_info.get('chunk_id', f"chunk_display_resumo_expander_app_{i}")

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
                    key=f"chunk_preview_resumo_expander_key_app_{chunk_id}"
                )
                st.markdown("---")
