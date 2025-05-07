import streamlit as st
from app import resumo_interface
from app2 import peticao_interface
from app3 import validacao_interface

st.set_page_config(
    page_title="Plataforma Jurídica Inteligente",
    page_icon="https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/lexautomate_icon.png",
    layout="wide"
)

# Logo e título lado a lado
col1, col2 = st.columns([1, 4])
with col1:
    st.image("https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/logo_lexautomate.png", width=250)
with col2:
    st.markdown("""
    ## LexAutomate - Plataforma Jurídica Inteligente  
    ### Resumos, Geração de Peças Jurídicas e Análise de Cláusulas com IA  
    <small>Versão 1.2.0 - HITL e RAG</small>  
    <small>Criado por Thiago Azeredo Rodrigues</small>

    """, unsafe_allow_html=True)

# Abas principais
abas = st.tabs([
    "Resumo de Documento",
    "Geração de Peça Jurídica",
    "Validação de Cláusula",
    "Instruções de Uso"
])

with abas[0]:
    resumo_interface()

with abas[1]:
    peticao_interface()

with abas[2]:
    validacao_interface()

with abas[3]:
    st.header("Instruções de Uso da LexAutomate")

    st.markdown("""
### Como usar cada funcionalidade

**1. Resumo de Documento**
- Envie um arquivo PDF ou DOCX contendo o contrato ou petição.
- A IA irá gerar um resumo jurídico estruturado com base nas cláusulas principais.
- Você pode revisar e editar o texto antes de exportar.

**2. Geração de Peça Jurídica**
- Faça upload de um ou mais documentos com os fatos ou fundamentos.
- Escreva um prompt com instruções específicas (ex: tipo de peça, área do direito, estrutura desejada).
- A IA irá redigir uma peça completa em Markdown formatado.

**3. Validação de Cláusula**
- Envie um contrato e especifique qual cláusula deseja analisar.
- A IA avalia validade, riscos e legalidade com base no contexto jurídico brasileiro.

---

### Dicas para melhorar os resultados:

- Use linguagem clara e objetiva nos prompts.
- Especifique **o tipo de peça** (ex: "petição inicial trabalhista").
- Informe **estado/foro**, **partes envolvidas** e **valores** quando possível.
- Você pode indicar **estrutura da peça** ou **modelo desejado**.

---

### 🧠 Técnicas avançadas de uso com prompts estratégicos

Você pode **refinar seus comandos (prompts)** para guiar a IA na geração de peças mais precisas e contextualizadas. Veja alguns exemplos:

- **Geração específica de peças:**  
  *“Gere uma petição inicial com base no contrato anexo, estruturando os pedidos conforme o descumprimento das obrigações ora listadas.”*

- **Recurso com contra-argumentação:**  
  *“Redija um recurso ordinário com base na petição inicial e na sentença anexas, rebatendo especialmente os fundamentos da improcedência do pedido de equiparação salarial. Utilize como estrutura do documento a ser gerado o modelo de Recurso Ordinário anexado.”*

- **Cláusulas críticas:**  
  *“Analise a cláusula de exclusividade do contrato à luz da jurisprudência atual.”*

- **Validação de cláusulas:**  
  *“Verifique a validade da cláusula de confidencialidade do contrato anexo, considerando a legislação brasileira e jurisprudência atual.”*

- **Análise de riscos:**  
  *“Identifique os riscos associados à cláusula de rescisão unilateral do contrato, considerando a legislação brasileira e jurisprudência atual.”*

- **Contestação processual guiada:**  
  *“Gere uma contestação processual com base na petição inicial e nos documentos anexos, abordando os seguintes pontos: [listar pontos específicos] e as seguintes teses defensivas: [listar as teses mais assertivas para defesa de forma].”*

---

### 📘 Leia mais: guia de prompts jurídicos eficazes

Aprofunde-se nas melhores estratégias lendo o artigo:

**[Engenharia de Prompt e Modelos de Linguagem: Um Aliado para os Profissionais do Direito](https://medium.com/@thiagoazro/engenharia-de-prompt-e-modelos-de-linguagem-um-aliado-para-os-profissionais-do-direito-af86658e470b)**
    """)

# Rodapé
st.markdown("""
<hr style='margin-top: 3rem;'>
<div style='text-align: center; font-size: 0.8rem; color: gray;'>
    © 2025 LexAutomate. Todos os direitos reservados.
</div>
""", unsafe_allow_html=True)
