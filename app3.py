# app3.py (Modificado para RAG)

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
    st.title("Análise de Cláusulas Contratuais (com RAG)")
    st.write("Envie o contrato (PDF ou DOCX), selecione a área do direito e especifique a cláusula ou o ponto que deseja analisar!")

    # --- 3. Inicializar Clientes via rag_utils ---
    pinecone_index = rag_utils.get_pinecone_index()
    client_openai = rag_utils.get_openai_client()

    # Verifica se as conexões falharam
    if pinecone_index is None or client_openai is None:
        st.error("Falha ao inicializar os serviços necessários (Pinecone/OpenAI). Verifique as configurações e os logs no terminal.")
        st.stop()

    # --- Interface do Usuário ---
    uploaded_file = st.file_uploader("Faça upload do contrato", type=["pdf", "docx"])
    area_direito = st.selectbox(
        "Área do Direito relacionada à Cláusula",
        ["Civil", "Trabalhista", "Consumidor", "Empresarial/Societário", "Tributário", "Administrativo", "Imobiliário", "Outra"]
    )
    user_instruction = st.text_area(
        "Especifique a Cláusula ou Ponto a Validar/Analisar:",
        placeholder="Ex: 'Analise a validade da cláusula de não concorrência (Cláusula X) conforme a legislação trabalhista.' ou 'Verifique se a multa por atraso na Cláusula Y está de acordo com o Código Civil e o CDC.' ou 'Cole aqui o texto exato da cláusula que deseja analisar.'",
        height=150
    )

    # --- Processamento do Arquivo ---
    contract_text = "" # Inicializa
    if uploaded_file is not None:
        with st.spinner('🔍 Extraindo texto do contrato...'):
            file_bytes = uploaded_file.read()
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
            st.info(f"Texto extraído de '{uploaded_file.name}'. Pronto para analisar.")

    # --- Análise da Cláusula ---
    if st.button("Analisar Cláusula com RAG"):
        if not uploaded_file:
             st.error("❌ Por favor, faça upload do contrato que contém a cláusula.")
             st.stop()
        if not contract_text: # Verifica se a extração deu certo
             st.error("❌ Não foi possível ler o contrato. Tente reenviar o arquivo.")
             st.stop()
        if not user_instruction:
            st.error("❌ Por favor, especifique a cláusula ou o ponto a ser analisado na caixa de texto.")
            st.stop()

        # --- 4. Definir system_message específico para esta tarefa ---
        system_message_clausula = f"""Você é um(a) advogado(a) consultor(a), especialista em análise contratual e gestão de riscos, com foco em Direito Brasileiro na área de {area_direito}.
Sua tarefa é analisar especificamente a cláusula ou o ponto do contrato indicado pelo usuário, à luz da legislação e jurisprudência predominante no Brasil.
Utilize o CONTEXTO recuperado da base de conhecimento jurídica para embasar sua análise sobre validade, legalidade, abusividade, omissões ou riscos associados à cláusula/ponto em questão.
Seja claro, objetivo e fundamente sua resposta. Indique se a redação está adequada, se há pontos de atenção, riscos ou sugestões de melhoria/adequação legal.
Foque exclusivamente na instrução do usuário sobre qual cláusula/ponto analisar."""

        # --- Combina área do direito com instrução do usuário para mais contexto ---
        user_instruction_final = f"Área do Direito Principal: {area_direito}\n\nInstrução de Análise: {user_instruction}"

        # --- 5. Substituir a chamada antiga pela chamada RAG ---
        with st.spinner('💬 Consultando base de conhecimento e analisando cláusula...'):
            # --- 6. Passar os Argumentos Corretos ---
            resultado_rag = rag_utils.generate_response_with_rag(
                system_message=system_message_clausula,
                user_instruction=user_instruction_final,   # Instrução combinada
                context_document_text=contract_text,      # Texto completo do contrato
                pinecone_index=pinecone_index,            # Objeto do índice Pinecone
                client_openai=client_openai               # Objeto do cliente Azure OpenAI
            )
            st.success("✅ Análise concluída!")
            st.markdown(resultado_rag) # Exibe a análise gerada

if __name__ == "__main__":
    main()
