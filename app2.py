import streamlit as st
import fitz  # PyMuPDF
import docx
from io import BytesIO
from openai import AzureOpenAI
from PIL import Image
import os
  


# Configurações do Azure OpenAI
AZURE_OPENAI_ENDPOINT = 'https://lexautomate.openai.azure.com/'  # seu endpoint
AZURE_OPENAI_API_KEY = '6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA'  # coloque aqui sua chave
AZURE_OPENAI_DEPLOYMENT = 'lexautomate_agent'  # exemplo: agentejuridico-gpt4o
AZURE_API_VERSION = '2024-02-15-preview'

client = AzureOpenAI(
    api_version=AZURE_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
)

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
    system_message = "Você é um advogado experiente, especialista na elaboração de petições judiciais. Com base no documento fornecido e na instrução do usuário, elabore uma petição bem estruturada, utilizando linguagem jurídica clara e objetiva. Siga as normas formais de petição, como preâmbulo, fatos, fundamentos jurídicos, pedidos e local/data. Caso o documento não seja necessário, utilize somente as instruções."
    user_message = f"Documento:\n{contract_text}\n\nInstrução do usuário: {user_instruction if user_instruction else 'Com base no documento fornecido e na instrução do usuário, elabore uma petição bem estruturada, utilizando linguagem jurídica clara e objetiva. Siga as normas formais de petição, como preâmbulo, fatos, fundamentos jurídicos, pedidos e local/data. Caso o documento não seja necessário, utilize somente as instruções.'}"

    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        model=AZURE_OPENAI_DEPLOYMENT,
        temperature=0.2,
        max_tokens=3000
    )
    return response.choices[0].message.content

# App Streamlit
def main():
    
    st.title("Geração de Petições Judiciais")
    st.write("Envie seu documento (PDF ou DOCX) e solicite a petição que deseja gerar!")

    uploaded_file = st.file_uploader("Faça upload do documento", type=["pdf", "docx"])
    user_instruction = st.text_area(
        "Qual petição deseja gerar? (Exemplo: 'Com base na petição inicial anexada, redija uma contestação que contenha os seguintes campos:')",
        placeholder="Especifique de forma clara e precisa qual modalidade de petição deseja gerar."
    )

    if uploaded_file is not None:
        with st.spinner('🔍 Gerando petição...'):
            if uploaded_file.name.endswith(".pdf"):
                contract_text = extract_text_from_pdf(uploaded_file.read())
            elif uploaded_file.name.endswith(".docx"):
                contract_text = extract_text_from_docx(uploaded_file.read())
            else:
                st.error("❌ Formato não suportado. Envie apenas PDF ou DOCX.")
                return

        if not contract_text.strip():
            st.error("❌ Não foi possível gerar a petição.")
            return

        if st.button("Gerar Petição"):
            with st.spinner('💬 Gerando peça jurídica, aguarde...'):
                try:
                    resumo = summarize_contract(contract_text, user_instruction)
                    st.success("✅ Geração de documento concluída!")
                    st.markdown(resumo)
                except Exception as e:
                    st.error(f"Erro ao gerar peça judicial: {e}")



if __name__ == "__main__":
    main()
