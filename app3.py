# app3.py (Análise de Cláusulas Contratuais)
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
    SYSTEM_PROMPT_APP3_VALIDACAO = open(os.path.join("prompts", "system_prompt_app3_validacao.md"), "r", encoding="utf-8").read()
except FileNotFoundError:
    error_message = "Erro: Arquivo 'prompts/system_prompt_app3_validacao.md' não encontrado. Verifique o caminho."
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP3_VALIDACAO = "Você é um assistente de IA para validar cláusulas." # Fallback
except Exception as e:
    error_message = f"Erro ao carregar 'prompts/system_prompt_app3_validacao.md': {e}"
    print(error_message)
    st.error(error_message)
    SYSTEM_PROMPT_APP3_VALIDACAO = "Você é um assistente de IA." # Fallback


def validacao_interface():
    st.subheader("Análise e Validação de Cláusulas Contratuais")
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
        key="validacao_uploader_multi_app3"
    )

    # Inicialização de session_state
    if 'validacao_multi_texto_extraido' not in st.session_state:
        st.session_state.validacao_multi_texto_extraido = ""
    if 'validacao_rag_response' not in st.session_state:
        st.session_state.validacao_rag_response = None # Mantido como None
    if 'validacao_edited_response' not in st.session_state:
        st.session_state.validacao_edited_response = "" # Inicializado como string vazia
    if 'validacao_final_version' not in st.session_state:
        st.session_state.validacao_final_version = None
    if 'geracao_em_andamento_validacao' not in st.session_state:
        st.session_state.geracao_em_andamento_validacao = False
    if 'last_retrieved_chunks_details_validacao' not in st.session_state:
        st.session_state.last_retrieved_chunks_details_validacao = []


    if not st.session_state.geracao_em_andamento_validacao and st.session_state.get('last_retrieved_chunks_details_validacao'):
        st.session_state.last_retrieved_chunks_details_validacao = []


    if uploaded_files and not st.session_state.validacao_multi_texto_extraido: # Processa apenas se não houver texto extraído
        textos = []
        st.session_state.geracao_em_andamento_validacao = True
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_path = f"temp_validacao_{uuid.uuid4().hex}{ext}" # Usando UUID
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
            st.session_state.validacao_multi_texto_extraido = "\n\n".join(textos)
            st.success("Textos extraídos com sucesso.")
        else:
            st.session_state.validacao_multi_texto_extraido = ""
            st.warning("Nenhum texto pôde ser extraído dos arquivos.")
        st.session_state.geracao_em_andamento_validacao = False
        st.rerun() # Atualiza a UI

    if st.session_state.validacao_multi_texto_extraido:
        with st.expander("Ver Texto Extraído", expanded=False):
            st.text_area(
                "Texto Completo:", 
                st.session_state.validacao_multi_texto_extraido, 
                height=200, 
                key="validacao_texto_view_app3",
                disabled=True
            )

        st.markdown("---")
        st.markdown("### 2. Geração da Análise com IA")
        prompt_validacao_usuario = st.text_area(
            "Especifique a cláusula ou ponto para análise/validação:",
            placeholder="Ex: Analise a Cláusula 5 (Multa Contratual) e verifique sua conformidade.",
            height=100,
            key="prompt_validacao_input_app3"
        )

        enable_google_search_validacao = st.checkbox("Habilitar busca complementar na Web (Google) para esta análise?", value=True, key="validacao_enable_google_search_app3")

        if st.button("Analisar/Validar Cláusulas", key="validacao_gerar_btn_app3"):
            if not prompt_validacao_usuario.strip():
                st.warning("Por favor, digite a instrução para a análise.")
            else:
                st.session_state.geracao_em_andamento_validacao = True
                st.session_state.last_retrieved_chunks_details_validacao = []

                with st.spinner("Analisando..."):
                    try:
                        resposta = generate_response_with_conditional_google_search(
                            system_message_base=SYSTEM_PROMPT_APP3_VALIDACAO,
                            user_instruction=prompt_validacao_usuario,
                            context_document_text=st.session_state.validacao_multi_texto_extraido,
                            search_client=search_client,
                            client_openai=client_openai,
                            azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,       # <--- CORRIGIDO
                            azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM, # <--- CORRIGIDO/ADICIONADO
                            top_k_initial_search_azure=7, # Ex: Buscar 7 inicialmente
                            top_k_rerank_azure=3,         # Ex: Manter os 3 melhores após reranking
                            use_semantic_search_azure=True,
                            enable_google_search_trigger=enable_google_search_validacao,
                            min_azure_results_for_google_trigger=1,
                            num_google_results=2,
                            temperature=0.1,
                            max_tokens=3500
                        )
                        
                        resposta_str = str(resposta).strip() if resposta is not None else ""
                        st.session_state.validacao_rag_response = resposta_str
                        st.session_state.validacao_edited_response = resposta_str
                        st.session_state.validacao_final_version = None
                        st.session_state.last_retrieved_chunks_details_validacao = st.session_state.get('last_retrieved_chunks_details', [])
                        st.success("Rascunho da análise gerado. Revise e edite abaixo.")
                    except Exception as e:
                        st.error(f"Ocorreu um erro ao realizar a análise: {e}")
                        st.session_state.validacao_rag_response = None
                        st.session_state.validacao_edited_response = "" # Limpa em caso de erro
                        traceback.print_exc()
                    finally:
                        st.session_state.geracao_em_andamento_validacao = False
                        st.rerun()

    texto_preview_validacao = st.session_state.get('validacao_edited_response', "").strip()
    if texto_preview_validacao: # Mostra apenas se houver algo
        st.markdown("---")
        st.markdown("### 3. Revisão, Edição e Exportação")
        st.markdown("#### Pré-visualização da Análise Formatada:")
        with st.container(border=True):
            st.markdown(texto_preview_validacao)

        edited_text_validacao = st.text_area( # Nome da variável local
            "Edite a análise gerada (use `**texto**` para negrito):",
            value=texto_preview_validacao, # Usa o valor da sessão
            height=400,
            key="validacao_editor_multi_app3"
        )

        if edited_text_validacao != st.session_state.get('validacao_edited_response', ""):
            st.session_state.validacao_edited_response = edited_text_validacao
            st.session_state.validacao_final_version = None
            # st.rerun()

        if st.button("Salvar Versão Editada", key="validacao_salvar_btn_app3"):
            st.session_state.validacao_final_version = st.session_state.validacao_edited_response
            st.success("Versão editada salva.")
            st.rerun()

        if st.session_state.validacao_final_version:
            st.markdown("**Exportar Versão Salva:**")
            try:
                docx_data = gerar_docx(st.session_state.validacao_final_version)
                st.download_button(
                    label="Exportar para DOCX",
                    data=docx_data,
                    file_name="LexAutomate_Analise_Clausulas.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="validacao_export_docx_btn_app3"
                )
            except Exception as e:
                st.error(f"Erro ao gerar DOCX: {e}")
                traceback.print_exc()

    retrieved_chunks_display_validacao = st.session_state.get('last_retrieved_chunks_details_validacao', [])

    if retrieved_chunks_display_validacao:
        st.markdown("---")
        with st.expander("🔎 Detalhes dos Documentos Recuperados pelo RAG (para a última análise)", expanded=False):
            for i, chunk_info in enumerate(retrieved_chunks_display_validacao):
                arquivo_origem = chunk_info.get('arquivo_origem', 'N/A')
                score = chunk_info.get('score', None)
                reranker_score = chunk_info.get('reranker_score', None)
                semantic_caption = chunk_info.get('semantic_caption', None)
                content_preview = chunk_info.get('content_preview', 'Conteúdo não disponível.')
                chunk_id = chunk_info.get('chunk_id', f"chunk_display_validacao_expander_app3_{i}")

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
                    key=f"chunk_preview_validacao_expander_key_app3_{chunk_id}"
                )
                st.markdown("---")

