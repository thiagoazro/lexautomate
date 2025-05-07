# app3.py (com múltiplos arquivos para análise de cláusulas contratuais)
import streamlit as st
import os
from rag_docintelligence import extrair_texto_documento
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_response_with_rag,
    gerar_docx
)

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
        key="validacao_uploader_multi"
    )

    # Inicialização de estado
    if 'validacao_multi_texto_extraido' not in st.session_state:
        st.session_state.validacao_multi_texto_extraido = ""
    if 'validacao_rag_response' not in st.session_state:
        st.session_state.validacao_rag_response = None
    if 'validacao_edited_response' not in st.session_state:
        st.session_state.validacao_edited_response = None
    if 'validacao_final_version' not in st.session_state:
        st.session_state.validacao_final_version = None

    if uploaded_files and not st.session_state.validacao_multi_texto_extraido:
        textos = []
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_path = f"temp_validacao_{file.file_id}{ext}"
            try:
                with open(temp_path, "wb") as f:
                    f.write(file.getvalue())
                with st.spinner(f"Extraindo texto de {file.name}..."):
                    texto = extrair_texto_documento(temp_path, ext)
                if texto:
                    textos.append(f"---\n**{file.name}**\n\n{texto}")
            except Exception as e:
                st.error(f"Erro ao processar {file.name}: {e}")
            finally:
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except Exception: pass

        st.session_state.validacao_multi_texto_extraido = "\n\n".join(textos)
        st.success("Textos extraídos com sucesso.")
        st.rerun()

    if st.session_state.validacao_multi_texto_extraido:
        with st.expander("Ver Texto Extraído", expanded=False):
            st.text_area("Texto Completo:", st.session_state.validacao_multi_texto_extraido, height=200, key="validacao_texto_view", disabled=True)

        st.markdown("---")
        st.markdown("### 2. Geração da Análise com IA")
        prompt_validacao = st.text_area(
            "Especifique a cláusula ou ponto para análise/validação:",
            placeholder="Ex: Analise a Cláusula 5 (Multa Contratual) e verifique sua conformidade.",
            height=100,
            key="prompt_validacao_input"
        )

        if st.button("Analisar/Validar Cláusulas", key="validacao_gerar_btn"):
            if not prompt_validacao.strip():
                st.warning("Por favor, digite a instrução para a análise.")
            else:
                with st.spinner("Analisando..."):
                    try:
                        system_message_validacao = """Você é um(a) advogado(a) consultor(a), especialista em análise contratual e gestão de riscos, com foco em Direito Brasileiro na área do direito referente ao objeto principal do contrato em análise.
Sua tarefa é analisar especificamente a cláusula ou o ponto do contrato indicado pelo usuário, à luz da legislação e jurisprudência predominante no Brasil.
Utilize o CONTEXTO recuperado da base de conhecimento jurídica para embasar sua análise sobre validade, legalidade, abusividade, omissões ou riscos associados à cláusula/ponto em questão.
Estruture sua resposta de forma clara, separando os pontos principais da análise.

**Formatação Importante:** Utilize Markdown para formatar a resposta. Use **negrito** (asteriscos duplos, como em `**Análise da Validade**` ou `**Pontos de Atenção**`) para os títulos dos principais tópicos da sua análise. Certifique-se de incluir uma linha em branco *antes* e *depois* de cada título em negrito para garantir um espaçamento adequado em relação ao texto do parágrafo. O texto dentro de cada tópico deve ser corrido, sem outra formatação Markdown, a menos que estritamente necessário para clareza. Seja objetivo e fundamente sua resposta."""
                        resposta_rag = generate_response_with_rag(
                            system_message=system_message_validacao,
                            user_instruction=prompt_validacao,
                            context_document_text=st.session_state.validacao_multi_texto_extraido,
                            search_client=search_client,
                            client_openai=client_openai,
                            top_k_chunks=5
                        )
                        st.session_state.validacao_rag_response = resposta_rag
                        st.session_state.validacao_edited_response = str(resposta_rag).strip() if resposta_rag else ""
                        st.session_state.validacao_final_version = None
                        st.success("Rascunho da análise gerado. Revise e edite abaixo.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ocorreu um erro ao realizar a análise: {e}")
                        st.session_state.validacao_rag_response = None
                        st.session_state.validacao_edited_response = None

    if st.session_state.validacao_edited_response:
        st.markdown("---")
        st.markdown("### 3. Revisão, Edição e Exportação")
        st.markdown("#### Pré-visualização da Análise Formatada:")
        with st.container(border=True):
            st.markdown(st.session_state.validacao_edited_response)

        edited_text = st.text_area(
            "Edite a análise gerada (use `**texto**` para negrito):",
            value=st.session_state.validacao_edited_response,
            height=400,
            key="validacao_editor_multi"
        )

        if edited_text != st.session_state.validacao_edited_response:
            st.session_state.validacao_edited_response = edited_text
            st.session_state.validacao_final_version = None
            st.rerun()

        if st.button("Salvar Versão Editada", key="validacao_salvar_btn"):
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
                    file_name="LexAutomate_Analise_Clausulas_Multidoc.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="validacao_export_docx_btn"
                )
            except Exception as e:
                st.error(f"Erro ao gerar DOCX: {e}")
