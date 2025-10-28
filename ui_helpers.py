import base64
import os
from PIL import Image
import streamlit as st

def resource_path(filename: str) -> str:
    """
    Retorna o caminho absoluto para um recurso que está no mesmo diretório do arquivo.
    Útil para Azure/ambientes onde o cwd pode variar.
    """
    base_dir = os.path.dirname(__file__)
    return os.path.join(base_dir, filename)

def set_background_png(png_filename: str):
    """
    Define o background da aplicação Streamlit usando um PNG codificado em base64.
    png_filename pode ser um caminho relativo (ex: 'background.png') ou absoluto.
    """
    try:
        path = png_filename
        if not os.path.isabs(path):
            path = resource_path(path)
        if not os.path.exists(path):
            st.warning(f"Background não encontrado: {path}")
            return

        with open(path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode()
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-image: url("data:image/png;base64,{encoded}");
                background-size: cover;
                background-repeat: no-repeat;
                background-attachment: fixed;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.error(f"Erro ao aplicar background: {e}")

def show_logo(logo_filename: str, width: int = 120, use_caption: bool = False):
    """
    Exibe a logo (Image) a partir de um arquivo.
    """
    try:
        path = logo_filename
        if not os.path.isabs(path):
            path = resource_path(path)
        if not os.path.exists(path):
            st.warning(f"Logo não encontrada: {path}")
            return
        img = Image.open(path)
        st.image(img, width=width, use_column_width=False, caption=logo_filename if use_caption else None)
    except Exception as e:
        st.error(f"Erro ao mostrar logo: {e}")

def inject_login_css():
    """
    Injeta CSS para centralizar o conteúdo e estilizar a caixa de login.
    Chame esta função antes de renderizar o formulário de login.
    """
    css = """
    <style>
    /* Container centralizado */
    .centered-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 100vh;
        color: #E3E6F3;
    }

    /* Caixa de login */
    .login-box {
        background: rgba(34, 40, 49, 0.97);
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 2px 16px rgba(0,0,0,0.32);
        width: 400px;
        margin-top: 16px;
    }

    /* Linha de botões */
    .button-row {
        display: flex;
        justify-content: space-between;
        gap: 24px;
        margin-top: 24px;
        width: 400px;
    }

    /* Melhora visual de inputs (opcional) */
    .stTextInput > div > div > input {
        background-color: rgba(255, 255, 255, 0.02);
        color: #E3E6F3;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
