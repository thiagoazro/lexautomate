# rag_utils.py
import streamlit as st
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery, QueryType
from azure.core.credentials import AzureKeyCredential
import sys
import os
import traceback
import re
import json
import requests
import joblib
import uuid # Adicionado para IDs únicos na visualização do grafo

from io import BytesIO
from docx import Document as DocxDocument
from docx.shared import Pt
# from docx.enum.text import WD_LINE_SPACING # WD_LINE_SPACING não é usado diretamente no código fornecido

from sentence_transformers import CrossEncoder

# --- INÍCIO: INTEGRAÇÃO GRAPH_RAG ---
try:
    from graph_rag import GraphRAG # Importa a classe do novo módulo
    GRAPH_RAG_AVAILABLE = True
    print("INFO RAG_UTILS: Módulo graph_rag.py carregado com sucesso.")
except ImportError:
    GRAPH_RAG_AVAILABLE = False
    print("AVISO RAG_UTILS: Módulo graph_rag.py não encontrado. Funcionalidade de grafo desabilitada.")
except Exception as e_graph_import:
    GRAPH_RAG_AVAILABLE = False
    print(f"ERRO RAG_UTILS: Falha ao importar graph_rag.py: {e_graph_import}. Funcionalidade de grafo desabilitada.")
# --- FIM: INTEGRAÇÃO GRAPH_RAG ---


# --- CREDENCIAIS HARDCODED DIRETAMENTE NO CÓDIGO ---
# (Mantido conforme o original)
AZURE_OPENAI_ENDPOINT = 'https://lexautomate.openai.azure.com/'
AZURE_OPENAI_API_KEY = '6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA'
AZURE_OPENAI_DEPLOYMENT_LLM = 'lexautomate_agent'
AZURE_OPENAI_DEPLOYMENT_EMBEDDING = 'text-embedding-3-large'
AZURE_API_VERSION = '2024-02-15-preview'

AZURE_SEARCH_ENDPOINT = "https://lexautomate-rag.search.windows.net"
AZURE_SEARCH_KEY = "cjnnxusQPkdT02Lu75uIeD7XEKrAzxgjalqWpS58SgAzSeCpCL38"
DEFAULT_AZURE_SEARCH_INDEX_NAME = "docs-index"
AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT = "default"

GOOGLE_API_KEY = "AIzaSyCUT6HKCaOe51hTM7PY3sexnSJm1mlO5k0"
GOOGLE_CX_ID = "e3c7fef3c7d1c4a10"
# -----------------------------------------------------------------------

# --- CAMINHOS PARA OS MODELOS DE CLASSIFICAÇÃO ---
try:
    PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(st.session_state.get('main_script_path', __file__)))
except Exception:
    PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(PROJECT_ROOT_DIR) == "utils":
        PROJECT_ROOT_DIR = os.path.dirname(PROJECT_ROOT_DIR)

CLASSIFIER_AREA_DIREITO_PATH = os.path.join(PROJECT_ROOT_DIR, "models", "classificador_area_direito.joblib")
CLASSIFIER_TIPO_TAREFA_PATH = os.path.join(PROJECT_ROOT_DIR, "models", "classificador_tipo_tarefa.joblib")
RERANKER_MODEL_NAME = 'cross-encoder/ms-marco-MiniLM-L-6-v2'

print(f"INFO RAG_UTILS: PROJECT_ROOT_DIR definido como: {PROJECT_ROOT_DIR}")
print(f"INFO RAG_UTILS: Caminho esperado para classificador de área: {CLASSIFIER_AREA_DIREITO_PATH}")
print(f"INFO RAG_UTILS: Caminho esperado para classificador de tarefa: {CLASSIFIER_TIPO_TAREFA_PATH}")


# --- Inicialização de Clientes ---
@st.cache_resource
def get_openai_client():
    print("INFO RAG_UTILS: Tentando inicializar cliente Azure OpenAI...")
    if not AZURE_OPENAI_API_KEY or not AZURE_OPENAI_API_KEY.strip():
         print("ERRO RAG_UTILS: AZURE_OPENAI_API_KEY está vazia. Verifique o valor em rag_utils.py.")
         st.error("ERRO: Chave da API OpenAI não configurada.")
         return None
    if not all([AZURE_OPENAI_ENDPOINT, AZURE_API_VERSION, AZURE_OPENAI_DEPLOYMENT_LLM, AZURE_OPENAI_DEPLOYMENT_EMBEDDING]):
         print("ERRO RAG_UTILS: Configurações Azure OpenAI (endpoint, versão, deployments) incompletas.")
         st.error("ERRO: Configurações da API OpenAI incompletas.")
         return None
    try:
        client = AzureOpenAI(api_version=AZURE_API_VERSION, azure_endpoint=AZURE_OPENAI_ENDPOINT, api_key=AZURE_OPENAI_API_KEY)
        print("INFO RAG_UTILS: Cliente Azure OpenAI inicializado com sucesso.")
        return client
    except Exception as e:
        print(f"ERRO CRÍTICO RAG_UTILS: Falha ao inicializar cliente Azure OpenAI: {traceback.format_exc()}");
        st.error(f"Falha OpenAI: {e}");
        return None

@st.cache_resource
def get_azure_search_client(index_name: str = DEFAULT_AZURE_SEARCH_INDEX_NAME):
    print(f"INFO RAG_UTILS: Tentando inicializar cliente Azure AI Search para o índice '{index_name}'...")
    if not AZURE_SEARCH_KEY or not AZURE_SEARCH_KEY.strip():
        print("ERRO RAG_UTILS: AZURE_SEARCH_KEY está vazia. Verifique o valor em rag_utils.py.")
        st.error("ERRO: Chave do Azure AI Search não configurada.")
        return None
    if not all([AZURE_SEARCH_ENDPOINT, index_name]):
        print("ERRO RAG_UTILS: Configurações do Azure AI Search (endpoint, nome do índice) incompletas.")
        st.error("ERRO: Configurações do Azure AI Search incompletas.")
        return None
    try:
        search_credential = AzureKeyCredential(AZURE_SEARCH_KEY)
        search_client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=index_name, credential=search_credential)
        print(f"INFO RAG_UTILS: Cliente Azure AI Search para '{index_name}' inicializado com sucesso.")
        return search_client
    except Exception as e:
        print(f"ERRO CRÍTICO RAG_UTILS: Falha ao inicializar Azure AI Search Client: {traceback.format_exc()}");
        st.error(f"Falha Azure AI Search: {e}");
        return None

# --- Funções de Reranking ---
@st.cache_resource
def get_reranker_model(model_name: str = RERANKER_MODEL_NAME):
    print(f"INFO RAG_UTILS: Carregando modelo reranker: {model_name}")
    try:
        model = CrossEncoder(model_name)
        print(f"INFO RAG_UTILS: Modelo reranker {model_name} carregado com sucesso.")
        return model
    except Exception as e:
        print(f"ERRO RAG_UTILS: Falha ao carregar modelo reranker {model_name}: {e}")
        st.error(f"Falha ao carregar modelo de reranking: {e}")
        return None

def rerank_chunks(query: str, chunks_details: list, model: CrossEncoder, top_n_rerank: int = 5) -> list:
    if not query or not chunks_details or model is None: return chunks_details
    candidate_contents = [chunk.get('content', '') for chunk in chunks_details]
    if not any(candidate_contents): return chunks_details
    sentence_pairs = [(query, content) for content in candidate_contents]
    try:
        scores = model.predict(sentence_pairs, show_progress_bar=False)
    except Exception as e:
        print(f"ERRO RAG_UTILS (Rerank): Falha ao calcular scores de reranking: {e}")
        return chunks_details
    for chunk, score in zip(chunks_details, scores):
        chunk['rerank_score_cross_encoder'] = float(score) # Assegura que é float
    reranked_chunks_details = sorted(chunks_details, key=lambda x: x.get('rerank_score_cross_encoder', -float('inf')), reverse=True)
    return reranked_chunks_details[:top_n_rerank]


# --- Funções de Classificação ---
@st.cache_resource
def carregar_classificador(model_path: str):
    if not model_path:
        print(f"AVISO RAG_UTILS: Caminho do modelo classificador não fornecido.")
        return None
    if not os.path.exists(model_path):
        print(f"AVISO RAG_UTILS: Modelo classificador não encontrado em {model_path} (caminho construído).")
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        path_option_1 = os.path.join(current_script_dir, "models", os.path.basename(model_path))
        path_option_2 = os.path.join(os.path.dirname(current_script_dir), "models", os.path.basename(model_path))
        path_option_3 = os.path.join(current_script_dir, os.path.basename(model_path))
        if os.path.exists(path_option_1): model_path = path_option_1
        elif os.path.exists(path_option_2): model_path = path_option_2
        elif os.path.exists(path_option_3): model_path = path_option_3
        else:
            print(f"AVISO RAG_UTILS: Modelo classificador também não encontrado nas tentativas: {path_option_1}, {path_option_2}, {path_option_3}.")
            return None
    try:
        modelo = joblib.load(model_path)
        print(f"INFO RAG_UTILS: Modelo classificador {model_path} carregado com sucesso.")
        return modelo
    except Exception as e:
        print(f"ERRO RAG_UTILS: Falha ao carregar modelo classificador {model_path}: {e}")
        return None

modelo_area_direito = carregar_classificador(CLASSIFIER_AREA_DIREITO_PATH)
modelo_tipo_tarefa = carregar_classificador(CLASSIFIER_TIPO_TAREFA_PATH)

def classificar_texto(texto: str, modelo_area, modelo_tarefa) -> tuple[str, str, dict, dict]:
    area_predita, tarefa_predita, prob_area, prob_tarefa = "desconhecida", "desconhecida", {}, {}
    if not texto.strip(): return area_predita, tarefa_predita, prob_area, prob_tarefa
    try:
        if modelo_area:
            area_predita = modelo_area.predict([texto])[0]
            probs = modelo_area.predict_proba([texto])[0]
            prob_area = {cls: prob for cls, prob in zip(modelo_area.classes_, probs)}
        if modelo_tipo_tarefa:
            tarefa_predita = modelo_tipo_tarefa.predict([texto])[0]
            probs = modelo_tipo_tarefa.predict_proba([texto])[0]
            prob_tarefa = {cls: prob for cls, prob in zip(modelo_tipo_tarefa.classes_, probs)}
    except Exception as e: print(f"AVISO RAG_UTILS (Classify): {e}")
    return area_predita, tarefa_predita, prob_area, prob_tarefa

def selecionar_prompt_dinamico(area: str, tarefa: str, base_system_prompt: str) -> str:
    prompt_modificado = base_system_prompt
    info_classificacao = []
    if area != "desconhecida": info_classificacao.append(f"Área do Direito identificada: {area}.")
    if tarefa != "desconhecida": info_classificacao.append(f"Tipo de tarefa identificado: {tarefa}.")
    if info_classificacao:
        prompt_modificado += "\n\n--- CLASSIFICAÇÃO AUTOMÁTICA DA CONSULTA ---\n" + \
                             "\n".join(info_classificacao) + \
                             "\nUse estas informações para refinar seu foco."
    return prompt_modificado

def get_embedding(text_chunk: str, client_openai: AzureOpenAI, deployment_name: str = AZURE_OPENAI_DEPLOYMENT_EMBEDDING):
    if not text_chunk or client_openai is None: return None
    try:
        processed_chunk = ' '.join(text_chunk.replace('\n', ' ').split())
        if not processed_chunk: return None
        response = client_openai.embeddings.create(input=[processed_chunk], model=deployment_name)
        return response.data[0].embedding
    except Exception as e:
        print(f"  ERRO RAG_UTILS (get_embedding): {e}")
        return None

def expand_query_with_llm(original_query: str, client_openai: AzureOpenAI, azure_openai_deployment: str = AZURE_OPENAI_DEPLOYMENT_LLM) -> str:
    if not original_query.strip() or client_openai is None: return original_query
    prompt_de_expansao = f"""Analise a seguinte pergunta de um usuário e gere uma consulta otimizada para uma base de dados jurídica.
Siga estas regras para gerar a "Consulta Otimizada":
1.  Se a pergunta do usuário for PRIMARIAMENTE sobre um precedente ou número de processo específico (ex: "do que trata o precedente X?", "qual a decisão no caso Y?", "detalhes sobre TST-Ag-E-ED-RR-1002446-80.2016.5.02.0433"), a "Consulta Otimizada" DEVE ser APENAS o número exato do precedente/processo entre aspas duplas.
2.  Se a pergunta for mais geral, mas mencionar um precedente como parte de um contexto maior, extraia o precedente EXATAMENTE e identifique até 3 tópicos/palavras-chave principais da pergunta que descrevam o assunto jurídico. Nesse caso, a "Consulta Otimizada" deve ser: "[Número do Precedente Exato]" E ([Tópico 1] OU [Tópico 2])
3.  Se a pergunta NÃO mencionar um precedente específico, identifique 3-4 tópicos/palavras-chave principais e forme a "Consulta Otimizada" como: [Tópico 1] OU [Tópico 2] OU [Tópico 3]
Retorne APENAS a "Consulta Otimizada:", sem nenhuma outra explicação ou texto.
Pergunta do Usuário: "{original_query}"
Consulta Otimizada:"""
    try:
        response = client_openai.chat.completions.create(
            model=azure_openai_deployment,
            messages=[
                {"role": "system", "content": "Você é um assistente especialista em otimizar consultas de busca para sistemas jurídicos."},
                {"role": "user", "content": prompt_de_expansao}
            ],
            temperature=0.0, max_tokens=250 )
        expanded_query_text = response.choices[0].message.content.strip()
        if not expanded_query_text or expanded_query_text.lower() == "n/a" or len(expanded_query_text) < 3:
            return original_query
        return expanded_query_text
    except Exception as e:
        print(f"ERRO RAG_UTILS (QueryExpansion): {e}")
        return original_query

def formatar_chunks_para_llm_azure(chunks_info_list: list, fonte_descricao: str = "Base de Conhecimento Interna (Azure AI Search)") -> str:
    context = f"\n\n--- INÍCIO DO CONTEXTO DE {fonte_descricao} ---\n"
    if not chunks_info_list:
        context += "Nenhum documento ou trecho relevante foi encontrado nesta fonte para a consulta atual.\n"
    else:
        for i, chunk_info in enumerate(chunks_info_list, 1):
            content = chunk_info.get('content', 'Conteúdo não disponível')
            source = chunk_info.get('arquivo_origem', 'Fonte desconhecida')
            tipo_doc = chunk_info.get('tipo_documento', 'N/A') # Adicionado
            score_azure = chunk_info.get('score')
            reranker_score_azure_semantic = chunk_info.get('reranker_score') # Score semântico do Azure
            reranker_score_ce = chunk_info.get('rerank_score_cross_encoder') # Score do CrossEncoder

            score_info = []
            if score_azure is not None: score_info.append(f"Score Busca: {score_azure:.3f}")
            if reranker_score_azure_semantic is not None: score_info.append(f"Score Semântico Azure: {reranker_score_azure_semantic:.3f}")
            if reranker_score_ce is not None: score_info.append(f"Score CrossEncoder: {reranker_score_ce:.3f}")
            score_str = f" ({', '.join(score_info)})" if score_info else ""

            context += f"\n[FONTE INTERNA {i}: {source} (Tipo: {tipo_doc}){score_str}]\n"
            semantic_caption_text = chunk_info.get("semantic_caption") # Captions semânticas do Azure Search
            if semantic_caption_text: # Adiciona se existir
                context += f"Destaque Semântico (Azure): {semantic_caption_text}\n"
            context += f"Conteúdo do Trecho: {content}\n"
    context += f"--- FIM DO CONTEXTO DE {fonte_descricao} ---\n"
    return context

def find_relevant_chunks_azure_search(
    original_user_query: str, search_client: SearchClient, client_openai: AzureOpenAI,
    azure_openai_deployment_for_expansion: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    top_k_initial_search: int = 20, use_semantic_search: bool = True,
    semantic_config_name: str = AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT,
    search_filter: str | None = None ):

    if not original_user_query or search_client is None or client_openai is None: return []
    query_for_search = expand_query_with_llm(original_user_query, client_openai, azure_openai_deployment_for_expansion)
    query_embedding_vector = get_embedding(query_for_search, client_openai)
    vector_query = None
    if query_embedding_vector:
        vector_query = VectorizedQuery(vector=query_embedding_vector, k_nearest_neighbors=top_k_initial_search, fields="content_vector", exhaustive=True)

    search_args: dict[str, any] = {
        "vector_queries": [vector_query] if vector_query else None,
        "select": ["chunk_id", "document_id", "arquivo_origem", "content", "tipo_documento", "language_code"], # Adicionado tipo_documento
        "top": top_k_initial_search,
        "include_total_count": True
    }
    if search_filter: search_args["filter"] = search_filter

    search_text_for_azure = query_for_search # Usar a query expandida para busca textual também

    if use_semantic_search:
        current_search_args = {
            "search_text": search_text_for_azure,
            "query_type": QueryType.SEMANTIC,
            "semantic_configuration_name": semantic_config_name,
            # "captions": "extractive", # Habilita captions (trechos destacados)
            # "answers": "extractive|count-3", # Habilita respostas diretas (se configurado no índice)
            # "query_language": "pt-BR", # Adicionado para busca semântica
            # "query_speller": "lexicon" # Habilita correção ortográfica, se desejado
        }
        search_args.update(current_search_args)
    elif vector_query and not search_text_for_azure.strip(): # Busca puramente vetorial se não houver texto
         search_args["search_text"] = None # Ou "*" se a API exigir algo
         search_args.pop("query_type", None) # Remove query_type se for SEMANTIC
         # Remove outros parâmetros semânticos
         for key_to_remove in ["semantic_configuration_name", "captions", "answers", "query_language", "query_speller"]:
            search_args.pop(key_to_remove, None)
    else: # Busca híbrida (vetorial + texto simples) ou só texto simples
        search_args["search_text"] = search_text_for_azure
        # Se query_type era SEMANTIC, mas não estamos usando, muda para SIMPLE
        if "query_type" in search_args and search_args["query_type"] == QueryType.SEMANTIC:
             search_args["query_type"] = QueryType.SIMPLE # Ou FULL para sintaxe Lucene completa
        # Remove parâmetros semânticos se não estiver usando busca semântica
        for key_to_remove in ["semantic_configuration_name", "captions", "answers", "query_language", "query_speller"]:
            search_args.pop(key_to_remove, None)

    try:
        # Para o log JSON, converte enums para seus valores de string, se existirem
        loggable_search_args = {}
        for k, v in search_args.items():
            if hasattr(v, 'value'): # Para enums como QueryType
                loggable_search_args[k] = v.value
            elif isinstance(v, list) and v and hasattr(v[0], 'vector'): # Para VectorizedQuery
                 loggable_search_args[k] = "[VectorizedQuery Object]" # Simplificado para log
            else:
                loggable_search_args[k] = v
        print(f"DEBUG RAG_UTILS: Executando busca com args: {json.dumps(loggable_search_args, indent=2, default=str)}")

        search_results_iterable = search_client.search(**search_args) # type: ignore
        retrieved_chunks_details = []
        for i, doc_result in enumerate(search_results_iterable):
            chunk_detail = {
                "rank_azure": i + 1, "chunk_id": doc_result.get("chunk_id", "N/A"),
                "document_id": doc_result.get("document_id", "N/A"), "arquivo_origem": doc_result.get("arquivo_origem", "N/A"),
                "tipo_documento": doc_result.get("tipo_documento", "N/A"), # Adicionado
                "score": doc_result.get("@search.score"), "reranker_score": doc_result.get("@search.reranker_score"), # Score semântico
                "content": doc_result.get("content", ""), "content_preview": doc_result.get("content", "")[:200] + "...",
                "semantic_caption": None, # Inicializa
            }
            # Extrai captions se existirem (Azure Search pode retornar isso)
            if "@search.captions" in doc_result and doc_result["@search.captions"]:
                chunk_detail["semantic_caption"] = " ".join([cap.text for cap in doc_result["@search.captions"] if cap.text]) # Pega o texto da caption
            retrieved_chunks_details.append(chunk_detail)
        if 'streamlit' in __import__('sys').modules: # Salva os chunks brutos da busca
            st.session_state.last_retrieved_chunks_details_azure_raw = retrieved_chunks_details
        return retrieved_chunks_details
    except Exception as e:
        print(f"ERRO RAG_UTILS (find_relevant_chunks_azure_search): {e}")
        traceback.print_exc()
        if 'streamlit' in __import__('sys').modules: st.session_state.last_retrieved_chunks_details_azure_raw = []
        return []


# --- GOOGLE CUSTOM SEARCH FUNCTIONS ---
def call_google_custom_search(query: str, num_results: int = 3) -> list:
    if not GOOGLE_API_KEY or not GOOGLE_API_KEY.strip() or \
       not GOOGLE_CX_ID or not GOOGLE_CX_ID.strip():
        print("ALERTA RAG_UTILS: Chaves Google Custom Search não configuradas ou vazias. Busca na web desabilitada.")
        return []
    try:
        url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_CX_ID}&q={query}&num={num_results}&hl=pt-BR"
        response = requests.get(url, timeout=15) # Adicionado timeout
        response.raise_for_status() # Levanta erro para status HTTP ruins
        search_results_json = response.json()
        formatted_results = []
        if "items" in search_results_json: # Verifica se 'items' existe
            for item in search_results_json.get("items", []): # Usa .get com fallback
                title = item.get("title")
                link = item.get("link")
                snippet = item.get("snippet", item.get("htmlSnippet")) # Usa snippet ou htmlSnippet
                if snippet: # Limpa HTML do snippet
                    snippet = re.sub('<[^<]+?>', '', snippet).strip() # Remove tags HTML
                    snippet = re.sub(r'\s+', ' ', snippet) # Normaliza espaços
                formatted_results.append({"title": title, "link": link, "snippet": snippet})
        return formatted_results
    except requests.exceptions.RequestException as e: # Captura erros de request
        print(f"ERRO RAG_UTILS (call_google_custom_search - HTTP): {e}")
        return []
    except Exception as e: # Captura outros erros
        print(f"ERRO RAG_UTILS (call_google_custom_search - Geral): {e}")
        return []


def should_trigger_google_search(
    user_instruction: str, azure_search_results: list, min_azure_results_threshold: int = 1,
    area_predita: str | None = None, tarefa_predita: str | None = None ) -> bool:
    palavras_chave_busca_web = [
        "pesquise na web", "busque na internet", "notícias recentes sobre",
        "informações atuais sobre", "google por", "qual a cotação atual",
        "dados atualizados de", "legislação mais recente sobre", "jurisprudência recente sobre",
        "eventos atuais", "últimas notícias"
    ]
    if any(keyword.lower() in user_instruction.lower() for keyword in palavras_chave_busca_web): return True
    if tarefa_predita and tarefa_predita.lower() in ["noticias", "atualidades_juridicas", "pesquisa_web"]: return True # Se a tarefa for de pesquisa web
    if not azure_search_results or len(azure_search_results) < min_azure_results_threshold: return True # Se poucos resultados internos
    return False

def formatar_google_results_para_llm(raw_google_data_list: list) -> str:
    if not raw_google_data_list:
        return "\n\n--- CONTEXTO DA BUSCA NA WEB (Google) ---\nNenhuma informação adicional encontrada.\n--- FIM DO CONTEXTO DA BUSCA NA WEB ---\n"
    context = "\n\n--- INÍCIO DO CONTEXTO DA BUSCA NA WEB (Google) ---\n"
    context += "Informações recuperadas da internet:\n"
    for i, res in enumerate(raw_google_data_list):
        context += f"\n[WEB {i+1}: {res.get('title', 'N/A')}] (Link: {res.get('link', 'N/A')})\nSnippet: {res.get('snippet', 'N/A')}\n"
    context += "--- FIM DO CONTEXTO DA BUSCA NA WEB ---\n"
    return context

# --- GERAÇÃO DE RESPOSTA PRINCIPAL ---
def generate_response_with_conditional_google_search(
    system_message_base: str, user_instruction: str, context_document_text: str | None,
    search_client: SearchClient, client_openai: AzureOpenAI,
    azure_openai_deployment_llm: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    azure_openai_deployment_expansion: str = AZURE_OPENAI_DEPLOYMENT_LLM, # Usado na expansão da query
    top_k_initial_search_azure: int = 20, top_k_rerank_azure: int = 5,
    use_semantic_search_azure: bool = True, semantic_config_name_azure: str = AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT,
    enable_google_search_trigger: bool = True,
    min_azure_results_for_google_trigger: int = 2, # Gatilho para Google se menos de X resultados do Azure
    num_google_results: int = 3, temperature: float = 0.1, max_tokens: int = 4000,
    use_reranker: bool = True # Habilita/desabilita o reranker CrossEncoder
    ):

    area_predita, tarefa_predita, _, _ = classificar_texto(user_instruction, modelo_area_direito, modelo_tipo_tarefa)
    system_message_final = selecionar_prompt_dinamico(area_predita, tarefa_predita, system_message_base)
    search_filter_for_azure = None # Pode ser usado para filtrar por tipo de documento, data, etc.

    retrieved_azure_chunks_initial = find_relevant_chunks_azure_search(
        original_user_query=user_instruction, search_client=search_client, client_openai=client_openai,
        azure_openai_deployment_for_expansion=azure_openai_deployment_expansion,
        top_k_initial_search=top_k_initial_search_azure, use_semantic_search=use_semantic_search_azure,
        semantic_config_name=semantic_config_name_azure, search_filter=search_filter_for_azure
    )

    retrieved_azure_chunks_final = retrieved_azure_chunks_initial
    if use_reranker and retrieved_azure_chunks_initial:
        reranker_model_instance = get_reranker_model()
        if reranker_model_instance:
            retrieved_azure_chunks_final = rerank_chunks(
                query=user_instruction, # Usar a instrução original do usuário para reranking
                chunks_details=retrieved_azure_chunks_initial,
                model=reranker_model_instance, top_n_rerank=top_k_rerank_azure
            )
    # Salva os chunks finais (após reranking) para possível exibição na UI
    if 'streamlit' in __import__('sys').modules:
        st.session_state.last_retrieved_chunks_details = retrieved_azure_chunks_final # Chunks pós-reranking

    context_from_azure_search = formatar_chunks_para_llm_azure(retrieved_azure_chunks_final)
    formatted_google_context = ""

    if enable_google_search_trigger and \
       should_trigger_google_search(user_instruction, retrieved_azure_chunks_final, min_azure_results_for_google_trigger, area_predita, tarefa_predita):
        raw_google_data = call_google_custom_search(user_instruction, num_results=num_google_results)
        formatted_google_context = formatar_google_results_para_llm(raw_google_data)

    # --- INÍCIO: INTEGRAÇÃO GRAPH_RAG ---
    graph_context_for_llm = ""
    if GRAPH_RAG_AVAILABLE and retrieved_azure_chunks_final: # Só processa se houver chunks e o módulo estiver disponível
        try:
            print("INFO RAG_UTILS: Iniciando processamento com GraphRAG...")
            # Passar user_instruction para GraphRAG ter o contexto da query original
            graph_module = GraphRAG(retrieved_documents=retrieved_azure_chunks_final, user_query=user_instruction)
            graph_context_for_llm = graph_module.generate_textual_summary_for_llm()
            print(f"INFO RAG_UTILS: Contexto do GraphRAG gerado: {graph_context_for_llm[:200]}...") # Log preview

            # Opcional: Gerar e armazenar caminho da visualização
            if 'streamlit' in sys.modules:
                 # Gerar um ID único para esta execução específica para evitar sobrescrever arquivos de visualização
                 unique_viz_id = graph_module.run_id # Usa o run_id do GraphRAG
                 output_viz_path = graph_module.visualize_graph(filename_prefix=f"lexautomate_graph_gen_{unique_viz_id[:8]}")
                 if output_viz_path:
                     st.session_state[f'last_graph_viz_path_general'] = output_viz_path # Chave genérica, pode ser específica da aba depois
                     print(f"INFO RAG_UTILS: Visualização do grafo salva em: {output_viz_path}")
                     # A UI precisaria de lógica para exibir um link para este arquivo.
                     # Ex: st.markdown(f"[Visualizar Grafo]({st.session_state.last_graph_viz_path_general})") - requer servir o arquivo
        except Exception as e_graph:
            print(f"ERRO RAG_UTILS: Falha durante o processamento do GraphRAG: {e_graph}")
            traceback.print_exc()
            graph_context_for_llm = "\nFalha ao gerar análise estrutural adicional dos documentos (grafo).\n"
    # --- FIM: INTEGRAÇÃO GRAPH_RAG ---

    combined_context = context_from_azure_search
    if formatted_google_context:
        combined_context += "\n" + formatted_google_context
    if graph_context_for_llm: # Adiciona o contexto do grafo se disponível
        combined_context += f"\n\n--- ANÁLISE ESTRUTURAL ADICIONAL (GRAFO DE CONHECIMENTO) ---\n{graph_context_for_llm}\n--- FIM DA ANÁLISE ESTRUTURAL ---\n"

    final_user_message = (
        f"{combined_context}\n\n"
        f"Considerando o CONTEXTO ADICIONAL RECUPERADO (incluindo a análise estrutural, se disponível) e o TEXTO COMPLETO DO DOCUMENTO FORNECIDO (se houver), "
        f"siga EXATAMENTE a seguinte instrução:\n\n"
        f"Instrução do Usuário: '{user_instruction}'\n\n"
        f"---\n**TEXTO COMPLETO DO DOCUMENTO (do arquivo carregado):**\n---\n"
        f"{context_document_text if context_document_text else 'Nenhum documento principal fornecido.'}\n"
        f"---\nFim do Documento\n---"
    )
    messages = [{"role": "system", "content": system_message_final}, {"role": "user", "content": final_user_message}]
    try:
        response = client_openai.chat.completions.create(
            model=azure_openai_deployment_llm, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        generated_text = response.choices[0].message.content
        return generated_text
    except Exception as e:
        print(f"ERRO RAG_UTILS (generate_response_with_conditional_google_search): {e}")
        return f"Erro ao gerar resposta: {e}"


# --- Função para o Consultor ---
MAX_CHAT_HISTORY_MESSAGES = 10 # Limita o número de mensagens do histórico a serem enviadas
def build_messages_for_llm_chat(system_message, chat_history, user_instruction_with_context):
    messages: list[dict[str,str]] = [{"role": "system", "content": system_message}]
    if chat_history: # Adiciona histórico do chat, limitado
        start_index = max(0, len(chat_history) - MAX_CHAT_HISTORY_MESSAGES)
        for msg_item in chat_history[start_index:]:
            # Garante que o item é um dicionário com 'role' e 'content'
            if isinstance(msg_item, dict) and "role" in msg_item and "content" in msg_item:
                messages.append({"role": msg_item["role"], "content": msg_item["content"]})
    messages.append({"role": "user", "content": user_instruction_with_context})
    return messages

def generate_consultor_response_with_rag(
    system_message_base: str, user_instruction: str, chat_history: list,
    search_client: SearchClient, client_openai: AzureOpenAI,
    azure_openai_deployment_llm: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    azure_openai_deployment_expansion: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    top_k_initial_chunks_consultor: int = 15, top_k_rerank_consultor: int = 7,
    use_semantic_search_in_consultor: bool = True,
    enable_google_search_trigger_consultor: bool = True,
    min_azure_results_for_google_trigger_consultor: int = 1,
    num_google_results_consultor: int = 2,
    use_reranker_consultor: bool = True # Habilita/desabilita reranker para o consultor
    ):

    if client_openai is None or search_client is None: return "Erro: Serviços de IA não configurados."

    area_predita, tarefa_predita, _, _ = classificar_texto(user_instruction, modelo_area_direito, modelo_tipo_tarefa)
    system_message_final = selecionar_prompt_dinamico(area_predita, tarefa_predita, system_message_base)
    search_filter_for_azure = None # Filtro para busca no Azure, se necessário

    retrieved_azure_chunks_initial = find_relevant_chunks_azure_search(
        original_user_query=user_instruction, search_client=search_client, client_openai=client_openai,
        azure_openai_deployment_for_expansion=azure_openai_deployment_expansion,
        top_k_initial_search=top_k_initial_chunks_consultor, use_semantic_search=use_semantic_search_in_consultor,
        search_filter=search_filter_for_azure
    )

    retrieved_azure_chunks_final = retrieved_azure_chunks_initial
    if use_reranker_consultor and retrieved_azure_chunks_initial:
        reranker_model_instance = get_reranker_model()
        if reranker_model_instance:
            retrieved_azure_chunks_final = rerank_chunks(
                query=user_instruction,
                chunks_details=retrieved_azure_chunks_initial,
                model=reranker_model_instance, top_n_rerank=top_k_rerank_consultor
            )
    # Salva os chunks finais para a interface do consultor
    if 'streamlit' in __import__('sys').modules:
        st.session_state.last_retrieved_chunks_details_consultor = retrieved_azure_chunks_final # Para exibir na UI

    context_from_azure_search = formatar_chunks_para_llm_azure(retrieved_azure_chunks_final, "Base Jurídica Interna")
    formatted_google_context_consultor = ""

    if enable_google_search_trigger_consultor and \
       should_trigger_google_search(user_instruction, retrieved_azure_chunks_final, min_azure_results_for_google_trigger_consultor, area_predita, tarefa_predita):
        raw_google_data_consultor = call_google_custom_search(user_instruction, num_results=num_google_results_consultor)
        formatted_google_context_consultor = formatar_google_results_para_llm(raw_google_data_consultor)

    # --- INÍCIO: INTEGRAÇÃO GRAPH_RAG PARA CONSULTOR ---
    graph_context_for_llm_consultor = ""
    if GRAPH_RAG_AVAILABLE and retrieved_azure_chunks_final: # Só processa se houver chunks
        try:
            print("INFO RAG_UTILS (Consultor): Iniciando processamento com GraphRAG...")
            graph_module_consultor = GraphRAG(retrieved_documents=retrieved_azure_chunks_final, user_query=user_instruction)
            graph_context_for_llm_consultor = graph_module_consultor.generate_textual_summary_for_llm()
            print(f"INFO RAG_UTILS (Consultor): Contexto do GraphRAG gerado: {graph_context_for_llm_consultor[:200]}...")

            # Opcional: Gerar e armazenar caminho da visualização para o consultor
            if 'streamlit' in sys.modules and st._is_running_with_streamlit:
                 unique_viz_id_consultor = graph_module_consultor.run_id
                 output_viz_path_consultor = graph_module_consultor.visualize_graph(filename_prefix=f"lexautomate_graph_consultor_{unique_viz_id_consultor[:8]}")
                 if output_viz_path_consultor:
                     st.session_state[f'last_graph_viz_path_consultor'] = output_viz_path_consultor
                     print(f"INFO RAG_UTILS (Consultor): Visualização do grafo salva em: {output_viz_path_consultor}")
        except Exception as e_graph_consultor:
            print(f"ERRO RAG_UTILS (Consultor): Falha durante o processamento do GraphRAG: {e_graph_consultor}")
            traceback.print_exc()
            graph_context_for_llm_consultor = "\nFalha ao gerar análise estrutural adicional dos documentos (grafo).\n"
    # --- FIM: INTEGRAÇÃO GRAPH_RAG PARA CONSULTOR ---


    combined_context_for_llm = context_from_azure_search
    if formatted_google_context_consultor:
        combined_context_for_llm += "\n" + formatted_google_context_consultor
    if graph_context_for_llm_consultor: # Adiciona contexto do grafo se disponível
        combined_context_for_llm += f"\n\n--- ANÁLISE ESTRUTURAL ADICIONAL (GRAFO DE CONHECIMENTO) ---\n{graph_context_for_llm_consultor}\n--- FIM DA ANÁLISE ESTRUTURAL ---\n"

    user_instruction_with_context_for_llm = (
        f"Pergunta: '{user_instruction}'\n\n"
        f"{combined_context_for_llm}\n\n" # Inclui Azure Search, Google e Grafo
        f"Com base no contexto fornecido e seu conhecimento jurídico, responda à pergunta de forma completa, didática e fundamentada, citando fontes relevantes quando apropriado."
    )
    messages_for_llm = build_messages_for_llm_chat(system_message_final, chat_history, user_instruction_with_context_for_llm)

    final_response = "Desculpe, não consegui processar seu pedido neste momento."
    try:
        response = client_openai.chat.completions.create(
            model=azure_openai_deployment_llm, messages=messages_for_llm,
            temperature=0.5, max_tokens=2000, top_p=0.95, # Parâmetros para respostas mais criativas/detalhadas
        )
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            final_response = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"ERRO CRÍTICO RAG_UTILS (generate_consultor_response_with_rag): {e}")
        final_response = f"Erro ao gerar resposta. Tente mais tarde." # Mensagem mais genérica para o usuário
    return final_response


# --- Geração de DOCX ---
def gerar_docx(texto_markdown):
    try:
        document = DocxDocument()
        style = document.styles['Normal']
        if style and style.font: font = style.font; font.name = 'Arial'; font.size = Pt(11) # type: ignore
        if style and style.paragraph_format: paragraph_format = style.paragraph_format; paragraph_format.space_before = Pt(0); paragraph_format.space_after = Pt(6) # type: ignore
        linhas = texto_markdown.split('\n')
        for linha_original in linhas:
            paragrafo_docx = document.add_paragraph()
            linha_strip = linha_original.strip()
            # Melhorado regex para headings, incluindo os que podem ter ** no texto
            match_heading = re.match(r'^(#{1,6})\s+(.*)', linha_strip)
            if match_heading:
                nivel = len(match_heading.group(1)); texto_titulo = match_heading.group(2).strip()
                # Remove ** do início e fim se for todo o título
                if texto_titulo.startswith('**') and texto_titulo.endswith('**') and len(texto_titulo) > 4:
                    texto_titulo = texto_titulo[2:-2]
                run = paragrafo_docx.add_run(texto_titulo); run.bold = True
                if nivel == 1: run.font.size = Pt(16)
                elif nivel == 2: run.font.size = Pt(14)
                elif nivel == 3: run.font.size = Pt(13)
                else: run.font.size = Pt(12)
                if paragrafo_docx.paragraph_format: paragrafo_docx.paragraph_format.space_before = Pt(12) if nivel <= 2 else Pt(6); paragrafo_docx.paragraph_format.space_after = Pt(6)
                continue # Próxima linha

            # Checa se a linha inteira é um título em negrito (sem #)
            eh_titulo_linha_inteira_bold = linha_strip.startswith('**') and linha_strip.endswith('**') and len(linha_strip) > 4 and linha_strip.count('**') == 2
            if eh_titulo_linha_inteira_bold:
                texto_do_titulo = linha_strip[2:-2]; run = paragrafo_docx.add_run(texto_do_titulo); run.bold = True; run.font.size = Pt(12)
                if paragrafo_docx.paragraph_format: paragrafo_docx.paragraph_format.space_before = Pt(6); paragrafo_docx.paragraph_format.space_after = Pt(6)
                continue # Próxima linha

            # Processa negrito dentro do parágrafo
            if linha_strip: # Só processa se não for linha vazia
                partes = re.split(r'(\*\*.+?\*\*)', linha_original) # Divide por **texto**
                for parte in partes:
                    if parte.startswith('**') and parte.endswith('**') and len(parte) > 4 : # Se for negrito
                        run_bold = paragrafo_docx.add_run(parte[2:-2]); run_bold.bold = True
                    elif parte: # Se for texto normal
                        paragrafo_docx.add_run(parte)
        buffer = BytesIO(); document.save(buffer); buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f"ERRO RAG_UTILS (gerar_docx): {e}")
        if 'streamlit' in __import__('sys').modules: st.error(f"Erro ao gerar DOCX: {e}")
        raise # Re-levanta a exceção para ser tratada externamente se necessário

print("INFO RAG_UTILS: Módulo `rag_utils.py` carregado (v13 - Revisão de nomes de função e GraphRAG integrado).")