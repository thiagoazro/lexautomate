# app2.py (Geração de Peça Processual)
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
    SYSTEM_PROMPT_APP2_PETICAO = open(os.path.join("prompts", "system_prompt_app2_peticao.md"), "r", encoding="utf-8").read()
except FileNotFoundError:
    error_message = "Erro: Arquivo 'prompts/system_prompt_app2_peticao.md' não encontrado. Verifique o caminho."
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP2_PETICAO = "Você é um assistente de IA para gerar peças jurídicas." # Fallback
except Exception as e:
    error_message = f"Erro ao carregar 'prompts/system_prompt_app2_peticao.md': {e}"
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP2_PETICAO = "Você é um assistente de IA." # Fallback


def peticao_interface():
    st.subheader("Geração de Peça Processual com Base em Documentos")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_azure_search_client()
    if not client_openai or not search_client:
        st.error("Falha ao inicializar serviços de IA.")
        st.stop()

    uploaded_files = st.file_uploader(
        "1. Envie documentos com a situação do cliente (PDF, DOCX)",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        key="peticao_multi_uploader_app2"
    )

    # Inicialização de session_state
    if 'peticao_multi_texto_extraido' not in st.session_state:
        st.session_state.peticao_multi_texto_extraido = ""
    if 'peticao_rag_response' not in st.session_state:
        st.session_state.peticao_rag_response = "" # Inicializado como string vazia
    if 'peticao_edited_response' not in st.session_state:
        st.session_state.peticao_edited_response = "" # Inicializado como string vazia
    if 'peticao_final_version' not in st.session_state:
        st.session_state.peticao_final_version = None
    if 'geracao_em_andamento_peticao' not in st.session_state:
        st.session_state.geracao_em_andamento_peticao = False
    if 'last_retrieved_chunks_details_peticao' not in st.session_state:
        st.session_state.last_retrieved_chunks_details_peticao = []


    if not st.session_state.geracao_em_andamento_peticao and st.session_state.get('last_retrieved_chunks_details_peticao'):
        st.session_state.last_retrieved_chunks_details_peticao = []


    if uploaded_files and not st.session_state.peticao_multi_texto_extraido: # Processa apenas se não houver texto extraído
        textos = []
        st.session_state.geracao_em_andamento_peticao = True
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_path = f"temp_peticao_{uuid.uuid4().hex}{ext}" # Usando UUID para garantir unicidade
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
                    try:
                        os.remove(temp_path)
                    except Exception as e_rm:
                        print(f"Aviso: Falha ao remover arquivo temporário {temp_path}: {e_rm}")
        
        if textos:
            st.session_state.peticao_multi_texto_extraido = "\n\n".join(textos)
            st.success("Textos extraídos com sucesso.")
        else:
            st.session_state.peticao_multi_texto_extraido = ""
            st.warning("Nenhum texto pôde ser extraído dos arquivos.")
        st.session_state.geracao_em_andamento_peticao = False
        st.rerun() # Atualiza a UI

    if st.session_state.peticao_multi_texto_extraido:
        with st.expander("Ver Texto Extraído Consolidado", expanded=False):
            st.text_area(
                "Texto Extraído:", 
                st.session_state.peticao_multi_texto_extraido, 
                height=200, 
                disabled=True, 
                key="peticao_texto_extraido_display_app2"
            )

        st.markdown("---")
        st.markdown("### 2. Geração do Rascunho com IA")

        prompt_from_user_text_area = st.text_area(
            "2. Instrução para a IA (opcional):",
            placeholder=(
                "Escreva aqui instruções específicas para a peça jurídica a ser gerada.\n\n"
                "Você pode, por exemplo, indicar o tipo de peça desejada (petição inicial, contestação etc.), "
                "a área do Direito (trabalhista, cível, consumidor etc.), e, se desejar, referenciar um modelo "
                "a ser seguido.\n\n"
                "Exemplo: Elabore uma petição inicial trabalhista defendendo os interesses da parte autora, conforme os "
                "fatos descritos no documento enviado. Utilize a estrutura do modelo X como referência."
            ),
            height=150, 
            key="peticao_user_instruction_text_area_app2"
        )

        enable_google_search_peticao = st.checkbox("Habilitar busca complementar na Web (Google) para esta peça?", value=True, key="peticao_enable_google_search_app2")

        if st.button("Gerar Peça Processual", key="peticao_gerar_button_key_app2"):
            if not st.session_state.peticao_multi_texto_extraido.strip() and not prompt_from_user_text_area.strip():
                 st.warning("Forneça os documentos do cliente ou uma instrução detalhada para a IA.")
            else:
                st.session_state.geracao_em_andamento_peticao = True
                st.session_state.last_retrieved_chunks_details_peticao = []
                
                instrucao_final_usuario_para_rag = prompt_from_user_text_area.strip() if prompt_from_user_text_area.strip() else "Elabore a peça jurídica mais adequada com base nos documentos e fatos fornecidos."
                
                with st.spinner("LexAutomate está redigindo a peça... Por favor, aguarde."):
                    try:
                        resposta = generate_response_with_conditional_google_search(  # GraphRAG silently included

                            system_message_base=SYSTEM_PROMPT_APP2_PETICAO,
                            user_instruction=instrucao_final_usuario_para_rag,
                            context_document_text=st.session_state.peticao_multi_texto_extraido,
                            search_client=search_client,
                            client_openai=client_openai,
                            azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,       # <--- CORRIGIDO
                            azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM, # <--- CORRIGIDO/ADICIONADO
                            top_k_initial_search_azure=7, # Ex: Buscar 7 inicialmente
                            top_k_rerank_azure=3,         # Ex: Manter os 3 melhores após reranking
                            use_semantic_search_azure=True,
                            enable_google_search_trigger=enable_google_search_peticao,
                            min_azure_results_for_google_trigger=2,
                            num_google_results=3,
                            temperature=0.2,
                            max_tokens=4000 
                        )
                        
                        resposta_str = str(resposta).strip() if resposta is not None else ""
                        st.session_state.peticao_rag_response = resposta_str
                        st.session_state.peticao_edited_response = resposta_str
                        st.session_state.peticao_final_version = None
                        st.session_state.last_retrieved_chunks_details_peticao = st.session_state.get('last_retrieved_chunks_details', [])
                        st.success("Peça gerada com sucesso!")
                    except Exception as e:
                        st.error(f"Ocorreu um erro durante a geração da peça: {e}")
                        st.session_state.peticao_rag_response = ""
                        st.session_state.peticao_edited_response = ""
                        print(f"DEBUG: Erro na geração da peça: {e}")
                        traceback.print_exc()
                    finally:
                        st.session_state.geracao_em_andamento_peticao = False
                        st.rerun()

    texto_preview_peticao = st.session_state.get('peticao_edited_response', "").strip()
    if texto_preview_peticao: # Mostra apenas se houver algo
        st.markdown("---")
        st.markdown("### 3. Revisão, Edição e Exportação")

        st.markdown("#### Pré-visualização da Peça:")
        with st.container(border=True):
            st.markdown(texto_preview_peticao, unsafe_allow_html=True)

        st.markdown("---")
        texto_editado_peticao = st.text_area(
            "Edite a peça gerada (Markdown):",
            value=texto_preview_peticao, # Usa o valor da sessão
            height=600,
            key="peticao_multi_editor_app2"
        )

        if texto_editado_peticao != st.session_state.get('peticao_edited_response', ""):
            st.session_state.peticao_edited_response = texto_editado_peticao
            st.session_state.peticao_final_version = None
            # st.rerun()

        col_btn1_save_peticao, col_btn2_download_peticao = st.columns(2)

        with col_btn1_save_peticao:
            if st.button("Salvar Versão Editada", key="peticao_save_edited_btn_key_app2"):
                st.session_state.peticao_final_version = st.session_state.peticao_edited_response
                st.success("Versão salva.")
                st.rerun()

        if st.session_state.peticao_final_version is not None:
             with col_btn2_download_peticao:
                try:
                    docx_data = gerar_docx(st.session_state.peticao_final_version)
                    st.download_button(
                        label="Baixar DOCX",
                        data=docx_data,
                        file_name="LexAutomate_Peticao.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="peticao_download_docx_final_key_app2"
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar DOCX: {e}")
                    print(f"DEBUG: Erro ao gerar DOCX para petição: {e}")
                    traceback.print_exc()

    retrieved_chunks_display_peticao = st.session_state.get('last_retrieved_chunks_details_peticao', [])
        
    if retrieved_chunks_display_peticao:
        st.markdown("---")
        with st.expander("🔎 Detalhes dos Documentos Recuperados pelo RAG (para a última geração)", expanded=False):
            for i, chunk_info in enumerate(retrieved_chunks_display_peticao):
                arquivo_origem = chunk_info.get('arquivo_origem', 'N/A')
                score = chunk_info.get('score', None)
                reranker_score = chunk_info.get('reranker_score', None)
                semantic_caption = chunk_info.get('semantic_caption', None)
                content_preview = chunk_info.get('content_preview', 'Conteúdo não disponível.')
                chunk_id = chunk_info.get('chunk_id', f"chunk_display_peticao_expander_app2_{i}")

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
                    key=f"chunk_preview_peticao_expander_key_app2_{chunk_id}"
                )
                st.markdown("---")
