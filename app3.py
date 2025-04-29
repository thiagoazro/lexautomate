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

def summarize_contract(contract_text, user_instruction, area_direito):
    system_message = f"Você é um especialista em Direito na área relativa a cláusula contratual especificada, com vasta experiência em revisão contratual.Analise a cláusula abaixo conforme a legislação vigente brasileira e a jurisprudência predominante. Diga se está correta, se contém ilegalidades, abusividades ou omissões, e fundamente sua resposta. Caso o usuário não especifique a cláusula, infomre no output que a cláusula não foi especificada."
    user_message = f"Ára do direito: {area_direito}\n\nDocumento:\n{contract_text}\n\nInstrução do usuário: {user_instruction if user_instruction else 'Com base no contrato fornecido e na cláusula especificada pelo usuário, analise a validade jurídica da cláusula de acordo com o ordenamento jurídico brasileiro, atentando-se para a área do direito  da cláusula, e a jurisprudência dominante. Caso o usuário não forneça cláusula, responda que a cláusula não foi especificada.'}"


    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        model=AZURE_OPENAI_DEPLOYMENT,
        temperature=0.2,
        max_tokens=3000
    )
    return response.choices[0].message.content

# App Streamlit
def main():
    
    st.title("Validação de Cláusulas Contratuais")
    st.write("Envie seu contrato (PDF ou DOCX) e receba análise da cláusula contratual específica!")

    uploaded_file = st.file_uploader("Faça upload do contrato", type=["pdf", "docx"])
    area_direito = st.selectbox("Área do Direito", ["Civil", "Trabalhista", "Previdenciário", "Tributário", "Família", "Societário"])
    user_instruction = st.text_area(
        "Especifique qual cláusula pretende validar. (Exemplo: 'Verifique se a cláusula de exclusuvidade respeita o direito civil brasileiro.')",
        placeholder="Especifique obrigatoriamente a cláusula do contrato a ser analisada ou cole a cláusula neste campo."
    )
 
     
    if uploaded_file is not None:
        with st.spinner('🔍 Analisando cláusula do contrato...'):
            if uploaded_file.name.endswith(".pdf"):
                contract_text = extract_text_from_pdf(uploaded_file.read())
            elif uploaded_file.name.endswith(".docx"):
                contract_text = extract_text_from_docx(uploaded_file.read())
            else:
                st.error("❌ Formato não suportado. Envie apenas PDF ou DOCX.")
                return

        if not contract_text.strip():
            st.error("❌ Não foi possível encontrat o texto do contrato enviado.")
            return

               
        if st.button("Analisar Cláusula"):
            
            with st.spinner('💬 Analisando cláusula contratual, aguarde...'):
                try:
                    resumo = summarize_contract(contract_text, user_instruction, area_direito)
                    st.success("✅ Análise concluída!")
                    st.markdown(resumo)
                except Exception as e:
                    st.error(f"Erro ao gerar análise: {e}")

   
if __name__ == "__main__":
    main()
