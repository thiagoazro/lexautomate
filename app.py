# app.py (Modificado)

import streamlit as st
import fitz  # PyMuPDF
import docx
from io import BytesIO
# Removido: from openai import AzureOpenAI
# Removido: from PIL import Image
import os
import rag_utils # <-- 1. Importar rag_utils

# Removidas: Configurações do Azure OpenAI que estavam aqui
# Removida: Inicialização do client = AzureOpenAI(...) que estava aqui

# Funções para extrair texto (MANTIDAS - ou podem ir para um utils geral)
def extract_text_from_pdf(file_bytes):
    # ... (código existente sem mudanças) ...
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text("text")
        return text.strip()
    except Exception as e:
        st.error(f"Erro ao ler PDF: {e}") # Usar st.error é melhor aqui
        return "" # Retornar string vazia em caso de erro

def extract_text_from_docx(file_bytes):
    # ... (código existente sem mudanças) ...
    try:
        doc = docx.Document(BytesIO(file_bytes))
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip() != ""]).strip()
    except Exception as e:
        st.error(f"Erro ao ler DOCX: {e}") # Usar st.error é melhor aqui
        return "" # Retornar string vazia em caso de erro

# Removida: Função summarize_contract antiga (será substituída pela chamada RAG)

# --- App Streamlit Modificado ---
def main():
    st.title("Resumo automático de Contratos (com RAG)")
    st.write("Envie seu contrato (PDF ou DOCX) e receba um resumo jurídico automático baseado em nossa base de conhecimento!")

    # --- 3. Inicializar Clientes via rag_utils ---
    pinecone_index = rag_utils.get_pinecone_index()
    client_openai = rag_utils.get_openai_client()

    # Verifica se as conexões falharam
    if pinecone_index is None or client_openai is None:
        # Mensagem de erro já é exibida pelas funções get_*
        st.warning("Não foi possível conectar aos serviços. Funcionalidade RAG desabilitada.")
        # Poderia optar por desabilitar o botão ou st.stop()
        # st.stop() # Descomente se quiser parar a execução aqui

    # --- Interface do Usuário (sem mudanças significativas) ---
    uploaded_file = st.file_uploader("Faça upload do contrato", type=["pdf", "docx"])
    user_instruction_specific = st.text_area(
        "Deseja direcionar a análise? (Opcional. Deixe em branco para resumo padrão)",
        placeholder="Ex: 'Resuma apenas as cláusulas de pagamento e multa.' ou 'Identifique as partes e o objeto principal.'"
    )

    contract_text = "" # Inicializa

    if uploaded_file is not None:
        with st.spinner('🔍 Extraindo texto do contrato...'):
            file_bytes = uploaded_file.read() # Ler uma vez
            if uploaded_file.name.endswith(".pdf"):
                contract_text = extract_text_from_pdf(file_bytes)
            elif uploaded_file.name.endswith(".docx"):
                contract_text = extract_text_from_docx(file_bytes)
            else:
                st.error("❌ Formato não suportado. Envie apenas PDF ou DOCX.")
                st.stop()

        if not contract_text:
            st.warning("⚠️ Não foi possível extrair texto do contrato ou o arquivo está vazio.")
        else:
             st.info(f"Texto extraído de '{uploaded_file.name}'. Pronto para resumir.")

    if st.button("Resumir Contrato com RAG"):
        if not contract_text:
            st.error("❌ Por favor, faça upload de um contrato para resumir.")
            st.stop()
        if pinecone_index is None or client_openai is None:
             st.error("❌ Serviços RAG indisponíveis. Não é possível resumir.")
             st.stop()

        # --- 4. Definir system_message específico para esta tarefa ---
        system_message_resumo = """Você é um assistente jurídico altamente qualificado, especialista em análise e resumo de contratos.
Seu objetivo é extrair as informações essenciais do contrato fornecido, utilizando o CONTEXTO recuperado da base de conhecimento para complementar ou validar informações quando relevante.
Se o usuário der uma instrução específica, foque nela. Caso contrário, forneça um resumo padrão incluindo:
- Partes Contratantes (nomes e identificação)
- Objeto Principal do Contrato
- Principais Obrigações de cada parte
- Prazos relevantes (vigência, pagamentos, entregas)
- Preço e Forma de Pagamento
- Multas e Penalidades principais
- Cláusulas de Rescisão/Extinção
- Foro de Eleição
Seja claro, conciso e use linguagem jurídica apropriada, mas acessível. Baseie-se primariamente no documento fornecido, usando o contexto recuperado como apoio."""

        # --- Define a instrução do usuário (padrão ou específica) ---
        user_instruction_final = user_instruction_specific if user_instruction_specific else "Faça um resumo jurídico padrão do contrato."

        # --- 5. Substituir a chamada antiga pela chamada RAG ---
        with st.spinner('💬 Consultando base de conhecimento e gerando resumo...'):
            # --- 6. Passar os Argumentos Corretos ---
            resultado_rag = rag_utils.generate_response_with_rag(
                system_message=system_message_resumo,
                user_instruction=user_instruction_final,
                context_document_text=contract_text, # Texto extraído do contrato
                pinecone_index=pinecone_index,       # Objeto do índice Pinecone
                client_openai=client_openai          # Objeto do cliente Azure OpenAI
            )
            st.success("✅ Resumo concluído!")
            st.markdown(resultado_rag)

if __name__ == "__main__":
    main()
