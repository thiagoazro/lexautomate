import streamlit as st
from PIL import Image
import app   # Importa a análise de contratos
import app2  # Importa a geração de petições
import app3  # Importa a validação de cláusulas
import os

def main():
    # Configurações iniciais da página
    # Carrega o ícone personalizado
    icon_path = "lexautomate_icon.png"
    if os.path.exists(icon_path):
        icon = Image.open(icon_path)
    else:
        icon = "🧠"  # fallback emoji

    # Configura a página
    st.set_page_config(
        page_title="LexAutomate - Legal Technology",
        page_icon=icon,
        layout="centered")

    # Exibe a logo centralizada
    logo_path = "logo_lexautomate.png"
    if os.path.exists(logo_path):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(Image.open(logo_path), width=250)
    else:
        st.warning("Logo da LexAutomate não encontrada.")

    st.title("LexAutomate - Plataforma Jurídica Inteligente")
    st.subheader("Selecione na barra lateral a funcionalidade jurídica desejada:")

    # Menu de navegação lateral
    menu = st.sidebar.selectbox(
        "Escolha a funcionalidade:",
        [
            "Análise e Resumo de Contratos",
            "Criação de Petições",
            "Análise de Cláusulas Contratuais"
        ]
    )

    # Direcionamento conforme opção escolhida
    if menu == "Análise e Resumo de Contratos":
        app.main()  # Chama o app.py

    elif menu == "Criação de Petições":
        app2.main()  # Chama o app2.py

    elif menu == "Análise de Cláusulas Contratuais":
        app3.main()  # Chama o app3.py

    st.markdown("---")
    st.caption("© 2025 LexAutomate - Todos os direitos reservados.")

if __name__ == "__main__":
    main()
