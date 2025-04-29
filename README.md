
# LexAutomate - Inteligência Jurídica Automatizada

O LexAutomate é uma aplicação que utiliza Inteligência Artificial para análise automática de contratos jurídicos, oferecendo resumos estruturados de forma rápida, segura e precisa.  
O projeto foi desenvolvido com Python, Streamlit e Azure OpenAI Service, garantindo alta performance e confiabilidade.

---

## Funcionalidades

- Upload de contratos nos formatos PDF ou DOCX.
- Análise automatizada utilizando modelos de linguagem da Azure.
- Geração de resumos jurídicos estruturados, contendo:
  - Nome das partes
  - Objetivo principal do contrato
  - Obrigações principais
  - Prazo de vigência
  - Cláusulas de multa
  - Cláusulas de confidencialidade
- Direcionamento da análise com perguntas específicas do usuário.

---

## Tecnologias Utilizadas

- Python 3.12
- Streamlit
- Azure OpenAI Service
- GitHub Actions (CI/CD automático)
- Azure App Service (Hospedagem)

---

## Deploy

O projeto está implantado automaticamente no Azure App Service através de pipelines configurados com GitHub Actions.

Acesse a aplicação em produção:  
[https://lexautomate-site-ame2cta6c7dyfyda.brazilsouth-01.azurewebsites.net](https://lexautomate-site-ame2cta6c7dyfyda.brazilsouth-01.azurewebsites.net)

---

## Como Rodar Localmente

Clone o repositório:

```bash
git clone https://github.com/seu-usuario/lexautomate.git
```

Acesse a pasta do projeto:

```bash
cd lexautomate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

Execute a aplicação:

```bash
streamlit run app.py
```

---

## Contato

Desenvolvido por Thiago Azeredo  
Email: thiagoazro@gmail.com  
LinkedIn: [Thiago Azeredo no LinkedIn](https://www.linkedin.com/in/thiagoazro/)

---

© 2025 LexAutomate - Todos os direitos reservados.
