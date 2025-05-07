# app.py (versão com múltiplos documentos para resumo jurídico)
import streamlit as st
import os
from rag_docintelligence import extrair_texto_documento
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_response_with_rag,
    gerar_docx
)

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

    if 'resumo_multi_texto_extraido' not in st.session_state:
        st.session_state.resumo_multi_texto_extraido = ""
    if 'resumo_rag_response' not in st.session_state:
        st.session_state.resumo_rag_response = None
    if 'resumo_edited_response' not in st.session_state:
        st.session_state.resumo_edited_response = None
    if 'resumo_final_version' not in st.session_state:
        st.session_state.resumo_final_version = None

    if uploaded_files and not st.session_state.resumo_multi_texto_extraido:
        textos = []
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_path = f"temp_resumo_multi_{file.file_id}{ext}"
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

        st.session_state.resumo_multi_texto_extraido = "\n\n".join(textos)
        st.success("Textos extraídos com sucesso.")
        st.rerun()

    if st.session_state.resumo_multi_texto_extraido:
        with st.expander("Ver Texto Extraído Consolidado", expanded=False):
            st.text_area("Texto Completo:", st.session_state.resumo_multi_texto_extraido, height=200, disabled=True)

        st.markdown("---")
        st.markdown("### 2. Geração do Rascunho com IA")
        prompt_resumo = st.text_area (
    "Direcione o resumo (opcional - Deixe em branco para resumo padrão):",
    placeholder="Ex: Gere um resumo da cláusula de penalidades.\n"
                "Ex: Para cada contrato anexado, gere um resumo com o nome das partes e as obrigações principais.",
    height=100,
    key="prompt_resumo_input"
)

        if st.button("Gerar Resumo com RAG", key="resumo_gerar_btn"):
            user_instruction = prompt_resumo.strip() if prompt_resumo.strip() else "Gerar um resumo padrão do documento, destacando os pontos chave conforme a estrutura solicitada."
            with st.spinner("Gerando resumo..."):
                try:
                    system_message_resumo = """Você é um assistente jurídico altamente qualificado, especialista em análise e resumo de contratos.
Seu objetivo é extrair as informações essenciais do contrato fornecido, utilizando o CONTEXTO recuperado da base de conhecimento para complementar ou validar informações quando relevante.
Se o usuário der uma instrução específica, foque nela. Caso contrário, forneça um resumo padrão estruturado com os seguintes tópicos principais:
- Partes Contratantes
- Objeto Principal do Contrato
- Principais Obrigações
- Prazos Relevantes
- Preço e Forma de Pagamento
- Multas e Penalidades
- Rescisão/Extinção
- Foro de Eleição

**Formatação Importante:** Utilize Markdown para formatar a resposta. Use **negrito** (asteriscos duplos, como em `**Título Principal**`) para todos os títulos dos tópicos listados acima. Certifique-se de incluir uma linha em branco *antes* e *depois* de cada título em negrito para garantir um espaçamento adequado em relação ao texto do parágrafo. O texto dentro de cada tópico deve ser corrido, sem outra formatação Markdown, a menos que estritamente necessário para clareza. Baseie-se primariamente no documento fornecido, usando o contexto recuperado como apoio."""
                    resposta_rag = generate_response_with_rag(
                        system_message=system_message_resumo,
                        user_instruction=user_instruction,
                        context_document_text=st.session_state.resumo_multi_texto_extraido,
                        search_client=search_client,
                        client_openai=client_openai,
                        top_k_chunks=5
                    )
                    st.session_state.resumo_rag_response = resposta_rag
                    st.session_state.resumo_edited_response = str(resposta_rag).strip() if resposta_rag is not None else ""
                    st.session_state.resumo_final_version = None
                    st.success("Rascunho gerado. Revise, edite e confira a formatação abaixo.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ocorreu um erro ao gerar o resumo: {e}")
                    st.session_state.resumo_rag_response = None
                    st.session_state.resumo_edited_response = None

    if st.session_state.resumo_edited_response is not None:
        st.markdown("---")
        st.markdown("### 3. Revisão, Edição e Exportação")
        st.markdown("#### Pré-visualização do Documento Formatado:")
        preview_text_app1 = st.session_state.get('resumo_edited_response',"")
        if not isinstance(preview_text_app1, str): preview_text_app1 = str(preview_text_app1)
        with st.container(border=True):
            st.markdown(preview_text_app1)
        st.markdown("---")
        edited_text_from_area = st.text_area(
            "Edite o texto abaixo (use `**texto**` para negrito):",
            value=st.session_state.resumo_edited_response,
            height=400,
            key="resumo_editor_multi"
        )
        if edited_text_from_area != st.session_state.resumo_edited_response:
            st.session_state.resumo_edited_response = edited_text_from_area
            st.session_state.resumo_final_version = None
            st.rerun()
        if st.button("Salvar Versão Editada", key="resumo_salvar_btn"):
            st.session_state.resumo_final_version = st.session_state.resumo_edited_response
            st.success("Versão editada salva.")
            st.rerun()
        if st.session_state.resumo_final_version is not None:
            st.markdown("**Exportar Versão Salva:**")
            final_text_to_export = st.session_state.resumo_final_version
            file_basename = f"LexAutomate_Resumo_Multidoc"
            try:
                docx_data = gerar_docx(final_text_to_export)
                st.download_button(
                    label="Exportar para DOCX", 
                    data=docx_data, 
                    file_name=f"{file_basename}.docx", 
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                    key="resumo_export_docx_btn"
                )
            except Exception as e: 
                st.error(f"Erro ao gerar DOCX: {e}")
                st.exception(e)
