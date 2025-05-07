# app2.py (com múltiplos arquivos, mantendo prompt e placeholder originais)
import streamlit as st
import os
from rag_docintelligence import extrair_texto_documento
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_response_with_rag,
    gerar_docx
)

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
        key="peticao_multi_uploader"
    )

    if 'peticao_multi_texto_extraido' not in st.session_state:
        st.session_state.peticao_multi_texto_extraido = ""
    if 'peticao_rag_response' not in st.session_state:
        st.session_state.peticao_rag_response = ""
    if 'peticao_edited_response' not in st.session_state:
        st.session_state.peticao_edited_response = ""
    if 'peticao_final_version' not in st.session_state:
        st.session_state.peticao_final_version = None

    if uploaded_files and not st.session_state.peticao_multi_texto_extraido:
        textos = []
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_path = f"temp_multi_{file.file_id}{ext}"
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

        st.session_state.peticao_multi_texto_extraido = "\n\n".join(textos)
        st.success("Textos extraídos com sucesso.")
        st.rerun()

    if st.session_state.peticao_multi_texto_extraido:
        with st.expander("Ver Texto Extraído Consolidado", expanded=False):
            st.text_area("Texto Extraído:", st.session_state.peticao_multi_texto_extraido, height=200, disabled=True)

        st.markdown("---")
        st.markdown("### 2. Geração do Rascunho com IA")

        prompt = st.text_area(
            "2. Instrução para a IA (opcional):",
            placeholder=(
                "Escreva aqui instruções específicas para a peça jurídica a ser gerada.\n\n"
                "Você pode, por exemplo, indicar o tipo de peça desejada (petição inicial, contestação etc.), "
                "a área do Direito (trabalhista, cível, consumidor etc.), e, se desejar, referenciar um modelo "
                "a ser seguido.\n\n"
                "Exemplo: Elabore uma petição inicial trabalhista defendendo os interesses da parte autora, conforme os "
                "fatos descritos no documento enviado. Utilize a estrutura do modelo X como referência."
            ),
            height=120
        )

        if st.button("Gerar Peça Processual"):
            if not st.session_state.peticao_multi_texto_extraido.strip():
                st.warning("Texto extraído ausente.")
            else:
                with st.spinner("Gerando rascunho..."):
                    try:
                        system_prompt =  """Você é um(a) advogado(a) altamente qualificado(a), com especialização na área do Direito correspondente ao tema central do documento analisado. Sua expertise inclui a elaboração de diversas peças processuais e extraprocessuais, com base na legislação e jurisprudência predominantes no ordenamento jurídico brasileiro.

Sua tarefa é redigir uma **peça jurídica completa**, com base no conteúdo do documento fornecido e no CONTEXTO recuperado da base de conhecimento jurídica. Se o usuário especificar o tipo de peça (como petição inicial, contestação, recurso, manifestação etc.), siga essa instrução. Caso contrário, identifique a peça jurídica mais adequada com base nos fatos, fundamentos e contexto.

**Quando possível**, utilize a **estrutura sugerida pelo próprio modelo ou indicada pelo usuário**. Se nenhuma estrutura for especificada, adote uma estrutura formal padrão da prática forense brasileira, com seções apropriadas para a peça em questão.

As seções mais comuns nas peças jurídicas são:

- **Endereçamento**
- **Qualificação das Partes**
- **Dos Fatos**
- **Do Direito**
- **Dos Pedidos**
- **Protesta por Provas**
- **Valor da Causa**
- **Termos Finais**
- **Na petição inicial e nos recursos, no final de cada tópico do fundamentos de direito, já faça um pedido de provimento do referido tópico, que irá ser repetido no tópico dos pedidos**


Em cada uma dessas seções, elabore os conteúdos de forma coesa, fundamentada, mantendo uma estrutura organizada e clara para leitura jurídica.

**Formatação Importante:** Utilize Markdown para formatar a resposta. Use **negrito** (com dois asteriscos antes e depois, como em `**Dos Fatos**`) nos títulos das seções.

Inclua **uma linha em branco antes e depois de cada título** para garantir que o Markdown seja renderizado corretamente.

Exemplo de formatação correta:

**Dos Fatos**

A parte autora foi admitida em...

Seja objetivo, juridicamente rigoroso e produza um documento pronto para ser revisado e eventualmente assinado."""

                        resposta = generate_response_with_rag(
                            system_message=system_prompt,
                            user_instruction=prompt.strip() if prompt.strip() else "",
                            context_document_text=st.session_state.peticao_multi_texto_extraido,
                            search_client=search_client,
                            client_openai=client_openai,
                            top_k_chunks=7
                        )
                        resposta = str(resposta).strip()
                        st.session_state.peticao_rag_response = resposta
                        st.session_state.peticao_edited_response = resposta
                        st.session_state.peticao_final_version = None
                        st.success("Peça gerada.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro na geração: {e}")
                        st.session_state.peticao_rag_response = ""
                        st.session_state.peticao_edited_response = ""

    texto_preview = st.session_state.get('peticao_edited_response', "").strip()
    if texto_preview:
        st.markdown("---")
        st.markdown("### 3. Revisão, Edição e Exportação")

        st.markdown("#### Pré-visualização da Peça:")
        with st.container(border=True):
            st.markdown(texto_preview, unsafe_allow_html=True)

        st.markdown("---")
        texto_editado = st.text_area(
            "Edite a peça gerada (Markdown):",
            value=texto_preview,
            height=600,
            key="peticao_multi_editor"
        )

        if texto_editado != st.session_state.peticao_edited_response:
            st.session_state.peticao_edited_response = texto_editado
            st.session_state.peticao_final_version = None
            st.rerun()

        if st.button("Salvar Versão Editada"):
            st.session_state.peticao_final_version = st.session_state.peticao_edited_response
            st.success("Versão salva.")
            st.rerun()

        if st.session_state.peticao_final_version:
            try:
                docx_data = gerar_docx(st.session_state.peticao_final_version)
                st.download_button(
                    label="Baixar DOCX",
                    data=docx_data,
                    file_name="LexAutomate_Peticao_Multipla.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            except Exception as e:
                st.error(f"Erro ao gerar DOCX: {e}")
