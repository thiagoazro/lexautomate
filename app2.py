# app2.py (Modificado para RAG)

import streamlit as st
import fitz  # PyMuPDF
import docx
from io import BytesIO
# Removido: from openai import AzureOpenAI
# Removido: from PIL import Image - Não parece ser usada aqui
import os
import rag_utils # <-- 1. Importar rag_utils

# Removidas: Configurações do Azure OpenAI que estavam aqui
# Removida: Inicialização do client = AzureOpenAI(...) que estava aqui

# Funções para extrair texto (MANTIDAS)
def extract_text_from_pdf(file_bytes):
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text("text")
        return text.strip()
    except Exception as e:
        st.error(f"Erro ao ler PDF: {e}")
        return ""

def extract_text_from_docx(file_bytes):
    try:
        doc = docx.Document(BytesIO(file_bytes))
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip() != ""]).strip()
    except Exception as e:
        st.error(f"Erro ao ler DOCX: {e}")
        return ""

# Removida: Função summarize_contract antiga

# --- App Streamlit Modificado ---
def main():
    st.title("Geração de Petições Judiciais (com RAG)")
    st.write("Envie documentos de referência (PDF ou DOCX) e descreva a petição que deseja gerar!")

    # --- 3. Inicializar Clientes via rag_utils ---
    pinecone_index = rag_utils.get_pinecone_index()
    client_openai = rag_utils.get_openai_client()

    # Verifica se as conexões falharam
    if pinecone_index is None or client_openai is None:
        st.error("Falha ao inicializar os serviços necessários (Pinecone/OpenAI). Verifique as configurações e os logs no terminal.")
        st.stop()

    # --- Interface do Usuário ---
    # Aceita múltiplos arquivos
    uploaded_files = st.file_uploader(
        "Faça upload dos documentos de referência (Opcional)",
        type=["pdf", "docx"],
        accept_multiple_files=True
    )
    user_instruction = st.text_area(
        "Qual petição deseja gerar e quais informações devem constar?",
        placeholder="Ex: 'Gere uma Petição Inicial de Ação de Alimentos com base nos fatos X, Y, Z, com pedido de alimentos provisórios.' ou 'Com base na sentença anexada, elabore um Recurso de Apelação sobre os pontos A e B.'",
        height=150
    )

    # --- Processamento dos Arquivos ---
    all_docs_text = "" # Inicializa variável para concatenar texto dos documentos
    if uploaded_files:
        with st.spinner(f'🔍 Extraindo texto de {len(uploaded_files)} documento(s)...'):
            temp_texts = []
            for i, uploaded_file in enumerate(uploaded_files):
                file_bytes = uploaded_file.read()
                text = ""
                if uploaded_file.name.endswith(".pdf"):
                    text = extract_text_from_pdf(file_bytes)
                elif uploaded_file.name.endswith(".docx"):
                    text = extract_text_from_docx(file_bytes)
                else:
                    st.error(f"❌ Formato não suportado: {uploaded_file.name}")
                    # Poderia parar (st.stop()) ou apenas pular o arquivo

                if text:
                    temp_texts.append(f"\n--- INÍCIO DOCUMENTO {i+1}: {uploaded_file.name} ---\n{text}\n--- FIM DOCUMENTO {i+1} ---\n")
                else:
                     st.warning(f"⚠️ Não foi possível extrair texto de '{uploaded_file.name}' ou está vazio.")

            all_docs_text = "\n".join(temp_texts) # Junta o texto de todos os documentos

        if not all_docs_text:
            st.error("❌ Não foi possível extrair texto de nenhum dos documentos enviados.")
        else:
            st.info(f"Texto extraído de {len(uploaded_files)} documento(s). Pronto para gerar petição.")


    # --- Geração da Petição ---
    if st.button("Gerar Petição com RAG"):
        if not user_instruction:
            st.warning("⚠️ Por favor, descreva a petição que deseja gerar.")
            st.stop()
        # Não paramos mais se não houver documentos, pois a instrução pode ser suficiente

        # --- 4. Definir system_message específico para esta tarefa ---
        system_message_peticao = """Você é um advogado(a) altamente experiente, especialista na redação de peças processuais conforme as normas brasileiras.
Sua tarefa é elaborar a petição solicitada pelo usuário, utilizando as informações fornecidas na instrução e nos documentos anexados (se houver).
Use o CONTEXTO recuperado da base de conhecimento jurídica para embasar os fundamentos legais, citar jurisprudência relevante ou complementar informações.
Estruture a peça de forma clara e lógica, seguindo as formalidades exigidas (endereçamento, preâmbulo/qualificação, fatos, fundamentos jurídicos, pedidos, valor da causa, etc.).
Adapte a linguagem ao tipo de peça solicitada. Seja preciso, objetivo e fundamentado."""

        # --- 5. Substituir a chamada antiga pela chamada RAG ---
        with st.spinner('💬 Consultando base de conhecimento e gerando peça jurídica...'):
            # --- 6. Passar os Argumentos Corretos ---
            resultado_rag = rag_utils.generate_response_with_rag(
                system_message=system_message_peticao,
                user_instruction=user_instruction,       # Instrução do usuário sobre a petição
                context_document_text=all_docs_text,    # Texto concatenado dos documentos enviados
                pinecone_index=pinecone_index,          # Objeto do índice Pinecone
                client_openai=client_openai             # Objeto do cliente Azure OpenAI
            )
            st.success("✅ Geração de documento concluída!")
            st.markdown(resultado_rag) # Exibe a petição gerada

if __name__ == "__main__":
    main()
