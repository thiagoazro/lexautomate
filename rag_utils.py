# rag_utils.py
import streamlit as st
from pinecone import Pinecone
from openai import AzureOpenAI
import os
import time # Para adicionar um pequeno delay em caso de erro de rate limit (opcional)

# --- Configurações (DIRETO NO CÓDIGO - NÃO RECOMENDADO PARA PRODUÇÃO!) ---

# ATENÇÃO: Colocar chaves diretamente no código é um RISCO DE SEGURANÇA.
# Remova antes de compartilhar ou enviar para versionamento (Git).
# Use variáveis de ambiente ou um gerenciador de segredos em produção.

# Configs Pinecone
PINECONE_API_KEY = "pcsk_3hauhv_LYhcF6L6vCkkUc5U3WxkBjC2TALRB9GzAkkAN5GihNkJ27XFKxtSgP24NipbtLt"
PINECONE_INDEX_NAME = "lexautomate"

# Configs Azure OpenAI
AZURE_OPENAI_ENDPOINT = 'https://lexautomate.openai.azure.com/'
AZURE_OPENAI_API_KEY = '6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA'
AZURE_OPENAI_DEPLOYMENT_LLM = 'lexautomate_agent' # Deployment do GPT-4o (ou similar) para GERAÇÃO
AZURE_OPENAI_DEPLOYMENT_EMBEDDING = 'text-embedding-3-large' # Deployment do text-embedding-3-large para EMBEDDING
AZURE_API_VERSION = '2024-02-15-preview' # Ou a versão que você estiver usando

# --- Inicialização dos Clientes (com Cache do Streamlit) ---

@st.cache_resource # Cacheia para não reconectar a cada interação
def get_pinecone_index():
    """Inicializa e retorna o objeto do índice Pinecone."""
    print("INFO: Inicializando conexão com Pinecone...")
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)

        # Chama list_indexes() para obter o objeto IndexList
        # CORREÇÃO: Chame o método .names() para obter a lista de nomes
        print("INFO: Obtendo lista de índices...")
        # Obtenha o objeto IndexList primeiro para verificar o formato, se necessário
        index_list_object = pc.list_indexes()

        # CORREÇÃO: Verifique se o objeto retornado tem o método 'names' e chame-o
        if hasattr(index_list_object, 'names') and callable(index_list_object.names):
            index_names = index_list_object.names() # <-- CORREÇÃO: Chamar o método
            print(f"INFO: Nomes de índices obtidos via .names(): {index_names}")
        elif isinstance(index_list_object, list): # Fallback para o caso anterior (se a biblioteca mudar)
             print("AVISO: pc.list_indexes() retornou uma lista diretamente. Adaptando...")
             index_names = [index_info.get('name') for index_info in index_list_object if isinstance(index_info, dict) and 'name' in index_info]
             print(f"INFO: Nomes de índices obtidos via lista de dicionários: {index_names}")
        else:
            st.error(f"Erro Crítico: Resultado inesperado ao listar índices do Pinecone. Tipo: {type(index_list_object)}. Resultado: {index_list_object}. Verifique a versão da biblioteca pinecone-client ou o estado do serviço.")
            print(f"ERRO: Resultado inesperado de pc.list_indexes(). Tipo: {type(index_list_object)}. Resultado: {index_list_object}")
            return None


        if not index_names:
             st.error(f"Erro Crítico: A lista de nomes de índices do Pinecone está vazia. Verifique se há índices na sua conta.")
             print("ERRO: A lista de nomes de índices retornada está vazia.")
             return None

        # Verifica se o índice desejado existe na lista de nomes
        if PINECONE_INDEX_NAME not in index_names:
             st.error(f"Erro Crítico: Índice Pinecone '{PINECONE_INDEX_NAME}' não encontrado na sua conta. Índices disponíveis: {', '.join(index_names) if index_names else 'Nenhum índice encontrado'}. Verifique o nome configurado ou crie o índice no console Pinecone.")
             print(f"ERRO: Índice Pinecone '{PINECONE_INDEX_NAME}' não encontrado na lista: {index_names}")
             return None

        # Se chegou aqui, o índice existe e a conexão básica funcionou
        index = pc.Index(PINECONE_INDEX_NAME)

        # Testa a conexão buscando estatísticas (opcional mas útil para confirmar acesso ao índice)
        try:
            index.describe_index_stats()
            print(f"INFO: Conexão com índice Pinecone '{PINECONE_INDEX_NAME}' estabelecida com sucesso.")
            st.sidebar.success("Pinecone Conectado", icon="🌲") # Feedback visual
            return index
        except Exception as stats_error:
            st.warning(f"Conexão básica com Pinecone OK, mas falha ao obter estatísticas do índice '{PINECONE_INDEX_NAME}': {stats_error}. O índice pode não estar totalmente pronto ou haver um problema de permissão/rede secundário.")
            print(f"AVISO: Falha ao obter estatísticas do índice: {stats_error}")
            # Optamos por retornar o índice, pois a conexão inicial funcionou
            return index

    except Exception as e:
        st.error(f"Falha Crítica ao conectar ao Pinecone: {e}")
        print(f"ERRO: Falha ao conectar ao Pinecone: {e}")
        return None


@st.cache_resource # Cacheia para não recriar o cliente a cada interação
def get_openai_client():
    """Inicializa e retorna o cliente Azure OpenAI."""
    print("INFO: Inicializando cliente Azure OpenAI...")
    try:
        client = AzureOpenAI(
            api_version=AZURE_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
        )
        # Testa a conexão listando modelos (opcional mas útil)
        # Pode ser removido se causar lentidão ou se a permissão for restrita
        try:
            client.models.list()
            print("INFO: Cliente Azure OpenAI inicializado com sucesso.")
            st.sidebar.success("Azure OpenAI Conectado", icon="🤖") # Feedback visual
            return client
        except Exception as models_error:
             st.warning(f"Conexão básica com Azure OpenAI OK, mas falha ao listar modelos: {models_error}. Verifique permissões ou estado do serviço. Continuar tentando usar o cliente...")
             print(f"AVISO: Falha ao listar modelos do Azure OpenAI: {models_error}")
             return client # Retorna o cliente mesmo que listar modelos falhe

    except Exception as e:
         st.error(f"Falha Crítica ao inicializar cliente Azure OpenAI: {e}")
         print(f"ERRO: Falha ao inicializar cliente Azure OpenAI: {e}")
         return None

# --- Funções Principais do RAG ---

def get_embedding(text_chunk, client_openai):
    """Gera embedding para um pedaço de texto usando o deployment Azure configurado."""
    if not text_chunk or client_openai is None:
         print("AVISO: Texto vazio ou cliente OpenAI inválido para get_embedding.")
         return None
    try:
        # Limpa espaços extras que podem atrapalhar alguns modelos
        processed_chunk = ' '.join(text_chunk.split())
        if not processed_chunk:
             print("AVISO: Chunk ficou vazio após processamento.")
             return None

        # Chama a API de embedding do Azure
        response = client_openai.embeddings.create(
            input=processed_chunk,
            model=AZURE_OPENAI_DEPLOYMENT_EMBEDDING # Usa o nome da deployment de embedding
        )
        return response.data[0].embedding
    except Exception as e:
        st.error(f"Erro na API de Embedding do Azure: {e}")
        print(f"ERRO: Falha em get_embedding: {e}")
        # Opcional: Adicionar retry simples para rate limits
        if "429" in str(e): # Código de erro para Rate Limit
             print("AVISO: Rate limit atingido na API de Embedding. Aguardando 1 segundo...")
             time.sleep(1)
             # Poderia tentar novamente aqui, mas simplificamos retornando None
        return None

def find_relevant_chunks_pinecone(query_text, pinecone_index, client_openai, top_k=5):
    """Busca chunks relevantes no índice Pinecone usando o embedding da query."""
    if not query_text or pinecone_index is None or client_openai is None:
        print("AVISO: Query vazia ou clientes inválidos para find_relevant_chunks_pinecone.")
        return [] # Retorna lista vazia se não puder buscar

    print(f"INFO: Gerando embedding para a query: '{query_text[:100]}...'")
    query_embedding = get_embedding(query_text, client_openai)

    if query_embedding is None:
        st.warning("Não foi possível gerar o embedding para a busca. Verifique os logs de erro.")
        print("ERRO: Falha ao gerar embedding para a query.")
        return [] # Retorna lista vazia se não conseguiu embedding

    print(f"INFO: Buscando top_{top_k} chunks relevantes no Pinecone...")
    try:
        results = pinecone_index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True # ESSENCIAL para recuperar o texto original
        )
        # Extrai apenas o texto dos metadados
        relevant_texts = [
            match['metadata']['text']
            for match in results.get('matches', []) # Usa .get para evitar erro se 'matches' não existir
            if 'metadata' in match and 'text' in match['metadata']
        ]
        print(f"INFO: Encontrados {len(relevant_texts)} chunks relevantes.")
        return relevant_texts
    except Exception as e:
        st.error(f"Erro ao realizar busca no Pinecone: {e}")
        print(f"ERRO: Falha em find_relevant_chunks_pinecone query: {e}")
        return [] # Retorna lista vazia em caso de erro na busca

def generate_response_with_rag(system_message, user_instruction, context_document_text, pinecone_index, client_openai):
    """Função principal que orquestra o RAG: busca contexto e gera resposta."""
    if client_openai is None or pinecone_index is None:
         st.error("Erro: Clientes OpenAI ou Pinecone não inicializados corretamente.")
         return "Desculpe, ocorreu um erro interno. Não foi possível conectar aos serviços necessários."

    # 1. Preparar a query para busca vetorial
    # Combina a instrução do usuário com o início do documento (se houver) para dar mais contexto à busca
    query_for_retrieval = user_instruction
    if context_document_text:
         query_for_retrieval += "\n\n--- Início do Documento Fornecido ---\n" + context_document_text[:1000] + "\n--- Fim do Início do Documento ---"

    # 2. Buscar chunks (contexto) relevantes no Pinecone
    with st.spinner("Consultando base de conhecimento..."):
        retrieved_chunks = find_relevant_chunks_pinecone(query_for_retrieval, pinecone_index, client_openai, top_k=5) # Busca 5 chunks

    # 3. Montar a string de contexto para o prompt do LLM
    if retrieved_chunks:
        context_string = "---\nContexto Recuperado da Base de Conhecimento Jurídico:\n---\n"
        for i, chunk in enumerate(retrieved_chunks):
            context_string += f"Contexto {i+1}:\n{chunk}\n\n" # Adiciona cada chunk recuperado
        context_string += "---\nFim do Contexto Recuperado\n---"
        print("INFO: Contexto formatado para enviar ao LLM.")
    else:
        context_string = "\n(Nenhum contexto específico foi recuperado da base de conhecimento para esta consulta)"
        st.warning("Não foram encontradas informações muito relevantes na base de conhecimento para esta consulta específica.")
        print("AVISO: Nenhum contexto relevante recuperado.")

    # 4. Montar o prompt final para o LLM (modelo de GERAÇÃO)
    # Combina: Instrução do Sistema + Contexto Recuperado + Instrução Original + Documento Completo (opcional)
    final_user_message = (
        f"{context_string}\n\n" # Adiciona o contexto recuperado (ou a mensagem de nenhum contexto)
        f"Considerando o CONTEXTO acima e, se aplicável, o DOCUMENTO COMPLETO fornecido abaixo, "
        f"siga EXATAMENTE a seguinte instrução:\n\n"
        f"Instrução do Usuário: '{user_instruction}'\n\n"
        f"DOCUMENTO COMPLETO (apenas para referência geral, use o CONTEXTO para detalhes específicos):\n"
        f"{context_document_text if context_document_text else 'Nenhum documento completo foi fornecido.'}"
    )

    # 5. Chamar o LLM de GERAÇÃO do Azure com o prompt aumentado
    print(f"INFO: Chamando LLM ({AZURE_OPENAI_DEPLOYMENT_LLM}) para gerar resposta...")
    with st.spinner("Gerando resposta com base no contexto..."):
        try:
            response = client_openai.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT_LLM, # Usa o deployment do LLM de GERAÇÃO
                messages=[
                    {"role": "system", "content": system_message}, # A instrução geral de como o LLM deve se comportar
                    {"role": "user", "content": final_user_message} # O prompt combinado com contexto e instrução
                ],
                temperature=0.3, # Um valor baixo para respostas mais focadas e menos criativas
                max_tokens=4000 # Ajuste conforme necessário (cuidado com o limite do modelo)
            )
            final_response = response.choices[0].message.content
            print("INFO: Resposta do LLM recebida.")
            return final_response
        except Exception as e:
            st.error(f"Erro ao chamar o LLM do Azure ({AZURE_OPENAI_DEPLOYMENT_LLM}): {e}")
            print(f"ERRO: Falha na chamada a client_openai.chat.completions.create: {e}")
            # Tenta dar uma mensagem de erro mais útil
            if "prompt has resulted in exclusion" in str(e):
                return "Desculpe, a sua solicitação não pôde ser processada devido aos filtros de conteúdo."
            elif "maximum context length" in str(e):
                 return "Desculpe, a combinação da sua instrução e do contexto recuperado excedeu o limite de tamanho do modelo. Tente ser mais específico."
            else:
                return "Ocorreu um erro inesperado ao tentar gerar a resposta do modelo de linguagem."

# --- Fim do arquivo rag_utils.py ---