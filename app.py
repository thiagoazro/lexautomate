import streamlit as st
import fitz  # PyMuPDF
import docx
from io import BytesIO
from openai import AzureOpenAI
from PIL import Image
import os

# ... (Azure OpenAI configuration)

def extract_text_from_file(file_bytes):
    if file_bytes.name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    elif file_bytes.name.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    else:
        return f"Unsupported format: {file_bytes.name}"

def summarize_contract(contract_text, user_instruction):
    # ... (summarization logic)

def main():
    st.title("Resumo automático de Contratos")
    st.write("Envie seu contrato (PDF ou DOCX) e receba um resumo jurídico automático!")
    uploaded_files = st.file_uploader("Faça upload do contrato", type=["pdf", "docx"], accept_multiple_files=True)

    user_instruction = st.text_area(
        "Deseja direcionar a análise? (Exemplo: 'Resuma apenas as obrigações das partes.')",
        placeholder="Deixe em branco para resumo padrão (nome das partes, objetivo principal do contrato, obrigações, prazos, preço e forma de pagamento, vigência, multas e penalidades, rescisão e extinção, confidencialidade, foro de eleição)."
    )

    if uploaded_files is not None:
        with st.spinner('🔍 Extraindo texto do contrato...'):
            for uploaded_file in uploaded_files:
                contract_text = extract_text_from_file(uploaded_file)
                if contract_text.strip():
                    if st.button("Resumir Contrato"):
                        with st.spinner('💬 Resumindo contrato, aguarde...'):
                            try:
                                resumo = summarize_contract(contract_text, user_instruction)
                                st.success("✅ Resumo concluída!")
                                st.markdown(resumo)
                            except Exception as e:
                                st.error(f"Erro ao gerar resumo: {e}")

if __name__ == "__main__":
    main()
