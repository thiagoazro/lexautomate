import streamlit as st
import fitz  # PyMuPDF
import docx
from io import BytesIO
from openai import AzureOpenAI
import os

# Configurações do Azure OpenAI
AZURE_OPENAI_ENDPOINT = 'https://lexautomate.openai.azure.com/'  # Seu endpoint
AZURE_OPENAI_API_KEY = '6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA'  # Sua chave da API
AZURE_OPENAI_DEPLOYMENT = 'lexautomate_agent'  # Nome da sua deployment
AZURE_API_VERSION = '2024-02-15-preview'

try:
    client = AzureOpenAI(
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
    )
except Exception as e:
    st.error(f"Erro ao inicializar o cliente Azure OpenAI: {e}")
    st.stop()

# Funções para extrair texto
def extract_text_from_pdf(file_bytes):
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text("text")
        return text.strip()
    except Exception as e:
        return f"Erro ao ler PDF: {e}"

def extract_text_from_docx(file_bytes):
    try:
        doc = docx.Document(BytesIO(file_bytes))
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip() != ""]).strip()
    except Exception as e:
        return f"Erro ao ler DOCX: {e}"

def summarize_contract(contract_text, user_instruction):
    system_message = "Você é um assistente jurídico especializado em análise de contratos com mais de 10 anos de experiência. Seja objetivo, claro e profissional."
    user_message = f"Contrato:\n{contract_text}\n\nInstrução do usuário: {user_instruction if user_instruction else 'Resuma nome das partes, objetivo principal do contrato, obrigações, prazos, preço e forma de pagamento, vigência, multas e penalidades, rescisão e extinção, confidencialidade, foro de eleição'}"
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            model=AZURE_OPENAI_DEPLOYMENT,
            temperature=0.2,
            max_tokens=3000
        )
        if response.choices and len(response.choices) > 0:
            return response.choices.message.content
        else:
            return "Erro: Resposta da API não continha a mensagem esperada."
    except Exception as api_error:
        return f"Erro ao gerar resumo com a API: {api_error}"

# App Streamlit
def main():
    st.title("Resumo Automático de Contratos")
    st.write("Envie seus contratos (PDF ou DOCX) e receba resumos jurídicos automáticos!")
    uploaded_files = st.file_uploader("Faça upload do(s) contrato(s)", type=["pdf", "docx"], accept_multiple_files=True)
    user_instruction = st.text_area(
        "Deseja direcionar a análise? (Exemplo: 'Resuma apenas as obrigações das partes.')",
        placeholder="Deixe em branco para resumo padrão (nome das partes, objetivo principal do contrato, obrigações, prazos, preço e forma de pagamento, vigência, multas e penalidades, rescisão e extinção, confidencialidade, foro de eleição)."
    )

    if uploaded_files:
        for uploaded_file in uploaded_files:
            with st.spinner(f'🔍 Extraindo texto de {uploaded_file.name}...'):
                file_content = uploaded_file.read()
                if uploaded_file.name.endswith(".pdf"):
                    contract_text = extract_text_from_pdf(file_content)
                elif uploaded_file.name.endswith(".docx"):
                    contract_text = extract_text_from_docx(file_content)
                else:
                    st.error(f"❌ Formato não suportado: {uploaded_file.name}. Envie apenas PDF ou DOCX.")
                    continue

                if not contract_text.strip():
                    st.error(f"❌ Não foi possível extrair o texto do contrato {uploaded_file.name}.")
                    continue

                if st.button(f"Resumir Contrato: {uploaded_file.name}"):
                    with st.spinner(f'💬 Resumindo contrato {uploaded_file.name}, aguarde...'):
                        resumo = summarize_contract(contract_text, user_instruction)
                        if resumo.startswith("Erro"):  # Check for error message
                            st.error(resumo)
                        else:
                            st.success(f"✅ Resumo de {uploaded_file.name} concluído!")
                            st.markdown(resumo)

if __name__ == "__main__":
    main()
