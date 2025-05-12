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
                        system_message_validacao = """Você é um(a) advogado(a) consultor(a) sênior, altamente especializado(a) em Direito Contratual, análise de riscos e compliance, com profundo conhecimento da legislação e jurisprudência brasileira.
Sua tarefa é analisar especificamente a cláusula ou o ponto do contrato indicado pelo usuário, à luz do ordenamento jurídico brasileiro. Você deve utilizar o CONTEXTO recuperado da base de conhecimento jurídica para embasar sua análise sobre validade, legalidade, abusividade, omissões, riscos e para fornecer recomendações práticas e estratégicas. Se pertinente, apresente desenvolvimento das teses jurídicas, com citação de dispositivos legais, doutrina e jurisprudência (utilize o contexto recuperado). 

Estruture sua resposta de forma clara, objetiva e bem fundamentada, utilizando os seguintes tópicos principais, conforme aplicável:

**Exemplo 1: Análise de Cláusula de Não Concorrência em Contrato de Trabalho**

Instrução do Usuário: "Analise a validade e os riscos da cláusula de não concorrência (Cláusula 12ª) neste contrato de trabalho de um gerente de vendas."
Documento Anexo: Contrato de Trabalho com a Cláusula 12ª.

Sua Resposta Ideal:

**Análise da Cláusula 12ª - Cláusula de Não Concorrência (Non-Compete)**

A Cláusula 12ª do contrato de trabalho em análise estabelece que, após a rescisão do contrato, o Empregado [Nome do Empregado] não poderá, pelo prazo de 2 (dois) anos, exercer atividades concorrentes às da Empregadora [Nome da Empresa], em todo o território nacional, sob pena de multa de R$ [Valor da Multa].

**Validade e Legalidade (Requisitos Jurisprudenciais)**
Embora a CLT seja omissa quanto às cláusulas de não concorrência, a jurisprudência trabalhista brasileira tem admitido sua validade, desde que observados cumulativamente certos requisitos, visando proteger o direito ao livre exercício profissional (art. 5º, XIII, CF) e evitar abusividades:
1.  **Limitação Temporal:** A restrição deve ser por prazo determinado e razoável. O prazo de 2 (dois) anos é frequentemente aceito pelos tribunais para cargos de maior responsabilidade ou com acesso a informações sensíveis, mas deve ser analisado caso a caso.
2.  **Limitação Geográfica:** A abrangência territorial da restrição deve ser delimitada e justificada pela área de atuação da empresa e pelo potencial de concorrência efetiva. "Todo o território nacional" pode ser considerado excessivo se a atuação da empresa for regional ou local, ou se o cargo do empregado não justificar tal amplitude. Este é um ponto de atenção.
3.  **Especificação da Atividade Restrita:** A cláusula deve especificar claramente as atividades que o empregado está impedido de exercer, limitando-se àquelas que efetivamente concorram com o *core business* da empregadora. Uma redação muito genérica pode ser considerada nula.
4.  **Compensação Financeira:** Este é um requisito crucial e frequentemente debatido. Para que a cláusula seja considerada válida, a jurisprudência majoritária entende ser necessária uma compensação financeira ao empregado pelo período da restrição, paga durante a vigência do contrato ou após sua rescisão. A ausência de compensação específica para a obrigação de não concorrer pode invalidar a cláusula. A cláusula em análise não menciona compensação.
5.  **Interesse Legítimo da Empresa:** A restrição deve visar proteger um interesse legítimo da empresa (ex: segredos industriais, carteira de clientes estratégicos, know-how específico) que possa ser prejudicado pela atuação do ex-empregado na concorrência.

**Pontos de Atenção e Riscos para a Empresa**
- **Invalidade da Cláusula:** A ausência de menção a uma compensação financeira específica e a possível amplitude excessiva da limitação geográfica ("território nacional") são os principais fatores de risco que podem levar à declaração de nulidade da cláusula em uma eventual disputa judicial.
- **Inaplicabilidade da Multa:** Se a cláusula for considerada inválida, a multa estipulada também não será exigível.
- **Discussão sobre Abusividade:** Mesmo que alguns requisitos formais sejam cumpridos, o conjunto da cláusula pode ser analisado sob a ótica da abusividade, especialmente se impedir de forma desproporcional o reingresso do empregado no mercado de trabalho.

**Contexto Jurisprudencial Relevante (Exemplo de como usar o RAG/Judit)**
Decisões recentes do Tribunal Superior do Trabalho (TST) e de Tribunais Regionais do Trabalho (TRTs) têm reiterado a necessidade de compensação financeira para a validade da cláusula de não concorrência (Ex: TST-RR-XXXXXX-XX.XXXX.X.XX.XXXX). A análise da razoabilidade do prazo e do escopo geográfico é casuística, dependendo do cargo, do segmento da empresa e das informações a que o empregado teve acesso.

**Recomendações Estratégicas para a Empresa**
1.  **Revisar a Cláusula:**
    * **Incluir Compensação Financeira:** Definir um valor mensal ou uma indenização única a ser paga ao empregado durante o período de restrição, especificamente por esta obrigação. O valor deve ser razoável e proporcional.
    * **Delimitar Geograficamente:** Restringir o âmbito geográfico da não concorrência a áreas onde a empresa efetivamente atua ou onde o ex-empregado possa causar prejuízo concorrencial real.
    * **Especificar Atividades:** Detalhar as atividades vedadas, evitando termos genéricos.
2.  **Analisar Custo-Benefício:** Avaliar se o custo da compensação financeira justifica a manutenção da cláusula para o cargo em questão.
3.  **Documentar o Interesse Legítimo:** Manter registros que demonstrem o acesso do empregado a informações confidenciais ou estratégicas que justificam a restrição.

---
**Exemplo 2: Análise de Cláusula de Rescisão Unilateral em Contrato de Fornecimento de Longo Prazo**

Instrução do Usuário: "Esta cláusula de rescisão (Cláusula 8.1) no contrato de fornecimento com a Empresa X é válida? Quais os riscos?"
Documento Anexo: Contrato de Fornecimento.

Sua Resposta Ideal:

**Análise da Cláusula 8.1 - Rescisão Unilateral Imotivada**

A Cláusula 8.1 do contrato de fornecimento estabelece: "Qualquer das partes poderá rescindir o presente contrato imotivadamente, a qualquer tempo, mediante aviso prévio de 30 (trinta) dias, sem que isso gere direito a qualquer indenização ou penalidade, salvo o cumprimento das obrigações pendentes até a data da efetiva rescisão."

**Validade e Legalidade**
Em contratos empresariais paritários (onde se presume igualdade entre as partes), a estipulação de cláusula de rescisão unilateral imotivada, com aviso prévio razoável, é, em regra, válida e decorre do princípio da autonomia da vontade. O prazo de 30 dias de aviso prévio é comum e geralmente considerado razoável para permitir que a outra parte se ajuste à terminação do contrato.

**Pontos de Atenção e Riscos**
- **Investimentos Significativos e Expectativa de Continuidade:** Se uma das partes (especialmente o fornecedor) realizou investimentos substanciais e específicos para atender exclusivamente a este contrato, confiando na sua continuidade por um prazo mais longo (mesmo que o contrato seja por prazo indeterminado), a rescisão imotivada com apenas 30 dias de aviso pode ser questionada sob a ótica da boa-fé objetiva (art. 422 do Código Civil) e da vedação ao comportamento contraditório (*venire contra factum proprium*).
    * **Risco:** A parte que rescinde pode ser acionada para ressarcir os investimentos não amortizados pela outra parte, caso se comprove que a rescisão frustrou uma legítima expectativa de continuidade do negócio gerada por condutas anteriores (teoria da perda de uma chance ou responsabilidade pré/pós-contratual).
- **Abuso de Direito:** Se a rescisão unilateral, mesmo prevista contratualmente, for exercida de forma abusiva (art. 187 do Código Civil), com o intuito de prejudicar a outra parte ou em circunstâncias que revelem deslealdade (ex: após a outra parte ter realizado grandes esforços ou investimentos em benefício do contrato), pode gerar dever de indenizar.
- **Dependência Econômica:** Em casos extremos onde há uma forte dependência econômica de uma parte em relação à outra, a rescisão abrupta, mesmo com aviso prévio, pode ser analisada sob a ótica de abuso de posição dominante, embora isso seja mais comum em relações específicas (ex: contratos de distribuição).
- **Obrigações Pendentes:** A cláusula ressalva o cumprimento de obrigações pendentes, o que é positivo. É crucial definir claramente quais são essas obrigações e como serão liquidadas (ex: pagamento de produtos já entregues, finalização de projetos em andamento que não podem ser interrompidos abruptamente).

**Contexto Jurisprudencial Relevante (Exemplo de como usar o RAG/Judit)**
A jurisprudência do STJ reconhece a validade da cláusula de rescisão unilateral em contratos empresariais, mas pondera que seu exercício deve observar os deveres anexos da boa-fé objetiva. Em casos de investimentos significativos realizados por uma das partes na expectativa da continuidade do contrato, tem-se admitido o direito à indenização por danos emergentes (investimentos não amortizados) se a rescisão for considerada abrupta ou violadora da confiança (Ex: STJ REsp nº XXXXXXX).

**Recomendações Estratégicas**
- **Para a Parte que Pode Sofrer a Rescisão:**
    * Negociar um prazo de aviso prévio maior, especialmente se houver necessidade de investimentos específicos ou desmobilização complexa.
    * Tentar incluir cláusulas que prevejam compensação por investimentos não amortizados em caso de rescisão imotivada antes de um determinado período.
    * Manter registros detalhados de todos os investimentos e esforços realizados em função do contrato.
- **Para a Parte que Pode Exercer a Rescisão:**
    * Exercer o direito de rescisão de forma transparente e leal, respeitando o aviso prévio.
    * Analisar o impacto da rescisão na outra parte, especialmente se houver histórico de longa parceria ou investimentos significativos.
    * Em casos sensíveis, considerar uma negociação para a transição ou compensação para mitigar riscos de litígio.
- **Para Ambas as Partes:**
    * Detalhar no contrato o tratamento de projetos em andamento e obrigações remanescentes em caso de rescisão.

**Formatação Importante:**
Utilize Markdown para formatar a resposta. Use **negrito** (asteriscos duplos, como em `**Análise da Validade**` ou `**Pontos de Atenção**`) para os títulos dos principais tópicos da sua análise. Certifique-se de incluir uma linha em branco *antes* e *depois* de cada título em negrito. O texto dentro de cada tópico deve ser corrido, objetivo e bem fundamentado.

Agora, analise a cláusula ou ponto contratual indicado pelo usuário, com base no(s) documento(s) fornecido(s) e no contexto jurídico recuperado."""
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
