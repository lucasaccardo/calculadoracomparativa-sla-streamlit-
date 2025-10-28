# ui_helpers.py
import os
import base64
from PIL import Image
import streamlit as st

def resource_path(filename: str) -> str:
    """
    Retorna o caminho absoluto para um recurso localizado no mesmo diretório deste arquivo.
    Útil para Azure App Service onde o cwd pode variar.
    """
    base_dir = os.path.dirname(__file__)
    return os.path.join(base_dir, filename)

def set_background_png(png_filename: str):
    """
    Aplica o background somente uma vez por sessão para evitar reinjeções que causam
    duplicação/rolagem. Marca st.session_state['login_bg_applied'] = True.
    """
    try:
        if st.session_state.get("login_bg_applied"):
            return
    except Exception:
        pass

    try:
        path = png_filename
        if not os.path.isabs(path):
            path = resource_path(path)
        if not os.path.exists(path):
            return
        with open(path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode()
        css = f"""
        <style id="login-bg">
        /* Background aplicado apenas ao container da app (não modifica altura/overflow global) */
        .stApp {{
            background-image: url("data:image/png;base64,{encoded}");
            background-size: cover;
            background-repeat: no-repeat;
            background-position: center center;
            background-attachment: fixed;
        }}
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)
        try:
            st.session_state["login_bg_applied"] = True
        except Exception:
            pass
    except Exception:
        return

def clear_login_background():
    """
    Marca que o background de login deve ser considerado removido.
    Aplicar aplicar_estilos() sobrescreverá o background injetado.
    """
    try:
        st.session_state["login_bg_applied"] = False
    except Exception:
        pass

def show_logo(logo_filename: str, width: int = 120, use_caption: bool = False):
    """
    Exibe a logo a partir de arquivo. Usa resource_path por segurança em deploys.
    """
    try:
        path = logo_filename
        if not os.path.isabs(path):
            path = resource_path(path)
        if not os.path.exists(path):
            return
        img = Image.open(path)
        st.image(img, width=width, use_column_width=False, caption=logo_filename if use_caption else None)
    except Exception:
        return

def inject_login_css():
    """
    CSS específico para a tela de login: centraliza o cartão, define largura fixa/responsiva,
    organiza os botões abaixo do cartão e evita rolagem desnecessária.
    Chame somente quando estiver exibindo a tela de login.
    """
    css = """
    <style id="login-css">
    /* Garantir que o wrapper do login não force scroll desnecessário e centralizar conteúdo */
    .login-wrapper {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 100vh;
        padding: 4vh 16px;
        box-sizing: border-box;
    }
    /* Card do login */
    .login-card {
        width: 420px;
        max-width: calc(100% - 32px);
        background: rgba(15, 23, 42, 0.90);
        border-radius: 12px;
        padding: 20px 22px;
        box-shadow: 0 8px 30px rgba(0,0,0,0.55);
        border: 1px solid rgba(255,255,255,0.04);
    }
    /* Logo centralizada acima do card */
    .login-logo {
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 8px;
    }
    /* Título e subtítulo */
    .login-title { text-align: center; margin-top: 8px; margin-bottom: 4px; color: #E5E7EB; }
    .login-subtitle { text-align: center; color: rgba(255,255,255,0.65); margin-bottom: 14px; }

    /* Links abaixo do login (Criar cadastro / Esqueci senha) */
    .login-links {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        max-width: 420px;
        margin: 12px auto 0 auto;
    }
    .login-links .stButton > button {
        background: transparent !important;
        color: var(--primary, #2563EB) !important;
        border: 0 !important;
        padding: 8px 12px !important;
        box-shadow: none !important;
        font-size: 13px !important;
        border-radius: 8px !important;
    }

    /* Responsividade: em telas muito pequenas o card ocupa a maior parte */
    @media(max-width: 480px) {
        .login-card { width: 92%; padding: 16px; }
        .login-links { flex-direction: column; gap: 8px; align-items: center; }
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
