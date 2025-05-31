# chroma_utils.py (corrigido)
import os
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
# Importe AzureOpenAIEmbeddings de langchain_openai ou langchain_community.embeddings dependendo da sua versão
# Vou usar langchain_openai que é o mais recente para novos desenvolvimentos com Azure
from langchain_openai import AzureOpenAIEmbeddings
import traceback

# --- CREDENCIAIS E CONSTANTES ---
AZURE_OPENAI_ENDPOINT = 'https://lexautomate.openai.azure.com/'
AZURE_OPENAI_API_KEY = '6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA'
AZURE_OPENAI_DEPLOYMENT_LLM = 'lexautomate'
AZURE_OPENAI_DEPLOYMENT_EMBEDDING = 'text-embedding-3-large'
AZURE_API_VERSION = '2025-01-01-preview'

# URL de teste (movida para dentro do if __name__ para clareza)

def _criar_retriever_chroma_de_url(url: str, top_k_retriever: int = 3):
    """
    Cria um retriever Chroma baseado no conteúdo de uma URL, usando embeddings da Azure.
    Retorna o retriever.
    """
    try:
        print(f"INFO CHROMA_UTILS: Carregando URL para Chroma: {url}")
        # Ajuste para WebBaseLoader: pode ser necessário instalar 'beautifulsoup4' e 'html2text'
        loader = WebBaseLoader(url, continue_on_failure=True, raise_for_status=False)
        docs = loader.load()

        if not docs:
            print(f"AVISO CHROMA_UTILS: Nenhum documento carregado da URL: {url}")
            return None

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        chunks = splitter.split_documents(docs)

        if not chunks:
            print(f"AVISO CHROMA_UTILS: Nenhum chunk gerado da URL: {url}")
            return None

        if not all([AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT_EMBEDDING, AZURE_API_VERSION]):
            print("ERRO CHROMA_UTILS: Credenciais/configurações do Azure OpenAI para embeddings não estão completas. Verifique as variáveis de ambiente.")
            return None

        # CORREÇÃO NA INSTANCIAÇÃO DE AzureOpenAIEmbeddings
        embeddings = AzureOpenAIEmbeddings(
            azure_deployment=AZURE_OPENAI_DEPLOYMENT_EMBEDDING,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            openai_api_key=AZURE_OPENAI_API_KEY,       # Nome corrigido do parâmetro
            openai_api_version=AZURE_API_VERSION,   # Nome corrigido do parâmetro
            chunk_size=1000                               # Parâmetro adicionado (ex: 1000 ou 16, conforme documentação/necessidade)
                                                          # A validação interna da Langchain limitará a 2048 ou outro valor.
        )

        # Cria o vectorstore em memória
        vectorstore = Chroma.from_documents(documents=chunks, embedding=embeddings)
        print(f"INFO CHROMA_UTILS: Vectorstore Chroma criado para {url} com {len(chunks)} chunks.")
        return vectorstore.as_retriever(search_kwargs={'k': top_k_retriever})
    except Exception as e:
        print(f"ERRO CHROMA_UTILS (_criar_retriever_chroma_de_url): Falha ao criar retriever Chroma para URL {url}: {e}")
        traceback.print_exc()
        return None

def formatar_contexto_chroma_para_llm(documentos_chroma: list, url_fonte: str) -> str:
    """
    Formata os documentos recuperados pelo Chroma para inclusão no prompt do LLM.
    """
    if not documentos_chroma:
        return f"\n\n--- CONTEXTO DA URL ({url_fonte}) ---\nNenhum conteúdo relevante encontrado nesta URL para a consulta.\n--- FIM DO CONTEXTO DA URL ---\n" # Ajuste na mensagem

    contexto_formatado = f"\n\n--- INÍCIO DO CONTEXTO DA URL ({url_fonte}) ---\n" # Ajuste na mensagem
    contexto_formatado += "Conteúdo extraído da URL para consulta:\n"
    for i, doc in enumerate(documentos_chroma):
        conteudo = doc.page_content
        metadata_source = doc.metadata.get('source', url_fonte)
        contexto_formatado += f"\n[TRECHO {i+1} DA URL: {metadata_source}]\n"
        contexto_formatado += f"Conteúdo do Trecho: {conteudo}\n"
    contexto_formatado += f"--- FIM DO CONTEXTO DA URL ({url_fonte}) ---\n" # Ajuste na mensagem
    return contexto_formatado

def obter_contexto_relevante_de_url(url_referencia: str, pergunta_usuario: str, top_k_chunks: int = 3) -> str: # Nome do parâmetro url alterado para clareza
    """
    Obtém chunks de contexto relevantes de uma URL com base na pergunta do usuário.
    """
    if not url_referencia:
        return ""

    retriever = _criar_retriever_chroma_de_url(url_referencia, top_k_retriever=top_k_chunks)
    if not retriever:
        return f"\n\n--- CONTEXTO DA URL ({url_referencia}) ---\nFalha ao carregar ou processar o conteúdo da URL.\n--- FIM DO CONTEXTO DA URL ---\n" # Ajuste na mensagem

    try:
        documentos_relevantes = retriever.invoke(pergunta_usuario)
        contexto_formatado = formatar_contexto_chroma_para_llm(documentos_relevantes, url_referencia)
        return contexto_formatado
    except Exception as e:
        print(f"ERRO CHROMA_UTILS (obter_contexto_relevante_de_url): Falha ao obter contexto da URL {url_referencia}: {e}")
        traceback.print_exc()
        return f"\n\n--- CONTEXTO DA URL ({url_referencia}) ---\nErro ao buscar informações na URL: {str(e)}\n--- FIM DO CONTEXTO DA URL ---\n" # Ajuste na mensagem

# Exemplo de uso (para teste)
if __name__ == '__main__':
    # Certifique-se de que as variáveis de ambiente AZURE_OPENAI_API_KEY, etc., estão configuradas
    if not AZURE_OPENAI_API_KEY: # Verifica se a chave foi carregada do ambiente
        print("AVISO: Configure a variável de ambiente AZURE_OPENAI_API_KEY e outras credenciais/configurações do Azure.")
    else:
        # Defina uma URL de teste válida aqui
        # A variável 'teste_url' definida no topo do script original era uma string, não um dicionário.
        url_para_teste = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp101.htm" # Exemplo: LRF
        # url_para_teste = "https://jurisprudencia.stf.jus.br/pages/search/sjur488739/false" # Sua URL de teste anterior
        pergunta_teste = "Quais são os limites para despesa total com pessoal?" # Pergunta relacionada à LRF

        print(f"Testando busca na URL: {url_para_teste}")
        print(f"Pergunta: {pergunta_teste}\n")

        contexto = obter_contexto_relevante_de_url(url_para_teste, pergunta_teste, top_k_chunks=2)
        print("\n--- CONTEXTO OBTIDO PARA TESTE ---\n")
        print(contexto)
        print("\n--- FIM DO TESTE ---")