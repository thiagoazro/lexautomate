# rag_utils.py
import streamlit as st
from pinecone import Pinecone
from openai import AzureOpenAI
import os

# Configs Pinecone
PINECONE_API_KEY = "pcsk_3hauhv_LYhcF6L6vCkkUc5U3WxkBjC2TALRB9GzAkkAN5GihNkJ27XFKxtSgP24NipbtLt" # <-- Sua chave Pinecone API Key
PINECONE_INDEX_NAME = "lexautomate" # <-- O nome do seu índice Pinecone (confirmado na última msg)

# Configs Azure OpenAI (valores dos seus arquivos app*.py e última decisão do modelo)
AZURE_OPENAI_ENDPOINT = 'https://lexautomate.openai.azure.com/' # <-- Seu endpoint Azure (dos seus arquivos)
AZURE_OPENAI_API_KEY = '6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA' # <-- Sua chave Azure API Key (dos seus arquivos - CUIDADO AO EXPOR!)
AZURE_OPENAI_DEPLOYMENT_LLM = 'lexautomate_agent' # <-- Nome da deployment do modelo de GERAÇÃO (dos seus arquivos)

# IMPORTANTE: Substitua a string abaixo pelo nome EXATO da sua implantação do text-embedding-3-large no Azure!
AZURE_OPENAI_DEPLOYMENT_EMBEDDING = 'NOME_DA_SUA_DEPLOYMENT_TEXT_EMBEDDING_3_LARGE' # <--- VOCÊ PRECISA PREENCHER ISTO!

AZURE_API_VERSION = '2024-02-15-preview' # <-- Versão da API Azure (dos seus arquivos)


# Cacheia a conexão com Pinecone para não reconectar a cada interação no Streamlit
@st.cache_resource
def get_pinecone_index():
    print("Inicializando conexão com Pinecone...") # Para debug, ver quando conecta
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        if PINECONE_INDEX_NAME not in pc.list_indexes().names:
             raise ValueError(f"Índice '{PINECONE_INDEX_NAME}' não encontrado.")
        index = pc.Index(PINECONE_INDEX_NAME)
        print("Conexão com Pinecone estabelecida.")
        return index
    except Exception as e:
        st.error(f"Falha ao conectar ao Pinecone: {e}")
        return None

# Cacheia o cliente OpenAI
@st.cache_resource
def get_openai_client():
     # ... (lógica para inicializar seu AzureOpenAI client) ...
     client_openai = AzureOpenAI(...)
     return client_openai

# Função de embedding (pode receber o cliente como argumento)
def get_embedding(text_chunk, client_openai):
    # ... (sua lógica de embedding usando o client_openai) ...
    pass

# Função de busca (recebe o índice como argumento)
def find_relevant_chunks_pinecone(query_text, pinecone_index, client_openai, top_k=5):
    if not query_text or pinecone_index is None or client_openai is None:
        return []
    try:
        query_embedding = get_embedding(query_text, client_openai)
        if query_embedding is None: return []

        results = pinecone_index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True
        )
        relevant_texts = [match['metadata']['text'] for match in results['matches'] if 'metadata' in match and 'text' in match['metadata']]
        return relevant_texts
    except Exception as e:
        st.error(f"Erro na busca Pinecone: {e}")
        return []

# Função RAG genérica
def generate_response_with_rag(system_message, user_instruction, context_document_text, pinecone_index, client_openai):
     # 1. Preparar query para Pinecone
     query_for_retrieval = user_instruction + "\n" + context_document_text[:1000]

     # 2. Buscar chunks relevantes
     retrieved_chunks = find_relevant_chunks_pinecone(query_for_retrieval, pinecone_index, client_openai)
     context_string = "..." # Montar string de contexto

     # 3. Montar prompt final
     final_user_message = "..." # Combinar instrução e contexto

     # 4. Chamar LLM
     response = client_openai.chat.completions.create(
         messages=[{"role": "system", "content": system_message}, {"role": "user", "content": final_user_message}],
         # ... outros parâmetros ...
     )
     return response.choices[0].message.content
