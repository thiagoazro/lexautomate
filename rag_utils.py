# rag_utils.py
import streamlit as st
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery, QueryType
from azure.search.documents.indexes import SearchIndexClient # Necessário para get_index
from azure.core.credentials import AzureKeyCredential
import os
import time
import uuid
import traceback
import re
import json # Adicionado para json.loads em function calling
import requests # Adicionado para Google Search

from io import BytesIO
from docx import Document as DocxDocument
from docx.shared import Pt
from docx.enum.text import WD_LINE_SPACING

# --- ATENÇÃO: CREDENCIAIS HARDCODED - NÃO RECOMENDADO PARA PRODUÇÃO ---
# --- Configurações Azure OpenAI (Suas Chaves e Endpoints) ---
AZURE_OPENAI_ENDPOINT = 'https://lexautomate.openai.azure.com/'
AZURE_OPENAI_API_KEY = '6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA'
AZURE_OPENAI_DEPLOYMENT_LLM = 'lexautomate_agent' # Usado como padrão, pode ser sobrescrito por app
AZURE_OPENAI_DEPLOYMENT_EMBEDDING = 'text-embedding-3-large'
AZURE_API_VERSION = '2024-02-15-preview' # Verifique a versão mais recente compatível com suas features

# --- Configurações Azure AI Search ---
AZURE_SEARCH_ENDPOINT = "https://lexautomate-rag2.search.windows.net"
AZURE_SEARCH_KEY = "igJqXTXsYEC6gpIzFvjOvjm0WtSgd0Xrw8TNMDkwK9AzSeC5ft3H"
DEFAULT_AZURE_SEARCH_INDEX_NAME = "docs-index"
# Adicione nomes de configuração semântica se você os tiver e quiser usá-los por padrão
AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT = "default" # Exemplo, substitua se tiver um nome específico

# --- Configurações Google Custom Search API ---
GOOGLE_API_KEY = "AIzaSyCUT6HKCaOe51hTM7PY3sexnSJm1mlO5k0" # Chave fornecida pelo usuário
GOOGLE_CX_ID = "e3c7fef3c7d1c4a10" # CX ID ATUALIZADO conforme fornecido pelo usuário
# -----------------------------------------------------------------------

# --- Inicialização dos Clientes ---
@st.cache_resource
def get_openai_client():
    print("INFO RAG_UTILS: Inicializando cliente Azure OpenAI...")
    if not all([AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_API_VERSION, AZURE_OPENAI_DEPLOYMENT_LLM, AZURE_OPENAI_DEPLOYMENT_EMBEDDING]):
         print("ERRO RAG_UTILS: Configurações OpenAI incompletas."); st.error("ERRO: Configs OpenAI.")
         return None
    try:
        client = AzureOpenAI(
            api_version=AZURE_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY
        )
        try:
            client.models.list() # Teste rápido para verificar a conexão
            print("INFO RAG_UTILS: Cliente Azure OpenAI inicializado e conectado com sucesso.")
        except Exception as me:
            print(f"AVISO RAG_UTILS: Cliente Azure OpenAI inicializado, mas teste de listagem de modelos falhou: {me}.")
        return client
    except Exception as e:
        print(f"ERRO CRÍTICO RAG_UTILS: Falha ao inicializar cliente Azure OpenAI: {traceback.format_exc()}");
        st.error(f"Falha OpenAI: {e}");
        return None

@st.cache_resource
def get_azure_search_client(index_name: str = DEFAULT_AZURE_SEARCH_INDEX_NAME):
    print(f"INFO RAG_UTILS: Inicializando cliente Azure AI Search para o índice '{index_name}'...")
    if not all([AZURE_SEARCH_ENDPOINT, index_name, AZURE_SEARCH_KEY]):
        print("ERRO RAG_UTILS: Configurações do Azure AI Search incompletas."); st.error("ERRO: Configs AI Search.")
        return None
    try:
        search_credential = AzureKeyCredential(AZURE_SEARCH_KEY)
        search_client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=index_name, credential=search_credential)

        # Testar conexão e obter informações do índice
        try:
            index_admin_client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=search_credential)
            idx_properties = index_admin_client.get_index(index_name)
            semantic_config_name_to_log = "Nenhuma"
            if idx_properties.semantic_search and idx_properties.semantic_search.configurations:
                 semantic_config_name_to_log = f"'{idx_properties.semantic_search.configurations[0].name}'"
            print(f"INFO RAG_UTILS: Conexão ao índice '{index_name}' OK. Configuração semântica: {semantic_config_name_to_log}.")
            print(f"INFO RAG_UTILS: Contagem atual de documentos no índice '{index_name}': {search_client.get_document_count()}")
        except Exception as se_test:
            print(f"AVISO RAG_UTILS: Falha ao obter detalhes do índice '{index_name}' ou contagem de documentos: {se_test}");
            # Não impede a criação do cliente, mas loga o aviso.
        return search_client
    except Exception as e:
        print(f"ERRO CRÍTICO RAG_UTILS: Falha ao inicializar Azure AI Search Client: {traceback.format_exc()}");
        st.error(f"Falha Azure AI Search: {e}");
        return None

# --- Funções de Busca Externa (Google) ---
def call_google_custom_search(query: str, num_results: int = 3) -> list:
    """
    Chama a Google Custom Search API e retorna os resultados formatados.
    Retorna uma lista de dicionários, cada um com 'title', 'link', 'snippet'.
    """
    if not GOOGLE_API_KEY:
        print("ALERTA RAG_UTILS: GOOGLE_API_KEY não configurada.")
        return []
    if not GOOGLE_CX_ID: # Removida a verificação do placeholder, pois agora deve estar preenchido
        print("ALERTA RAG_UTILS: GOOGLE_CX_ID não configurado.")
        return []

    print(f"INFO RAG_UTILS: Realizando Google Custom Search para: '{query}' com {num_results} resultados.")
    try:
        url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_CX_ID}&q={query}&num={num_results}&hl=pt-BR"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        search_results = response.json()

        formatted_results = []
        if "items" in search_results:
            for item in search_results.get("items", []):
                title = item.get("title")
                link = item.get("link")
                snippet = item.get("snippet", item.get("htmlSnippet"))
                if snippet:
                    snippet = re.sub('<[^<]+?>', '', snippet).strip()
                    snippet = re.sub('\s+', ' ', snippet)
                formatted_results.append({"title": title, "link": link, "snippet": snippet})
        print(f"INFO RAG_UTILS: Google Search para '{query}' retornou {len(formatted_results)} resultados.")
        return formatted_results
    except requests.exceptions.Timeout:
        print(f"ERRO RAG_UTILS: Timeout ao chamar Google Custom Search API para query: {query}")
    except requests.exceptions.HTTPError as e:
        print(f"ERRO RAG_UTILS: Erro HTTP ({e.response.status_code}) ao chamar Google Custom Search API: {e}. Resposta: {e.response.text if e.response else 'N/A'}")
    except requests.exceptions.RequestException as e:
        print(f"ERRO RAG_UTILS: Falha na requisição ao Google Custom Search API: {e}")
    except json.JSONDecodeError as e_json: 
        print(f"ERRO RAG_UTILS: Falha ao decodificar resposta JSON do Google Custom Search. Erro: {e_json}. Resposta: {response.text if 'response' in locals() else 'N/A'}")
    except Exception as e_generic: 
        print(f"ERRO RAG_UTILS: Erro inesperado no call_google_custom_search: {e_generic}\n{traceback.format_exc()}")
    return []

# --- Funções Auxiliares e de Decisão ---
def should_trigger_google_search(user_instruction: str, azure_search_results: list, min_azure_results_threshold: int = 1) -> bool:
    palavras_chave_busca_web = [
        "pesquise na web", "busque na internet", "notícias recentes sobre",
        "informações atuais sobre", "google por", "qual a cotação atual",
        "dados atualizados de", "legislação mais recente sobre", "jurisprudência recente sobre"
    ]
    if any(keyword.lower() in user_instruction.lower() for keyword in palavras_chave_busca_web):
        print("INFO RAG_UTILS: Busca no Google acionada por palavra-chave explícita na instrução.")
        return True
    if not azure_search_results or len(azure_search_results) < min_azure_results_threshold:
        print(f"INFO RAG_UTILS: Busca no Google acionada por resultados insuficientes do Azure Search (encontrados: {len(azure_search_results)}, mínimo desejado: {min_azure_results_threshold}).")
        return True
    return False

def formatar_google_results_para_llm(google_results: list) -> str:
    if not google_results:
        return "\n\n--- CONTEXTO DA BUSCA NA WEB (Google) ---\nNenhuma informação adicional encontrada na busca web para esta consulta.\n--- FIM DO CONTEXTO DA BUSCA NA WEB ---\n"
    context = "\n\n--- INÍCIO DO CONTEXTO DA BUSCA NA WEB (Google) ---\n"
    context += "As seguintes informações foram recuperadas da internet:\n"
    for i, res in enumerate(google_results):
        context += f"\n[WEB {i+1}: {res.get('title', 'N/A')}] (Link: {res.get('link', 'N/A')})\nSnippet: {res.get('snippet', 'N/A')}\n"
    context += "--- FIM DO CONTEXTO DA BUSCA NA WEB (Google) ---\n"
    return context

# --- Funções de Embedding e Busca no Azure AI Search ---
def get_embedding(text_chunk: str, client_openai: AzureOpenAI, deployment_name: str = AZURE_OPENAI_DEPLOYMENT_EMBEDDING):
    if not text_chunk or client_openai is None: return None
    try:
        processed_chunk = ' '.join(text_chunk.replace('\n', ' ').split())
        if not processed_chunk:
            print("  AVISO RAG_UTILS: Chunk vazio após processamento, não será gerado embedding.")
            return None
        response = client_openai.embeddings.create(input=[processed_chunk], model=deployment_name) # Input deve ser uma lista
        return response.data[0].embedding
    except Exception as e:
        print(f"  ERRO RAG_UTILS: Falha em get_embedding para chunk '{processed_chunk[:50]}...': {e}\n{traceback.format_exc()}")
        return None

def find_relevant_chunks_azure_search(
    query_text: str,
    search_client: SearchClient,
    client_openai: AzureOpenAI, # Necessário para gerar embedding da query
    top_k: int = 5,
    use_semantic_search: bool = True, 
    semantic_config_name: str = AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT,
    query_language: str = "pt-BR", 
    query_speller: str = "lexicon" 
):
    if not query_text or search_client is None or client_openai is None:
        print("ALERTA RAG_UTILS: Parâmetros inválidos para find_relevant_chunks_azure_search.")
        return []

    query_embedding = get_embedding(query_text, client_openai)
    if query_embedding is None:
        print("AVISO RAG_UTILS: Não foi possível gerar embedding para a consulta. A pesquisa vetorial será ignorada.")

    vector_query = None
    if query_embedding:
        vector_query = VectorizedQuery(
            vector=query_embedding,
            k_nearest_neighbors=top_k,
            fields="content_vector", 
            exhaustive=True 
        )

    print(f"INFO RAG_UTILS: Buscando top_{top_k} chunks no Azure AI Search para: '{query_text[:100]}...' | Semântica: {use_semantic_search}")

    try:
        fields_to_select = ["chunk_id", "document_id", "arquivo_origem", "content", "tipo_documento", "language_code"]
        
        search_args = {
            "vector_queries": [vector_query] if vector_query else None,
            "select": fields_to_select,
            "top": top_k
        }

        if use_semantic_search:
            search_args.update({
                "search_text": query_text, 
                "query_type": QueryType.SEMANTIC,
                "semantic_configuration_name": semantic_config_name,
                "query_caption": "extractive", 
                "query_answer": "extractive",  
                "query_language": query_language,
                "query_speller": query_speller
            })
        else:
            search_args["search_text"] = query_text if not vector_query else None 

        search_results_iterable = search_client.search(**search_args)
        retrieved_chunks_details = []

        print(f"\n--- DETALHES DOS CHUNKS RECUPERADOS DO AZURE AI SEARCH (Consulta: '{query_text[:50]}...') ---")
        for i, doc in enumerate(search_results_iterable):
            chunk_detail = {
                "rank": i + 1,
                "chunk_id": doc.get("chunk_id", "N/A"),
                "document_id": doc.get("document_id", "N/A"),
                "arquivo_origem": doc.get("arquivo_origem", "N/A"),
                "tipo_documento": doc.get("tipo_documento", "N/A"),
                "score": doc.get("@search.score"), 
                "reranker_score": doc.get("@search.reranker_score"), 
                "content": doc.get("content", ""),
                "content_preview": doc.get("content", "")[:200] + "...",
                "semantic_caption": None,
            }
            if use_semantic_search and "@search.captions" in doc and doc["@search.captions"]:
                chunk_detail["semantic_caption"] = " ".join([c.text for c in doc["@search.captions"] if c.text])
            retrieved_chunks_details.append(chunk_detail)

            print(f"  Chunk #{chunk_detail['rank']}: ID: {chunk_detail['chunk_id']}, Origem: {chunk_detail['arquivo_origem']}")
            print(f"    Score Busca: {chunk_detail['score']:.4f if chunk_detail['score'] else 'N/A'}")
            if chunk_detail['reranker_score'] is not None:
                print(f"    Score Reclassificação Semântica: {chunk_detail['reranker_score']:.4f}")
            if chunk_detail["semantic_caption"]:
                print(f"    Caption Semântico: '{chunk_detail['semantic_caption']}'")
            print(f"    Conteúdo (início): {chunk_detail['content_preview']}")
            print("-" * 20)

        print(f"--- FIM DETALHES DOS CHUNKS (Azure AI Search) ---")
        print(f"INFO RAG_UTILS: Encontrados {len(retrieved_chunks_details)} chunks relevantes no Azure (após possível reclassificação).")
        return retrieved_chunks_details

    except Exception as e:
        print(f"ERRO RAG_UTILS: Falha na pesquisa no Azure AI Search: {e}\n{traceback.format_exc()}")
        return []

def formatar_chunks_para_llm_azure(chunks_info_list: list, fonte_descricao: str = "Base de Conhecimento Interna (Azure AI Search)") -> str:
    context = f"\n\n--- INÍCIO DO CONTEXTO DE {fonte_descricao} ---\n"
    if not chunks_info_list:
        context += "Nenhum documento ou trecho relevante foi encontrado nesta fonte para a consulta atual.\n"
    else:
        for i, chunk_info in enumerate(chunks_info_list, 1):
            content = chunk_info.get('content', 'Conteúdo não disponível')
            source = chunk_info.get('arquivo_origem', 'Fonte desconhecida')
            tipo_doc = chunk_info.get('tipo_documento', 'N/A')
            score = chunk_info.get('score', None)
            reranker_score = chunk_info.get('reranker_score', None)

            score_info = []
            if score is not None: score_info.append(f"Score Busca: {score:.3f}")
            if reranker_score is not None: score_info.append(f"Score Semântico: {reranker_score:.3f}")
            score_str = f" ({', '.join(score_info)})" if score_info else ""

            context += f"\n[FONTE INTERNA {i}: {source} (Tipo: {tipo_doc}){score_str}]\n"
            if chunk_info.get("semantic_caption"):
                context += f"Destaque Semântico: {chunk_info['semantic_caption']}\n"
            context += f"Conteúdo do Trecho: {content}\n"
    context += f"--- FIM DO CONTEXTO DE {fonte_descricao} ---\n"
    return context

# --- Estratégia 1: Geração de Resposta com Fallback para Google Search ---
def generate_response_with_conditional_google_search(
    system_message: str,
    user_instruction: str,
    context_document_text: str,
    search_client: SearchClient,
    client_openai: AzureOpenAI,
    azure_openai_deployment: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    top_k_azure: int = 5, 
    use_semantic_search_azure: bool = True,
    semantic_config_name_azure: str = AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT,
    enable_google_search_fallback: bool = True,
    min_azure_results_for_fallback: int = 2, 
    num_google_results: int = 3,
    temperature: float = 0.1,
    max_tokens: int = 4000 
):
    print(f"INFO RAG_UTILS (CondSearch): Gerando resposta para: '{user_instruction[:100]}...'")

    retrieved_azure_chunks = find_relevant_chunks_azure_search(
        user_instruction, search_client, client_openai, 
        top_k=top_k_azure,
        use_semantic_search=use_semantic_search_azure,
        semantic_config_name=semantic_config_name_azure
    )
    context_from_azure_search = formatar_chunks_para_llm_azure(retrieved_azure_chunks)
    
    if 'streamlit' in sys.modules: 
        st.session_state.last_retrieved_chunks_details = retrieved_azure_chunks


    context_from_google_search = ""
    if GOOGLE_API_KEY and GOOGLE_CX_ID and \
       enable_google_search_fallback and \
       should_trigger_google_search(user_instruction, retrieved_azure_chunks, min_azure_results_for_fallback):
        print(f"INFO RAG_UTILS (CondSearch): Acionando Google Search com query: '{user_instruction}'")
        google_search_results = call_google_custom_search(user_instruction, num_results=num_google_results)
        context_from_google_search = formatar_google_results_para_llm(google_search_results)

    combined_context = context_from_azure_search
    if context_from_google_search:
        combined_context += "\n" + context_from_google_search

    final_user_message = (
        f"{combined_context}\n\n"
        f"Considerando o CONTEXTO ADICIONAL RECUPERADO acima (que pode incluir Fontes Documentais Internas e/ou informações da web) e, PRINCIPALMENTE, o TEXTO COMPLETO DO DOCUMENTO FORNECIDO abaixo (se houver), "
        f"siga EXATAMENTE a seguinte instrução:\n\n"
        f"Instrução do Usuário: '{user_instruction}'\n\n"
        f"---\n**TEXTO COMPLETO DO DOCUMENTO FORNECIDO (do arquivo carregado):**\n---\n"
        f"{context_document_text if context_document_text else 'Nenhum documento principal foi fornecido para esta tarefa.'}\n"
        f"---\nFim do Documento Fornecido\n---"
    )
    messages = [{"role": "system", "content": system_message}, {"role": "user", "content": final_user_message}]

    print("INFO RAG_UTILS (CondSearch): Enviando requisição para Azure OpenAI...")
    try:
        response = client_openai.chat.completions.create(
            model=azure_openai_deployment, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        generated_text = response.choices[0].message.content
        print("INFO RAG_UTILS (CondSearch): Resposta recebida do Azure OpenAI.")
        return generated_text 
    except Exception as e:
        print(f"ERRO RAG_UTILS (CondSearch): Erro ao chamar Azure OpenAI: {e}\n{traceback.format_exc()}")
        return f"Erro ao gerar resposta: {e}" 

# --- Estratégia 2: Decisão do LLM com Function Calling ---
GOOGLE_SEARCH_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "google_custom_search_tool",
        "description": (
            "Realiza uma busca na internet usando o Google Custom Search para obter informações atuais, "
            "notícias, ou dados que não estão presentes no conhecimento interno ou nos documentos fornecidos. "
            "Use esta ferramenta quando a pergunta do usuário explicitamente pedir informações da web, "
            "ou quando você julgar que o conhecimento disponível é insuficiente ou desatualizado. "
            "Não use para consultas sobre o conteúdo específico de documentos já fornecidos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A consulta de busca precisa e concisa para o Google. Exemplo: 'últimas decisões STF sobre PIS/COFINS 2024'."
                },
                "num_results": {
                    "type": "integer",
                    "description": "Número de resultados de busca a serem retornados (entre 1 e 5). Padrão é 3.",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    }
}
AVAILABLE_FUNCTIONS_MAP = {"google_custom_search_tool": call_google_custom_search}

def generate_response_with_function_calling(
    system_message: str,
    user_instruction: str,
    context_document_text: str,
    search_client: SearchClient,
    client_openai: AzureOpenAI,
    azure_openai_deployment: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    top_k_azure: int = 3,
    use_semantic_search_azure: bool = True,
    semantic_config_name_azure: str = AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT,
    temperature: float = 0.1,
    max_tokens: int = 4000,
    max_function_calls: int = 2 
):
    print(f"INFO RAG_UTILS (FuncCall): Gerando resposta para: '{user_instruction[:100]}...'")

    context_from_azure_search = ""
    if search_client:
        retrieved_azure_chunks = find_relevant_chunks_azure_search(
            user_instruction, search_client, client_openai,
            top_k=top_k_azure, use_semantic_search=use_semantic_search_azure,
            semantic_config_name=semantic_config_name_azure
        )
        context_from_azure_search = formatar_chunks_para_llm_azure(retrieved_azure_chunks)
        if 'streamlit' in sys.modules:
             st.session_state.last_retrieved_chunks_details = retrieved_azure_chunks


    initial_user_content = (
        f"{context_from_azure_search}\n\n"
        f"Considerando o CONTEXTO ADICIONAL RECUPERADO acima (se houver) e, PRINCIPALMENTE, o TEXTO COMPLETO DO DOCUMENTO FORNECIDO abaixo (se houver), "
        f"siga EXATAMENTE a seguinte instrução. Você pode usar ferramentas disponíveis se julgar necessário para obter informações mais atuais ou que não estão no contexto fornecido.\n\n"
        f"Instrução do Usuário: '{user_instruction}'\n\n"
        f"---\n**TEXTO COMPLETO DO DOCUMENTO FORNECIDO (do arquivo carregado):**\n---\n"
        f"{context_document_text if context_document_text else 'Nenhum documento principal foi fornecido para esta tarefa.'}\n"
        f"---\nFim do Documento Fornecido\n---"
    )
    messages = [{"role": "system", "content": system_message}, {"role": "user", "content": initial_user_content}]
    tools = [GOOGLE_SEARCH_TOOL_DEFINITION] if (GOOGLE_API_KEY and GOOGLE_CX_ID) else []
    tool_choice = "auto" if tools else None


    for i in range(max_function_calls + 1): 
        print(f"INFO RAG_UTILS (FuncCall): Iteração {i+1}. Enviando para Azure OpenAI. Tool choice: {tool_choice}")
        try:
            response = client_openai.chat.completions.create(
                model=azure_openai_deployment, messages=messages,
                tools=tools if tool_choice == "auto" and tools else None,
                tool_choice=tool_choice if tool_choice == "auto" and tools else None,
                temperature=temperature, max_tokens=max_tokens
            )
        except Exception as e:
            print(f"ERRO RAG_UTILS (FuncCall): Erro ao chamar Azure OpenAI: {e}\n{traceback.format_exc()}")
            return f"Erro ao gerar resposta: {e}" 

        response_message = response.choices[0].message
        messages.append(response_message)

        if response_message.tool_calls and tools:
            print(f"INFO RAG_UTILS (FuncCall): LLM solicitou chamada de ferramenta: {response_message.tool_calls[0].function.name}")
            tool_choice = "auto" 
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_to_call = AVAILABLE_FUNCTIONS_MAP.get(function_name)
                tool_response_content = f"Erro: Ferramenta '{function_name}' não encontrada ou não configurada corretamente."
                
                if function_to_call and GOOGLE_API_KEY and GOOGLE_CX_ID:
                    try:
                        function_args = json.loads(tool_call.function.arguments)
                        query = function_args.get("query")
                        num_res = function_args.get("num_results", 3)
                        
                        print(f"INFO RAG_UTILS (FuncCall): Executando '{function_name}' com query: '{query}', num_results: {num_res}")
                        function_response_data = function_to_call(query=query, num_results=num_res)
                        
                        if function_response_data:
                            tool_response_content = "Resultados da busca na web:\n"
                            for item_idx, item_data in enumerate(function_response_data): 
                                tool_response_content += f"- Título {item_idx+1}: {item_data.get('title', 'N/A')}\n  Snippet: {item_data.get('snippet', 'N/A')}\n  Link: {item_data.get('link', 'N/A')}\n"
                        else:
                            tool_response_content = "Nenhum resultado encontrado na busca web para esta consulta."
                    except Exception as e_func:
                        print(f"ERRO RAG_UTILS (FuncCall): Erro ao executar '{function_name}': {e_func}\n{traceback.format_exc()}")
                        tool_response_content = f"Erro ao executar a função {function_name}: {str(e_func)}"
                else:
                     print(f"ALERTA RAG_UTILS (FuncCall): Ferramenta '{function_name}' não pode ser chamada (não encontrada ou Google API/CX não configurados).")


                messages.append({
                    "tool_call_id": tool_call.id, "role": "tool",
                    "name": function_name, "content": tool_response_content,
                })
        else:
            final_answer = response_message.content
            print("INFO RAG_UTILS (FuncCall): LLM gerou resposta final.")
            return final_answer 
    
    print("ALERTA RAG_UTILS (FuncCall): Máximo de chamadas de função atingido. Retornando última mensagem do assistente.")
    last_assistant_message = next((m.content for m in reversed(messages) if m.role == "assistant" and m.content), None)
    if last_assistant_message:
        return last_assistant_message 
    return "Não foi possível obter uma resposta final após o máximo de chamadas de função." 

# --- Função de Geração de DOCX (Mantida do seu código original) ---
def gerar_docx(texto_markdown):
    print("INFO RAG_UTILS: Gerando arquivo DOCX com interpretação de Markdown...")
    try:
        document = DocxDocument()
        style = document.styles['Normal']
        font = style.font
        font.name = 'Arial' 
        font.size = Pt(11)  
        
        paragraph_format = style.paragraph_format
        paragraph_format.space_before = Pt(0)
        paragraph_format.space_after = Pt(6) 

        linhas = texto_markdown.split('\n')
        for linha_idx, linha_original in enumerate(linhas):
            paragrafo_docx = document.add_paragraph()
            paragrafo_docx.style = document.styles['Normal']

            linha_strip = linha_original.strip()

            match_heading = re.match(r'^(#{1,6})\s+(.*)', linha_strip)
            if match_heading:
                nivel = len(match_heading.group(1))
                texto_titulo = match_heading.group(2).strip()
                if texto_titulo.startswith('**') and texto_titulo.endswith('**') and len(texto_titulo) > 4:
                    texto_titulo = texto_titulo[2:-2]
                
                run = paragrafo_docx.add_run(texto_titulo)
                run.bold = True
                if nivel == 1: run.font.size = Pt(16)
                elif nivel == 2: run.font.size = Pt(14)
                elif nivel == 3: run.font.size = Pt(13)
                else: run.font.size = Pt(12)
                
                paragrafo_docx.paragraph_format.space_before = Pt(12) if nivel <= 2 else Pt(6)
                paragrafo_docx.paragraph_format.space_after = Pt(6)
                continue

            eh_titulo_linha_inteira_bold = linha_strip.startswith('**') and \
                                           linha_strip.endswith('**') and \
                                           len(linha_strip) > 4 and \
                                           linha_strip.count('**') == 2 
            if eh_titulo_linha_inteira_bold:
                texto_do_titulo = linha_strip[2:-2]
                run = paragrafo_docx.add_run(texto_do_titulo)
                run.bold = True
                run.font.size = Pt(12) 
                paragrafo_docx.paragraph_format.space_before = Pt(6)
                paragrafo_docx.paragraph_format.space_after = Pt(6)
                continue

            if linha_strip: 
                partes = re.split(r'(\*\*.+?\*\*)', linha_original) 
                for parte_idx, parte in enumerate(partes):
                    if parte.startswith('**') and parte.endswith('**') and len(parte) > 4:
                        texto_do_negrito = parte[2:-2]
                        run_bold = paragrafo_docx.add_run(texto_do_negrito)
                        run_bold.bold = True
                    elif parte: 
                        paragrafo_docx.add_run(parte)
            else: 
                pass


        buffer = BytesIO()
        document.save(buffer)
        buffer.seek(0)
        print("INFO RAG_UTILS: Arquivo DOCX gerado com sucesso.")
        return buffer.getvalue()
    except Exception as e:
        print(f"ERRO RAG_UTILS: Falha ao gerar DOCX: {e}\n{traceback.format_exc()}")
        if 'streamlit' in sys.modules:
            st.error(f"Erro ao gerar arquivo DOCX: {e}")
        raise 

import sys

def generate_response_with_rag(
    system_message,
    user_instruction,
    context_document_text,
    search_client,
    client_openai,
    top_k_chunks=5, 
    use_semantic_search_in_rag=True 
    ):
    print("AVISO RAG_UTILS: Chamando função de compatibilidade 'generate_response_with_rag'. Considere migrar para as novas funções com Google Search.")
    generated_text_result = generate_response_with_conditional_google_search(
        system_message=system_message,
        user_instruction=user_instruction,
        context_document_text=context_document_text,
        search_client=search_client,
        client_openai=client_openai,
        azure_openai_deployment=AZURE_OPENAI_DEPLOYMENT_LLM, 
        top_k_azure=top_k_chunks,
        use_semantic_search_azure=use_semantic_search_in_rag,
        semantic_config_name_azure=AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT, 
    )
    if isinstance(generated_text_result, tuple): 
        return generated_text_result[0]
    return generated_text_result

MAX_CHAT_HISTORY_MESSAGES = 10 

def build_messages_for_llm_chat(system_message, chat_history, user_instruction_with_context):
    messages = [{"role": "system", "content": system_message}]
    if chat_history:
        start_index = max(0, len(chat_history) - MAX_CHAT_HISTORY_MESSAGES)
        for msg in chat_history[start_index:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_instruction_with_context})
    return messages

def generate_consultor_response_with_rag( 
    system_message: str,
    user_instruction: str,
    chat_history: list,
    search_client: SearchClient,
    client_openai: AzureOpenAI,
    top_k_chunks: int = 3, 
    use_semantic_search_in_consultor: bool = True, 
    enable_google_search: bool = True,
    min_azure_results_for_google: int = 1,
    num_google_results_consultor: int = 2
    ):
    print(f"INFO RAG_UTILS (Consultor): Gerando resposta para: '{user_instruction[:100]}...'")

    retrieved_azure_chunks = find_relevant_chunks_azure_search(
        user_instruction, search_client, client_openai,
        top_k=top_k_chunks,
        use_semantic_search=use_semantic_search_in_consultor,
        semantic_config_name=AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT
    )
    context_from_azure_search = formatar_chunks_para_llm_azure(
        retrieved_azure_chunks,
        fonte_descricao="Base de Conhecimento Jurídico Interna"
    )
    if 'streamlit' in sys.modules:
        st.session_state.last_retrieved_chunks_details_consultor = retrieved_azure_chunks

    context_from_google_search = ""
    if GOOGLE_API_KEY and GOOGLE_CX_ID and \
       enable_google_search and \
       should_trigger_google_search(user_instruction, retrieved_azure_chunks, min_azure_results_for_google):
        print(f"INFO RAG_UTILS (Consultor): Acionando Google Search com query: '{user_instruction}'")
        google_search_results = call_google_custom_search(user_instruction, num_results=num_google_results_consultor)
        context_from_google_search = formatar_google_results_para_llm(google_search_results)

    combined_context_for_llm = context_from_azure_search
    if context_from_google_search:
        combined_context_for_llm += "\n" + context_from_google_search

    user_instruction_with_context_for_llm = (
        f"Pergunta do Utilizador: '{user_instruction}'\n\n"
        f"{combined_context_for_llm}\n\n"
        f"Com base no contexto acima (que pode incluir informações da base interna e/ou da web) e no seu conhecimento geral, por favor, responda à pergunta do utilizador de forma completa e didática, citando as fontes do contexto quando apropriado."
    )

    messages_for_llm = build_messages_for_llm_chat(
        system_message,
        chat_history, 
        user_instruction_with_context_for_llm
    )

    final_response = "Desculpe, não consegui processar o seu pedido para o consultor neste momento."
    print(f"INFO RAG_UTILS (Consultor): Enviando para LLM ({AZURE_OPENAI_DEPLOYMENT_LLM}) com {len(messages_for_llm)} mensagens.")
    try:
        response = client_openai.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_LLM, 
            messages=messages_for_llm,
            temperature=0.5, 
            max_tokens=2000,
            top_p=0.95,
        )
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            final_response = response.choices[0].message.content.strip()
        else:
            print("ERRO RAG_UTILS (Consultor): Resposta da API LLM inválida.")
    except Exception as e:
        print(f"ERRO CRÍTICO RAG_UTILS (Consultor): Falha chat.completions: {e}\n{traceback.format_exc()}")
        final_response = f"Erro ao gerar resposta do consultor. Tente novamente mais tarde."
    return final_response
