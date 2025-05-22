# app_parametrizador.py
import streamlit as st
import json
import os
import uuid # Para nomes de arquivo temporários
import traceback # Para logs de erro mais detalhados
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_response_with_conditional_google_search,
    AZURE_OPENAI_DEPLOYMENT_LLM,
    gerar_docx # Importar gerar_docx
)
# Assumindo que extrair_texto_documento está em rag_docintelligence.py e acessível
try:
    from rag_docintelligence import extrair_texto_documento
    DOC_INTELLIGENCE_AVAILABLE = True
except ImportError:
    DOC_INTELLIGENCE_AVAILABLE = False
    st.warning("Módulo rag_docintelligence.py não encontrado. A funcionalidade de anexar documento de exemplo estará desabilitada.")


# --- CONFIGURAÇÕES E CONSTANTES ---
MODELOS_PECAS_FILE = "modelos_pecas.json"

SYSTEM_PROMPT_PARAMETRIZADOR = """
Você é um assistente jurídico altamente competente, especializado na redação de petições processuais personalizadas e fundamentadas.
Sua tarefa é utilizar os parâmetros fornecidos pelo usuário, o modelo de peça selecionado e, SE FORNECIDO, o conteúdo de um DOCUMENTO DE EXEMPLO, para redigir uma peça jurídica completa, coesa, bem estruturada, e que respeite a linguagem formal, os fundamentos legais e a praxe forense.

Ao usar um DOCUMENTO DE EXEMPLO, utilize-o como referência para:
- Estilo de linguagem e formatação.
- Estrutura da peça (seções comuns, ordem dos argumentos).
- Extração de informações contextuais ou fatos relevantes que possam complementar os parâmetros fornecidos, SE PERTINENTE e SE NÃO CONTRADISSEREM as instruções explícitas do usuário.

Se um campo específico do modelo de peça não for preenchido pelo usuário (ex: [DETALHAR JORNADA HABITUAL]), indique claramente no texto gerado que aquela informação precisa ser complementada pelo usuário (ex: "[COMPLETAR COM A JORNADA HABITUAL DO RECLAMANTE]").
Priorize a clareza, a objetividade e a persuasão em sua redação.
Adapte-se ao tipo de peça e à área do direito especificadas.
"""

# --- FUNÇÕES AUXILIARES ---
@st.cache_data
def carregar_modelos_pecas(file_path: str) -> dict:
    try:
        if not os.path.exists(file_path):
            st.error(f"Arquivo de modelos '{file_path}' não encontrado. Verifique o caminho.")
            return {}
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Erro ao carregar ou processar o arquivo JSON de modelos: {e}")
        return {}

# --- INTERFACE PRINCIPAL ---
def parametrizador_interface():
    st.subheader("Geração de Peças Jurídicas Parametrizadas")
    st.markdown("Preencha os parâmetros, selecione um modelo e, opcionalmente, anexe um documento de exemplo para gerar uma petição personalizada.")
    st.markdown("---")

    modelos_data = carregar_modelos_pecas(MODELOS_PECAS_FILE)
    if not modelos_data:
        st.warning("Não foi possível carregar os modelos de peças. A funcionalidade pode estar limitada.")
        areas_disponiveis = ["Trabalhista", "Cível", "Consumidor", "Outra"]
        tipos_peca_disponiveis_fallback = ["Petição Inicial", "Contestação", "Recurso", "Outro"]
        modelos_peca_disponiveis_fallback = ["Modelo Genérico (Fallback)"]
    else:
        areas_disponiveis = list(modelos_data.keys())

    col1_selecao, col2_selecao, col3_selecao = st.columns(3)
    with col1_selecao:
        area_direito_selecionada = st.selectbox(
            "1. Grande Área do Direito:", options=areas_disponiveis, index=0, key="param_area_direito"
        )
        if area_direito_selecionada == "Outra":
            area_direito_outra = st.text_input("Especifique a Área do Direito:", key="param_area_outra")
            area_direito_final = area_direito_outra if area_direito_outra.strip() else "Outra (Não Especificada)"
        else:
            area_direito_final = area_direito_selecionada

    tipos_peca_para_area = []
    if area_direito_selecionada and area_direito_selecionada != "Outra" and area_direito_selecionada in modelos_data:
        tipos_peca_para_area = list(modelos_data[area_direito_selecionada].keys())
    elif area_direito_selecionada == "Outra":
        tipos_peca_para_area = ["Peça Jurídica Genérica"]
    if not tipos_peca_para_area and not modelos_data: # Fallback se JSON falhou
        tipos_peca_para_area = tipos_peca_disponiveis_fallback
    elif not tipos_peca_para_area:
         tipos_peca_para_area = ["Nenhum tipo de peça para esta área", "Outro"]


    with col2_selecao:
        tipo_peca_selecionado = st.selectbox(
            "2. Tipo Principal de Peça:", options=tipos_peca_para_area, index=0, key="param_tipo_peca"
        )
        if tipo_peca_selecionado == "Outro":
            tipo_peca_outro = st.text_input("Especifique o Tipo de Peça:", key="param_tipo_outro")
            tipo_peca_final = tipo_peca_outro if tipo_peca_outro.strip() else "Outra (Não Especificada)"
        else:
            tipo_peca_final = tipo_peca_selecionado

    modelos_especificos_para_tipo = []
    modelo_selecionado_info = None
    if area_direito_selecionada and tipo_peca_selecionado and \
       area_direito_selecionada in modelos_data and \
       tipo_peca_selecionado in modelos_data.get(area_direito_selecionada, {}):
        modelos_especificos_para_tipo = list(modelos_data[area_direito_selecionada][tipo_peca_selecionado].keys())
    elif area_direito_selecionada == "Outra" and tipo_peca_selecionado == "Peça Jurídica Genérica" and \
         "Outra" in modelos_data and "Peça Jurídica Genérica" in modelos_data["Outra"]:
         modelos_especificos_para_tipo = ["Peça Jurídica Genérica"]
    if not modelos_especificos_para_tipo and not modelos_data: # Fallback se JSON falhou
        modelos_especificos_para_tipo = modelos_peca_disponiveis_fallback

    with col3_selecao:
        if modelos_especificos_para_tipo:
            modelo_especifico_selecionado = st.selectbox(
                "3. Modelo/Assunto Específico da Peça:",
                options=modelos_especificos_para_tipo,
                index=0,
                key="param_modelo_especifico",
                help=modelos_data.get(area_direito_selecionada, {}).get(tipo_peca_selecionado, {}).get(modelos_especificos_para_tipo[0] if modelos_especificos_para_tipo else "", {}).get("descricao", "Selecione um modelo.")
            )
            if modelo_especifico_selecionado:
                if area_direito_selecionada == "Outra" and tipo_peca_selecionado == "Peça Jurídica Genérica":
                    modelo_selecionado_info = modelos_data.get("Outra", {}).get("Peça Jurídica Genérica", {}).get(modelo_especifico_selecionado)
                else:
                    modelo_selecionado_info = modelos_data.get(area_direito_selecionada, {}).get(tipo_peca_selecionado, {}).get(modelo_especifico_selecionado)
        else:
            st.info("Nenhum modelo específico disponível para a seleção atual.")
            modelo_especifico_selecionado = None

    st.markdown("---")
    st.markdown("#### Informações das Partes e Caso")
    autor = st.text_input("Nome da Parte Autora/Reclamante/Recorrente:", value=st.session_state.get("param_autor", "João da Silva"), key="param_autor_input")
    reu = st.text_input("Nome da Parte Ré/Reclamada/Recorrida:", value=st.session_state.get("param_reu", "Empresa XYZ Ltda."), key="param_reu_input")
    foro = st.text_input("Foro Competente:", value=st.session_state.get("param_foro", "Vara do Trabalho de Exemplo / Comarca de Exemplo"), key="param_foro_input")
    valor_causa = st.text_input("Valor da Causa (R$):", value=st.session_state.get("param_valor", "A ser calculado / 1.000,00"), key="param_valor_input")

    reivindicacoes_sugeridas_lista = []
    if modelo_selecionado_info and "reivindicacoes_comuns" in modelo_selecionado_info:
        reivindicacoes_sugeridas_lista = modelo_selecionado_info["reivindicacoes_comuns"]
    else:
        reivindicacoes_sugeridas_lista = [
            "Horas extras", "Adicional noturno", "Danos morais", "Obrigação de fazer",
            "Rescisão contratual", "Pagamento de multa", "Outro (especificar nas instruções)"
        ]

    with st.expander("Selecionar/Editar Reivindicações/Pedidos", expanded=True):
        reivindicacoes_selecionadas = st.multiselect(
            "Reivindicações / Pedidos Principais:",
            options=reivindicacoes_sugeridas_lista,
            default=st.session_state.get("param_reivindicacoes", []),
            key="param_reivindicacoes_multiselect"
        )
        pedidos_customizados_str = st.text_area(
            "Adicionar outros pedidos (um por linha):",
            value=st.session_state.get("param_pedidos_custom", ""),
            key="param_pedidos_custom_text", height=100
        )

    instrucao_adicional = st.text_area(
        "Instruções Adicionais ou Detalhes Específicos para a Peça:",
        value=st.session_state.get("param_instrucoes", ""),
        key="param_instrucoes_text", height=150,
        help="Quanto mais detalhes relevantes você fornecer, mais personalizada será a peça."
    )

    # --- ANEXAR DOCUMENTO DE EXEMPLO ---
    documento_exemplo_texto = ""
    if DOC_INTELLIGENCE_AVAILABLE:
        st.markdown("---")
        st.markdown("#### Documento de Exemplo (Opcional)")
        arquivo_exemplo = st.file_uploader(
            "Anexe um documento (PDF ou DOCX) para servir de exemplo/referência:",
            type=["pdf", "docx"],
            key="param_arquivo_exemplo"
        )

        if arquivo_exemplo:
            if 'param_texto_extraido_exemplo' not in st.session_state or \
               st.session_state.get('param_nome_arquivo_exemplo_processado') != arquivo_exemplo.name:
                try:
                    ext = os.path.splitext(arquivo_exemplo.name)[1].lower()
                    temp_file_path = f"temp_param_exemplo_{uuid.uuid4().hex}{ext}"
                    with open(temp_file_path, "wb") as f:
                        f.write(arquivo_exemplo.getvalue())
                    
                    with st.spinner(f"Extraindo texto de '{arquivo_exemplo.name}'..."):
                        texto_extraido = extrair_texto_documento(temp_file_path, ext)
                    
                    if texto_extraido:
                        st.session_state.param_texto_extraido_exemplo = texto_extraido
                        st.session_state.param_nome_arquivo_exemplo_processado = arquivo_exemplo.name
                        st.success(f"Texto extraído de '{arquivo_exemplo.name}' com sucesso!")
                    else:
                        st.warning(f"Não foi possível extrair texto de '{arquivo_exemplo.name}'.")
                        st.session_state.param_texto_extraido_exemplo = ""
                except Exception as e_extraction:
                    st.error(f"Erro ao processar o arquivo de exemplo '{arquivo_exemplo.name}': {e_extraction}")
                    traceback.print_exc()
                    st.session_state.param_texto_extraido_exemplo = ""
                finally:
                    if os.path.exists(temp_file_path):
                        try: os.remove(temp_file_path)
                        except: pass # Silenciar erro na remoção, se ocorrer
            
            documento_exemplo_texto = st.session_state.get('param_texto_extraido_exemplo', "")
            if documento_exemplo_texto:
                 with st.expander("Ver Texto Extraído do Documento de Exemplo", expanded=False):
                    st.text_area("", value=documento_exemplo_texto, height=200, disabled=True, key="param_view_texto_exemplo")
        else: # Limpa o texto se nenhum arquivo estiver carregado ou for removido
            st.session_state.param_texto_extraido_exemplo = ""
            st.session_state.param_nome_arquivo_exemplo_processado = None


    # --- BOTÃO DE GERAÇÃO ---
    st.markdown("---")
    if st.button("Gerar Petição Parametrizada", key="param_gerar_btn", type="primary"):
        if not modelo_selecionado_info and not (area_direito_selecionada == "Outra" and tipo_peca_selecionado == "Peça Jurídica Genérica"):
            st.error("Por favor, selecione um modelo de peça válido ou configure a opção 'Outra'.")
            st.stop()

        client_openai = get_openai_client()
        search_client = get_azure_search_client()
        if not client_openai or not search_client:
            st.error("Falha ao inicializar serviços de IA. Verifique as configurações.")
            st.stop()

        pedidos_finais = list(reivindicacoes_selecionadas)
        if pedidos_customizados_str.strip():
            pedidos_finais.extend([p.strip() for p in pedidos_customizados_str.split('\n') if p.strip()])
        reivindicacoes_formatadas_texto = ", ".join(pedidos_finais) if pedidos_finais else "(Pedidos não especificados ou a serem detalhados)"

        prompt_para_llm = ""
        prompt_template_usado = ""

        if modelo_selecionado_info and "prompt_template" in modelo_selecionado_info:
            prompt_template_usado = modelo_selecionado_info["prompt_template"]
        elif area_direito_selecionada == "Outra" and tipo_peca_selecionado == "Peça Jurídica Genérica": # Trata caso de "Outra"
            prompt_template_usado = modelos_data.get("Outra", {}).get("Peça Jurídica Genérica", {}).get("prompt_template", "")
        
        if prompt_template_usado:
            prompt_para_llm = prompt_template_usado.format(
                autor=autor, reu=reu, foro=foro, valor=valor_causa,
                reivindicacoes_formatadas=reivindicacoes_formatadas_texto,
                instrucao_adicional=instrucao_adicional if instrucao_adicional.strip() else "[Nenhuma instrução adicional específica fornecida pelo usuário]",
                tipo_peca_outro=tipo_peca_final, # Usado pelo template genérico de "Outra"
                area_direito_outro=area_direito_final, # Usado pelo template genérico de "Outra"
                # Adicionar o texto do documento de exemplo ao format, caso o template tenha o placeholder
                # Exemplo de placeholder no template: {documento_exemplo_para_referencia}
                # Se não houver placeholder específico, a função generate_response_... já usa context_document_text
                documento_exemplo_para_referencia=documento_exemplo_texto if documento_exemplo_texto else "[Nenhum documento de exemplo fornecido]"
            )
        else:
            st.warning("Template de prompt não encontrado. Usando prompt genérico.")
            prompt_para_llm = f"""
            Gere uma {tipo_peca_final.lower()} na área do Direito {area_direito_final.lower()}, com os seguintes parâmetros:
            - Parte autora: {autor}
            - Parte ré: {reu}
            - Foro competente: {foro}
            - Valor da causa: R$ {valor_causa}
            - Reivindicações/Pedidos: {reivindicacoes_formatadas_texto}
            {f'- Instruções adicionais: {instrucao_adicional}' if instrucao_adicional.strip() else ''}
            {f'- Basear-se também no seguinte documento de exemplo: {documento_exemplo_texto}' if documento_exemplo_texto else ''}
            Por favor, siga a estrutura formal de uma peça jurídica.
            """
        
        # Atualizar session_state com os valores atuais para persistência
        st.session_state.update({
            "param_autor": autor, "param_reu": reu, "param_foro": foro, "param_valor": valor_causa,
            "param_reivindicacoes": reivindicacoes_selecionadas,
            "param_pedidos_custom": pedidos_customizados_str, "param_instrucoes": instrucao_adicional
        })

        with st.spinner("LexAutomate está redigindo a peça com base nos seus parâmetros e exemplo (se houver)..."):
            try:
                resposta_llm = generate_response_with_conditional_google_search(
                    system_message_base=SYSTEM_PROMPT_PARAMETRIZADOR,
                    user_instruction=prompt_para_llm,
                    context_document_text=documento_exemplo_texto, # Passa o texto do doc de exemplo aqui!
                    search_client=search_client,
                    client_openai=client_openai,
                    azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,
                    azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM,
                    top_k_initial_search_azure=7, 
                    use_semantic_search_azure=True, # Desabilitar buscas RAG
                    enable_google_search_trigger=True, temperature=0.3, max_tokens=4000
                )
                resposta_formatada = str(resposta_llm).strip()
                st.session_state.peticao_parametrizada_gerada = resposta_formatada
            except Exception as e:
                st.error(f"Ocorreu um erro ao gerar a petição: {e}")
                st.session_state.peticao_parametrizada_gerada = None
                traceback.print_exc()

    if 'peticao_parametrizada_gerada' in st.session_state and st.session_state.peticao_parametrizada_gerada:
        st.markdown("---")
        st.markdown("### Petição Gerada:")
        texto_editado = st.text_area(
            "Revise e edite a petição abaixo:",
            value=st.session_state.peticao_parametrizada_gerada,
            height=600, key="param_editor_peticao"
        )
        st.session_state.peticao_parametrizada_gerada = texto_editado # Atualiza com edições

        # Download em DOCX como principal
        try:
            nome_arquivo_base = f"peticao_{area_direito_final.lower().replace(' ', '_').replace('/', '_')}_{tipo_peca_final.lower().replace(' ', '_').replace('/', '_')}"
            docx_bytes = gerar_docx(st.session_state.peticao_parametrizada_gerada)
            st.download_button(
                label="📥 Baixar Petição em DOCX",
                data=docx_bytes,
                file_name=f"{nome_arquivo_base}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="param_download_docx_btn",
                type="primary" # Botão primário
            )
        except Exception as e_docx:
            st.error(f"Erro ao gerar DOCX: {e_docx}")

        # Opção de download em TXT (secundária, pode ser em um expander ou menor)
        with st.expander("Opções adicionais de download"):
             st.download_button(
                label="Baixar em TXT",
                data=st.session_state.peticao_parametrizada_gerada,
                file_name=f"{nome_arquivo_base}.txt",
                mime="text/plain",
                key="param_download_txt_btn"
            )