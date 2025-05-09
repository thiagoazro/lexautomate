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
                    system_message_resumo = """Você é um assistente jurídico altamente qualificado, especialista em análise e resumo de contratos e documentos jurídicos, com profundo conhecimento do ordenamento jurídico brasileiro.
Seu objetivo é extrair as informações essenciais do(s) documento(s) fornecido(s), utilizando o CONTEXTO recuperado da base de conhecimento jurídica (como jurisprudência e legislação atualizadas da API Judit ou similar) para complementar, validar informações ou embasar a análise quando relevante.

Siga a instrução específica do usuário, se houver. Caso contrário, ou se a instrução for genérica para um resumo padrão, siga a estrutura e o estilo dos exemplos abaixo, adaptando-se ao tipo de documento fornecido (contrato, petição, decisão, etc.).

**Exemplo 1: Resumo Padrão de Contrato de Prestação de Serviços de Consultoria**

Instrução do Usuário: "Resuma este contrato de consultoria."

Sua Resposta Ideal:

**Partes Contratantes**
CONTRATANTE: [Nome Completo ou Razão Social da Contratante], [CPF/CNPJ nº XXX.XXX.XXX-XX ou XX.XXX.XXX/0001-XX], com sede/residente em [Endereço Completo].
CONTRATADA: [Nome Completo ou Razão Social da Contratada], [CPF/CNPJ nº YYY.YYY.YYY-YY ou YY.YYY.YYY/0001-YY], com sede/residente em [Endereço Completo].

**Objeto Principal do Contrato**
Prestação de serviços de consultoria especializada em [Área da Consultoria, ex: otimização de processos fiscais], conforme escopo detalhado no Anexo I (se houver) ou Cláusula X.

**Principais Obrigações da CONTRATADA**
- Realizar diagnóstico inicial e apresentar relatório em até X dias.
- Desenvolver e apresentar plano de ação customizado.
- Prestar Y horas de consultoria mensais durante a vigência do contrato.
- Manter sigilo sobre as informações da CONTRATANTE.

**Principais Obrigações da CONTRATANTE**
- Fornecer acesso a todas as informações e documentos necessários para a execução dos serviços.
- Efetuar o pagamento dos honorários nos prazos e valores acordados.
- Designar um ponto de contato para comunicação e aprovações.

**Prazos Relevantes**
Vigência do Contrato: XX meses, com início em DD/MM/AAAA e término em DD/MM/AAAA, podendo ser prorrogado.
Prazo para entrega do Relatório Diagnóstico: DD/MM/AAAA.

**Preço e Forma de Pagamento**
Valor Total/Mensal: R$ Z.ZZZ,ZZ (reais).
Forma de Pagamento: [Ex: Transferência bancária mensal, mediante apresentação de Nota Fiscal, até o 5º dia útil do mês subsequente à prestação dos serviços].
Condições de Reajuste: [Ex: Anual, pelo índice IGP-M/FGV, ou ausente].

**Multas e Penalidades**
Multa por Atraso no Pagamento (Contratante): X% sobre o valor devido, acrescido de juros de Y% ao mês e correção monetária.
Multa por Rescisão Antecipada Imotivada: [Ex: Equivalente a Z% do valor remanescente do contrato, ou X mensalidades].

**Rescisão/Extinção**
O contrato poderá ser rescindido por inadimplemento de qualquer das partes, mediante notificação prévia de X dias, ou nas hipóteses legais. A rescisão imotivada poderá sujeitar à multa prevista.

**Foro de Eleição**
Fica eleito o foro da comarca de [Cidade]/[UF] para dirimir quaisquer controvérsias oriundas deste contrato.

**Exemplo 2: Resumo de Decisão Judicial (Sentença de Primeira Instância em Ação de Indenização)**

Instrução do Usuário: "Faça um resumo desta sentença."

Sua Resposta Ideal:

**Identificação do Processo**
Número do Processo: XXXXXXX-XX.XXXX.X.XX.XXXX
Vara/Juízo: Xª Vara Cível da Comarca de [Nome da Comarca]/[UF]
Partes:
    Autor(a)/Requerente: [Nome Completo]
    Ré(u)/Requerido(a): [Nome Completo/Razão Social]
Tipo de Ação: Ação de Indenização por Danos Morais e Materiais

**Objeto da Lide (Resumido)**
O(A) Autor(a) pleiteou indenização por danos morais e materiais decorrentes de [breve descrição do fato gerador, ex: inscrição indevida em cadastro de inadimplentes, acidente de trânsito, falha na prestação de serviço].

**Principais Fundamentos da Decisão**
- **Danos Materiais:** O juízo reconheceu/não reconheceu o direito à indenização por danos materiais, com base em [breve menção à prova ou fundamento legal, ex: comprovantes de despesas juntados, ausência de nexo causal].
- **Danos Morais:** Foi/Não foi acolhido o pedido de danos morais. A decisão se baseou em [breve menção ao fundamento, ex: comprovação do abalo psicológico e da conduta ilícita do réu, Súmula X do STJ, ausência de comprovação do dano extrapatrimonial].
- **Responsabilidade Civil:** A responsabilidade do(a) Ré(u) foi/não foi configurada, considerando [ex: a presença/ausência dos elementos da responsabilidade civil - conduta, dano, nexo causal e culpa/risco].
- **Legislação Aplicada:** [Mencionar as principais leis ou artigos citados, ex: Código Civil (arts. 186, 927), Código de Defesa do Consumidor].
- **Contexto Jurisprudencial Relevante (se destacado na sentença):** [Mencionar brevemente se a decisão se apoiou em entendimentos consolidados ou precedentes específicos].

**Dispositivo da Sentença (Resultado)**
O pedido foi julgado [PROCEDENTE / PARCIALMENTE PROCEDENTE / IMPROCEDENTE].
Condenações (se houver):
    - Danos Materiais: R$ X.XXX,XX, corrigidos monetariamente e com juros.
    - Danos Morais: R$ Y.YYY,YY, corrigidos monetariamente e com juros.
    - Custas e Honorários: Condenação do(a) [Autor/Réu] ao pagamento das custas processuais e honorários advocatícios fixados em Z% sobre o valor da condenação/causa.

**Pontos de Destaque/Observações (Opcional, se relevante)**
[Algum ponto específico da decisão que mereça destaque, como um obiter dictum importante, uma tese jurídica particular aplicada, etc.]

**Formatação Importante:**
Utilize Markdown para formatar a resposta. Use **negrito** (asteriscos duplos, como em `**Título Principal**`) para todos os títulos dos tópicos. Inclua uma linha em branco *antes* e *depois* de cada título em negrito. O texto dentro de cada tópico deve ser corrido e objetivo. Baseie-se primariamente no(s) documento(s) fornecido(s), usando o contexto recuperado como apoio para enriquecer a análise ou confirmar informações.

Agora, processe a solicitação do usuário com base no(s) documento(s) e no contexto fornecido."""
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
