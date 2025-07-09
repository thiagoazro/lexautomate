# app5.py (Geração de Peças Jurídicas Parametrizadas lendo do MongoDB e URLs da Sidebar Global)
import streamlit as st
import os
import uuid
import traceback
from string import Formatter
from collections import defaultdict

# Importa utilitários RAG
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_response_with_conditional_google_search,
    AZURE_OPENAI_DEPLOYMENT_LLM,
    gerar_docx,
    salvar_feedback_rag
)
# Importa utilitários Chroma
from chroma_utils import obter_contexto_relevante_de_url
# Importa utilitários de banco de dados
from db_utils import carregar_modelos_pecas_from_mongodb # Importa a função para carregar modelos do MongoDB

# Tenta importar o módulo de inteligência de documentos
try:
    from rag_docintelligence import extrair_texto_documento
    DOC_INTELLIGENCE_AVAILABLE = True
except ImportError:
    DOC_INTELLIGENCE_AVAILABLE = False
    st.warning("Módulo 'rag_docintelligence.py' não encontrado. A funcionalidade de anexar documento de exemplo estará desabilitada.")

# --- CONFIGURAÇÕES E CONSTANTES ---
PROMPT_PARAMETRIZADOR_FILE = "prompts/system_prompt_app5_parametrizador.md"
# Sufixo para chaves de session_state desta aba, para evitar colisões
SESSION_STATE_SUFFIX = "_app5_parametrizador" # Renomeado para maior clareza

def carregar_prompt_parametrizador(prompt_path: str = PROMPT_PARAMETRIZADOR_FILE) -> str:
    """
    Carrega o system prompt específico para a funcionalidade de parametrizador.
    Prioriza o caminho relativo ao diretório pai, depois ao diretório atual.
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Tenta carregar do diretório pai (ex: prompts/system_prompt_app5_parametrizador.md)
        full_prompt_path = os.path.join(current_dir, "..", prompt_path)
        if not os.path.exists(full_prompt_path):
            # Se não encontrar, tenta carregar do diretório atual
            full_prompt_path = os.path.join(current_dir, prompt_path)
        
        with open(full_prompt_path, "r", encoding="utf-8") as f:
            print(f"INFO APP5 (Parametrizador): Prompt carregado de: {full_prompt_path}")
            return f.read()
    except FileNotFoundError:
        st.error(f"Erro: O arquivo de prompt '{prompt_path}' não foi encontrado em '{full_prompt_path}'.")
        return "Você é um assistente jurídico especializado em criar peças processuais detalhadas e bem fundamentadas."
    except Exception as e:
        st.error(f"Erro ao carregar o prompt do parametrizador de '{prompt_path}': {e}. Usando prompt padrão.")
        traceback.print_exc()
        return "Você é um assistente jurídico especializado em criar peças processuais detalhadas e bem fundamentadas."

def inicializar_session_state():
    """Inicializa as chaves necessárias no st.session_state para esta aba."""
    keys_to_init = [
        f'peticao_gerada{SESSION_STATE_SUFFIX}',
        f'last_user_urls_context{SESSION_STATE_SUFFIX}',
        f'last_prompt{SESSION_STATE_SUFFIX}',
        f'last_response_text{SESSION_STATE_SUFFIX}',
        f'geracao_em_andamento{SESSION_STATE_SUFFIX}'
    ]
    for key in keys_to_init:
        if key not in st.session_state:
            st.session_state[key] = "" if "geracao_em_andamento" not in key else False

def obter_modelos_pecas():
    """
    Carrega os modelos de peças do MongoDB e define fallbacks se nenhum modelo for carregado.
    Esta função utiliza st.cache_data e st.cache_resource (definidos em db_utils.py)
    para cachear os dados e a conexão com o banco.
    """
    modelos_data = carregar_modelos_pecas_from_mongodb()
    
    if not modelos_data:
        st.warning("Modelos de peças não carregados do MongoDB. Algumas opções podem estar limitadas ou ausentes. Verifique a conexão e se o DB está populado.")
        # Fallback para quando não há modelos
        areas_disponiveis = ["Nenhum Modelo Disponível"]
        tipos_peca_disponiveis = {"Nenhum Modelo Disponível": ["Nenhum"]}
        modelos_peca_disponiveis = {"Nenhum": ["Nenhum"]}
    else:
        areas_disponiveis = sorted(list(modelos_data.keys()))
        tipos_peca_disponiveis = {area: sorted(list(tipos.keys())) for area, tipos in modelos_data.items()}
        modelos_peca_disponiveis = {}
        for area_data in modelos_data.values():
            for tipo, modelos in area_data.items():
                modelos_peca_disponiveis[tipo] = sorted(list(modelos.keys()))

    return modelos_data, areas_disponiveis, tipos_peca_disponiveis, modelos_peca_disponiveis

def exibir_campos_entrada(modelos_data, areas_disponiveis, tipos_peca_disponiveis, modelos_peca_disponiveis):
    """
    Exibe os campos de entrada para seleção de modelos e informações básicas,
    incluindo campos parametrizáveis dinâmicos do MongoDB.
    Retorna um dicionário com todos os valores coletados.
    """
    col1, col2, col3 = st.columns(3)
    with col1:
        area_selecionada = st.selectbox("Área do Direito:", areas_disponiveis, key=f"area{SESSION_STATE_SUFFIX}")
    
    tipos_na_area = tipos_peca_disponiveis.get(area_selecionada, ["Outro"])
    with col2:
        tipo_peca_selecionado = st.selectbox("Tipo da Peça:", tipos_na_area, key=f"tipo{SESSION_STATE_SUFFIX}")
    
    modelos_no_tipo = modelos_peca_disponiveis.get(tipo_peca_selecionado, ["Modelo Genérico"])
    with col3:
        modelo_especifico_selecionado = st.selectbox("Modelo Específico:", modelos_no_tipo, key=f"modelo{SESSION_STATE_SUFFIX}")

    # Garante que info_modelo_selecionado seja um dicionário vazio se não houver seleção válida
    info_modelo_selecionado = modelos_data.get(area_selecionada, {}).get(tipo_peca_selecionado, {}).get(modelo_especifico_selecionado, {})

    if not info_modelo_selecionado and area_selecionada != "Nenhum Modelo Disponível":
        st.warning("Detalhes do modelo selecionado não encontrados no banco de dados. Um prompt genérico será usado.")

    st.markdown("### Preenchimento dos Dados da Peça")
    
    valores_parametrizados = {}

    # Adiciona campos dinâmicos do MongoDB
    campos_parametrizaveis = info_modelo_selecionado.get("campos_parametrizaveis", [])
    if campos_parametrizaveis:
        st.markdown("#### Campos Específicos do Modelo:")
        for campo in campos_parametrizaveis:
            nome_campo = campo.get("nome")
            label_campo = campo.get("label", nome_campo.replace('_', ' ').title() if nome_campo else "Campo Desconhecido")
            if nome_campo:
                valores_parametrizados[nome_campo] = st.text_input(label_campo, key=f"param_{nome_campo}{SESSION_STATE_SUFFIX}")
    else:
        st.info("Este modelo não possui campos parametrizáveis definidos no MongoDB. A geração dependerá mais das 'Instruções Adicionais'.")
        # Fallback para campos comuns se não houver campos parametrizáveis definidos
        st.markdown("#### Campos Comuns (Fallback):")
        valores_parametrizados["autor_recorrente"] = st.text_input("Parte Autora/Reclamante/Recorrente:", placeholder="Ex: João da Silva", key=f"autor_fallback{SESSION_STATE_SUFFIX}")
        valores_parametrizados["reu_recorrente"] = st.text_input("Parte Ré/Reclamada/Recorrida:", placeholder="Ex: Empresa XYZ Ltda.", key=f"reu_fallback{SESSION_STATE_SUFFIX}")
        valores_parametrizados["foro_competente"] = st.text_input("Foro Competente:", placeholder="Ex: Comarca de Exemplo / Vara do Trabalho de Exemplo", key=f"foro_fallback{SESSION_STATE_SUFFIX}")
        valores_parametrizados["valor_causa"] = st.text_input("Valor da Causa (R$):", placeholder="Ex: 10.000,00", key=f"valor_fallback{SESSION_STATE_SUFFIX}")


    # Pedidos Principais (do modelo ou adicionados)
    reivindicacoes_comuns_modelo = info_modelo_selecionado.get("reivindicacoes_comuns", [])
    pedidos_selecionados = st.multiselect(
        "Pedidos Principais (selecione do modelo ou adicione abaixo):", 
        reivindicacoes_comuns_modelo, 
        key=f"pedidos_multiselect{SESSION_STATE_SUFFIX}"
    )
    outros_pedidos_texto = st.text_area(
        "Outros Pedidos (um por linha):", 
        placeholder="Ex: Indenização por danos morais\nEx: Reintegração ao emprego", 
        key=f"outros_pedidos{SESSION_STATE_SUFFIX}"
    )
    
    # Instruções Adicionais para a IA
    instrucao_adicional_usuario = st.text_area(
        "Instruções Adicionais para a IA (detalhes específicos, teses, etc.):", 
        key=f"instrucao_adicional{SESSION_STATE_SUFFIX}"
    )

    # Adiciona os campos de "Pedidos" e "Instruções Adicionais" ao dicionário de valores parametrizados
    # para que possam ser usados no prompt_template se o modelo os referenciar.
    valores_parametrizados["pedidos_selecionados"] = pedidos_selecionados
    valores_parametrizados["outros_pedidos_texto"] = outros_pedidos_texto
    valores_parametrizados["instrucao_adicional_usuario"] = instrucao_adicional_usuario

    return (area_selecionada, tipo_peca_selecionado, modelo_especifico_selecionado, info_modelo_selecionado, valores_parametrizados)

def processar_documentos_exemplo():
    """Processa documentos de exemplo anexados pelo usuário."""
    texto_documento_exemplo = ""
    if DOC_INTELLIGENCE_AVAILABLE:
        st.markdown("### Documento(s) de Exemplo (Opcional)")
        docs_exemplo = st.file_uploader("Anexar documento(s) de referência (PDF ou DOCX):", type=["pdf", "docx"], accept_multiple_files=True, key=f"docs_exemplo{SESSION_STATE_SUFFIX}")
        if docs_exemplo:
            textos_docs_exemplo = []
            for doc in docs_exemplo:
                ext = os.path.splitext(doc.name)[1].lower()
                temp_path = f"temp{SESSION_STATE_SUFFIX}_{uuid.uuid4().hex}{ext}"
                try:
                    with open(temp_path, "wb") as f:
                        f.write(doc.getvalue())
                    with st.spinner(f"Extraindo texto de {doc.name}..."):
                        texto_extraido_doc = extrair_texto_documento(temp_path, ext)
                    if texto_extraido_doc:
                        textos_docs_exemplo.append(f"---\n**Documento de Exemplo: {doc.name}**\n\n{texto_extraido_doc}")
                    else:
                        st.warning(f"Não foi possível extrair texto de {doc.name}.")
                except Exception as e:
                    st.error(f"Erro ao processar {doc.name}: {e}")
                    traceback.print_exc()
                finally:
                    if os.path.exists(temp_path):
                        try: os.remove(temp_path)
                        except Exception as e_rm: print(f"Aviso: Falha ao remover arquivo temporário {temp_path}: {e_rm}")
            
            if textos_docs_exemplo:
                texto_documento_exemplo = "\n\n".join(textos_docs_exemplo)
                with st.expander("Ver Texto dos Documentos de Exemplo Anexados", expanded=False):
                    st.text_area("Texto Extraído dos Documentos de Exemplo:", texto_documento_exemplo, height=150, disabled=True, key=f"texto_docs_exemplo_display{SESSION_STATE_SUFFIX}")
    return texto_documento_exemplo

def obter_contexto_urls_sidebar(prompt_base_para_contexto_urls):
    """Lê URLs da sidebar e obtém contexto relevante."""
    url1_sidebar = st.session_state.get('sidebar_url1', "")
    url2_sidebar = st.session_state.get('sidebar_url2', "")
    url3_sidebar = st.session_state.get('sidebar_url3', "")
    user_urls_from_sidebar = [url for url in [url1_sidebar, url2_sidebar, url3_sidebar] if url.strip()]

    contexto_urls_agregado_para_prompt = ""
    contexto_urls_agregado_para_exibir = ""

    if user_urls_from_sidebar:
        st.info(f"Utilizando {len(user_urls_from_sidebar)} URL(s) de contexto da barra lateral para esta peça.")
        num_urls_para_consultar = len(user_urls_from_sidebar)
        spinner_message_urls = f"Consultando {num_urls_para_consultar} URL(s) da barra lateral..."
        with st.spinner(spinner_message_urls):
            for i, url_item in enumerate(user_urls_from_sidebar, 1):
                print(f"INFO APP5 (Parametrizador): Obtendo contexto Chroma da URL {i} (sidebar): {url_item} para a consulta: '{prompt_base_para_contexto_urls}'")
                contexto_url_individual = obter_contexto_relevante_de_url(
                    url_item,
                    prompt_base_para_contexto_urls,
                    top_k_chunks=2 # Limita para evitar sobrecarga e manter relevância
                )
                if contexto_url_individual and "Nenhum conteúdo relevante" not in contexto_url_individual and "Falha ao carregar" not in contexto_url_individual:
                    contexto_urls_agregado_para_prompt += f"\n--- Contexto da URL {i} ({url_item}) ---\n{contexto_url_individual}\n--- Fim do Contexto da URL {i} ---\n\n"
                    contexto_urls_agregado_para_exibir += f"<b>Contexto da URL {i} ({url_item}):</b><br>{contexto_url_individual}<hr>"
                    print(f"INFO APP5 (Parametrizador): Contexto da URL {i} (sidebar) adicionado.")
                else:
                    aviso_url = f"<i>Nenhum contexto útil obtido da URL {i} ({url_item}) da barra lateral.</i><br>"
                    contexto_urls_agregado_para_exibir += aviso_url
                    print(f"AVISO APP5 (Parametrizador): {aviso_url}")
            
    st.session_state[f'last_user_urls_context{SESSION_STATE_SUFFIX}'] = contexto_urls_agregado_para_exibir if contexto_urls_agregado_para_exibir else "Nenhuma URL fornecida na barra lateral ou nenhum contexto relevante extraído."
    return contexto_urls_agregado_para_prompt

def gerar_peticao_parametrizada(
    area_selecionada, tipo_peca_selecionado, modelo_especifico_selecionado, info_modelo_selecionado,
    valores_parametrizados, # Agora recebemos um dicionário com todos os valores
    texto_documento_exemplo, contexto_urls_agregado_para_prompt, enable_google_search_app5
):
    """Função principal para orquestrar a geração da petição."""
    client = get_openai_client()
    search_client = get_azure_search_client()
    if not client or not search_client:
        st.error("Erro ao inicializar clientes de IA. Verifique as configurações e logs.")
        return

    st.session_state[f'geracao_em_andamento{SESSION_STATE_SUFFIX}'] = True
    st.session_state[f'last_user_urls_context{SESSION_STATE_SUFFIX}'] = "" # Reset antes de nova geração

    # Extrai os valores dos pedidos e instruções adicionais do dicionário de valores_parametrizados
    pedidos_selecionados = valores_parametrizados.get("pedidos_selecionados", [])
    outros_pedidos_texto = valores_parametrizados.get("outros_pedidos_texto", "")
    instrucao_adicional_usuario = valores_parametrizados.get("instrucao_adicional_usuario", "")

    todos_pedidos_finais = pedidos_selecionados + [p.strip() for p in outros_pedidos_texto.split("\n") if p.strip()]
    pedidos_formatados_str = ", ".join(todos_pedidos_finais) if todos_pedidos_finais else "(não especificado)"

    # Define um fallback para o prompt_template se o modelo não for encontrado/válido
    prompt_template_modelo_fallback = (
        "Gere uma peça jurídica padrão com as informações fornecidas, pois o modelo selecionado não está disponível ou está incompleto. "
        "Use as seguintes informações: Área: {area_selecionada}, Tipo: {tipo_peca_selecionado}, Autor: {autor_recorrente}, Réu: {reu_recorrente}, Foro: {foro_competente}, Valor da causa: {valor_causa}, Pedidos: {pedidos_formatados_str}, "
        "Instruções: {instrucao_adicional_usuario}. Se houver, utilize o documento de exemplo: {texto_documento_exemplo}"
    )
    prompt_template_utilizado = info_modelo_selecionado.get("prompt_template", prompt_template_modelo_fallback)
    
    # Prepara os argumentos para formatar o prompt, combinando valores dinâmicos e estáticos
    format_args_peca = {
        "area_selecionada": area_selecionada,
        "tipo_peca_selecionado": tipo_peca_selecionado,
        "modelo_especifico_selecionado": modelo_especifico_selecionado,
        "pedidos_formatados_str": pedidos_formatados_str,
        "instrucao_adicional_usuario": instrucao_adicional_usuario,
        "texto_documento_exemplo": texto_documento_exemplo,
        **valores_parametrizados # Adiciona todos os campos dinâmicos coletados
    }

    # Garante que todas as variáveis usadas no template estejam no dicionário,
    # preenchendo com um valor padrão se ausente.
    campos_template = [f for _, f, _, _ in Formatter().parse(prompt_template_utilizado) if f]
    for campo in campos_template:
        if campo not in format_args_peca:
            format_args_peca[campo] = f"[{campo.upper()}]" # Adiciona um placeholder se o campo não estiver no dicionário

    # Usa defaultdict para evitar KeyError na formatação, preenchendo com um valor padrão
    format_args_peca_safe = defaultdict(lambda: "[DADO NAO INFORMADO]", format_args_peca)
    prompt_final_para_llm = prompt_template_utilizado.format_map(format_args_peca_safe)

    # Adiciona contexto das URLs ao prompt final, se houver
    if contexto_urls_agregado_para_prompt:
        prompt_final_para_llm = (
            f"{contexto_urls_agregado_para_prompt}"
            f"Considerando os contextos acima extraídos das URLs fornecidas pelo usuário na barra lateral, "
            f"e o(s) documento(s) de exemplo também fornecido(s) (se houver), gere a peça conforme as seguintes especificações:\n\n"
            f"Especificações da Peça: \"{prompt_final_para_llm}\""
        )

    with st.spinner("Gerando petição parametrizada com todas as fontes..."):
        try:
            system_prompt_base_app5 = carregar_prompt_parametrizador()
            resposta = generate_response_with_conditional_google_search(
                system_message_base=system_prompt_base_app5,
                user_instruction=prompt_final_para_llm,
                context_document_text=texto_documento_exemplo,
                search_client=search_client,
                client_openai=client,
                azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,
                azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM, # Pode ser o mesmo deployment
                top_k_initial_search_azure=5,
                top_k_rerank_azure=2,
                use_semantic_search_azure=True,
                enable_google_search_trigger=enable_google_search_app5,
                temperature=0.3, # Um pouco mais conservador para peças jurídicas
                max_tokens=4000 # Limite de tokens para a resposta
            )
            st.session_state[f'peticao_gerada{SESSION_STATE_SUFFIX}'] = str(resposta).strip()
            
            st.session_state[f'last_prompt{SESSION_STATE_SUFFIX}'] = prompt_final_para_llm
            st.session_state[f'last_response_text{SESSION_STATE_SUFFIX}'] = st.session_state[f'peticao_gerada{SESSION_STATE_SUFFIX}']

        except Exception as e:
            st.error(f"Erro ao gerar petição parametrizada: {e}")
            st.session_state[f'peticao_gerada{SESSION_STATE_SUFFIX}'] = ""
            traceback.print_exc()
        finally:
            st.session_state[f'geracao_em_andamento{SESSION_STATE_SUFFIX}'] = False
            st.rerun() # Força uma nova renderização para exibir o resultado

def exibir_peticao_e_feedback(tipo_peca_selecionado):
    """Exibe a petição gerada, opções de download e formulário de feedback."""
    if st.session_state.get(f'peticao_gerada{SESSION_STATE_SUFFIX}', ""):
        st.markdown("---")
        st.markdown("## 📝 Petição Gerada")

        if st.session_state.get(f'last_user_urls_context{SESSION_STATE_SUFFIX}') and ("Contexto da URL" in st.session_state.get(f'last_user_urls_context{SESSION_STATE_SUFFIX}')):
            with st.expander("Contexto das URLs da Barra Lateral Utilizado", expanded=False):
                st.markdown(st.session_state[f'last_user_urls_context{SESSION_STATE_SUFFIX}'], unsafe_allow_html=True)

        with st.expander("📄 Pré-visualização da Petição (Somente Leitura)", expanded=True):
            st.markdown(st.session_state[f'peticao_gerada{SESSION_STATE_SUFFIX}'], unsafe_allow_html=True)

        # Campo de edição opcional
        texto_editado_app5 = st.text_area("Edição opcional:", value=st.session_state[f'peticao_gerada{SESSION_STATE_SUFFIX}'], height=400, key=f"editor_peticao{SESSION_STATE_SUFFIX}")
        
        # Atualiza a session_state se o texto foi editado
        if texto_editado_app5 != st.session_state[f'peticao_gerada{SESSION_STATE_SUFFIX}']:
            st.session_state[f'peticao_gerada{SESSION_STATE_SUFFIX}'] = texto_editado_app5

        try:
            docx_file = gerar_docx(st.session_state[f'peticao_gerada{SESSION_STATE_SUFFIX}'])
            st.download_button(
                label="📅 Baixar Petição em DOCX",
                data=docx_file,
                file_name=f"LexAutomate_Peticao_{tipo_peca_selecionado.replace(' ', '_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"download_docx{SESSION_STATE_SUFFIX}_button"
            )
        except Exception as e:
            st.error(f"Erro ao gerar o DOCX para a petição: {e}")
            traceback.print_exc()

    # Se houver uma resposta gerada, exibe o formulário de feedback
    if f'last_response_text{SESSION_STATE_SUFFIX}' in st.session_state and st.session_state[f'last_response_text{SESSION_STATE_SUFFIX}']:
        with st.expander("💬 Sua opinião nos ajuda a melhorar esta funcionalidade"):
            # Usa um UUID no key para garantir que o feedback seja para a última geração
            feedback_key_suffix = uuid.uuid4().hex
            feedback_opcao_app5 = st.radio(
                "Esta petição gerada foi útil?",
                ["👍 Sim", "👎 Não"],
                key=f"feedback_radio_param{SESSION_STATE_SUFFIX}_{feedback_key_suffix}"
            )
            comentario_app5 = st.text_area(
                "Comentário sobre a petição (opcional):",
                placeholder="Diga o que achou da petição ou o que faltou.",
                key=f"feedback_comment_param{SESSION_STATE_SUFFIX}_{feedback_key_suffix}"
            )
            if st.button("Enviar Feedback da Petição Parametrizada", key=f"feedback_submit_param{SESSION_STATE_SUFFIX}_{feedback_key_suffix}"):
                salvar_feedback_rag(
                    pergunta=st.session_state.get(f'last_prompt{SESSION_STATE_SUFFIX}', "Instrução não registrada"),
                    resposta=st.session_state.get(f'last_response_text{SESSION_STATE_SUFFIX}', ""),
                    feedback=feedback_opcao_app5,
                    comentario=comentario_app5,
                )
                st.success("Feedback sobre a petição enviado com sucesso. Obrigado!")
                # Limpa as chaves de feedback para evitar reenvio acidental
                if f'last_response_text{SESSION_STATE_SUFFIX}' in st.session_state: del st.session_state[f'last_response_text{SESSION_STATE_SUFFIX}']
                if f'last_prompt{SESSION_STATE_SUFFIX}' in st.session_state: del st.session_state[f'last_prompt{SESSION_STATE_SUFFIX}']
                st.rerun() # Força uma nova renderização após o feedback

def parametrizador_interface():
    """Função principal que orquestra a interface do Streamlit para o parametrizador."""
    st.markdown("Preencha os campos, anexe documentos de exemplo e, opcionalmente, utilize as URLs da barra lateral para enriquecer a geração da peça.")
    st.markdown("---")

    inicializar_session_state()

    # Carrega modelos e define opções de seleção
    modelos_data, areas_disponiveis, tipos_peca_disponiveis, modelos_peca_disponiveis = obter_modelos_pecas()

    # Exibe campos de entrada e coleta os dados
    (area_selecionada, tipo_peca_selecionado, modelo_especifico_selecionado, info_modelo_selecionado,
     valores_parametrizados) = \
        exibir_campos_entrada(modelos_data, areas_disponiveis, tipos_peca_disponiveis, modelos_peca_disponiveis)

    # Processa documentos de exemplo
    texto_documento_exemplo = processar_documentos_exemplo()
    
    enable_google_search_app5 = st.checkbox("Habilitar busca complementar na Web (Google) para esta peça?", value=True, key=f"param_enable_google_search{SESSION_STATE_SUFFIX}_checkbox")

    # Botão de geração da petição
    if st.button("Gerar Petição Parametrizada", key=f"gerar_peticao_param{SESSION_STATE_SUFFIX}_button"):
        # Validações antes de gerar
        if area_selecionada == "Nenhum Modelo Disponível" or not info_modelo_selecionado:
            st.warning("Selecione um modelo de peça válido para gerar. Não há modelos disponíveis ou o selecionado está incompleto.")
            return
        
        # Exemplo de validação para campos essenciais se não houver campos_parametrizaveis definidos
        # Adapte esta validação conforme a necessidade do seu modelo ou remova se a IA for robusta o suficiente
        if not info_modelo_selecionado.get("campos_parametrizaveis"):
            if not valores_parametrizados.get("autor_recorrente") or not valores_parametrizados.get("reu_recorrente"):
                st.warning("Por favor, preencha os campos 'Parte Autora/Reclamante/Recorrente' e 'Parte Ré/Reclamada/Recorrida' para modelos sem campos parametrizáveis específicos.")
                return

        # Prepara o prompt base para busca de contexto em URLs
        # Usa os valores_parametrizados para construir a query de contexto
        todos_pedidos_finais_para_contexto = valores_parametrizados.get("pedidos_selecionados", []) + \
                                             [p.strip() for p in valores_parametrizados.get("outros_pedidos_texto", "").split("\n") if p.strip()]
        pedidos_formatados_str_para_contexto = ", ".join(todos_pedidos_finais_para_contexto) if todos_pedidos_finais_para_contexto else "(não especificado)"
        
        autor_para_contexto = valores_parametrizados.get("autor_recorrente", valores_parametrizados.get(info_modelo_selecionado.get("campos_parametrizaveis", [{}])[0].get("nome", "autor_recorrente"), "[AUTOR]"))
        reu_para_contexto = valores_parametrizados.get("reu_recorrente", valores_parametrizados.get(info_modelo_selecionado.get("campos_parametrizaveis", [{}])[1].get("nome", "reu_recorrente"), "[RÉU]"))

        prompt_base_para_contexto_urls = (
            f"Pesquisar jurisprudência e informações relevantes para uma peça do tipo '{tipo_peca_selecionado}' na área '{area_selecionada}', "
            f"envolvendo as partes '{autor_para_contexto}' e '{reu_para_contexto}', com os pedidos: '{pedidos_formatados_str_para_contexto}'. "
            f"Considerar também as seguintes instruções adicionais: '{valores_parametrizados.get('instrucao_adicional_usuario', '')}'."
        )

        # Obtém contexto das URLs da sidebar
        contexto_urls_agregado_para_prompt = obter_contexto_urls_sidebar(prompt_base_para_contexto_urls)

        # Chama a função de geração principal
        gerar_peticao_parametrizada(
            area_selecionada, tipo_peca_selecionado, modelo_especifico_selecionado, info_modelo_selecionado,
            valores_parametrizados, # Passa o dicionário completo
            texto_documento_exemplo, contexto_urls_agregado_para_prompt, enable_google_search_app5
        )
    
    # Exibe a petição gerada e o formulário de feedback
    exibir_peticao_e_feedback(tipo_peca_selecionado)

# Se este script for executado diretamente, chama a interface
if __name__ == "__main__":
    parametrizador_interface()

