
# LexAutomate - Plataforma de Análise Jurídica com IA #

Este projeto implementa uma plataforma jurídica baseada em Inteligência Artificial, composta por três módulos:

- **Resumo de Contratos**: Extrai e resume informações principais de documentos jurídicos (contratos em PDF ou DOCX).
- **Geração de Petições**: Gera petições jurídicas automáticas a partir de instruções fornecidas pelo usuário.
- **Validação de Cláusulas**: Analisa e valida cláusulas contratuais com base nas áreas de Direito selecionadas (Civil, Penal, Trabalhista, Previdenciário ou Tributário).
- ** Chatbot Jurídico**: Consultor jurídico que interage com o usuário para responder dúvidas jurídicas.

O sistema é hospedado na **Azure** e utiliza **Streamlit** como framework web, integrado com o serviço **Azure OpenAI**.

---

## Tecnologias Utilizadas ##

- **Python 3.12**
- **Streamlit** (Frontend Web)
- **Azure OpenAI Service** (Modelo GPT-4o)
- **Azure App Service** (Hospedagem)
- **GitHub Actions** (Deploy contínuo)
- **Bibliotecas auxiliares**:
  - `PyMuPDF`
  - `python-docx`
  - `Pillow`
  - `openai`
  - `joblit`
  - `nltk`

---
Utiliza RAG, busca semantica, e azure language. Jurisprudencia e modelo de peticoes incluidos. Google Search API incluído.

## Estrutura do Projeto

```
/
├── app.py        # Módulo 1: Resumo de Contratos
├── app2.py       # Módulo 2: Geração de Petições
├── app3.py       # Módulo 3: Validação de Cláusulas
├── app4.py       # Módulo 4: Consultor Jurídico
├── main.py       # Arquivo principal para navegação entre os módulos
├── requirements.txt
├── logo_lexautomate.png
├── lexautomate_icon.png
```

---

## Como Executar Localmente

1. Clone o repositório:

```bash
git clone https://github.com/thiagoazro/lexautomate.git
cd lexautomate
```

2. Instale as dependências:

```bash
pip install -r requirements.txt
```

3. Rode o projeto:

```bash
streamlit run main.py
```

---

## Como Funciona o Deploy

- O projeto utiliza **GitHub Actions** para build automático.
- A cada `git push` no ramo `main`, o workflow é disparado e faz o deploy diretamente no **Azure App Service**.

---

## Sobre o Projeto

**LexAutomate** é uma plataforma desenvolvida para otimizar operações jurídicas utilizando IA, oferecendo análises precisas de contratos, geração de peças jurídicas e validações de cláusulas conforme a legislação brasileira.

---

## Contato

**Thiago Azeredo Rodrigues**  
Fundador da LexAutomate  
[Adicionar LinkedIn ou E-mail profissional]
