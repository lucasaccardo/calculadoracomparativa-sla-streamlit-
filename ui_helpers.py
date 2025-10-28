import os
import base64
from PIL import Image
import streamlit as st

def resource_path(filename: str) -> str:
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
        # st.session_state pode não existir em contextos raros; continuar
        pass

    try:
        path = png_filename
        if not os.path.isabs(path):
            path = resource_path(path)
        if not os.path.exists(path):
            # silêncio — não quebrar se imagem não existir
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
        # não quebre o app se algo falhar
        return

def clear_login_background():
    """
    Marca que o background de login deve ser considerado removido.
    A remoção efetiva acontece ao injetar novamente o CSS neutro (aplicar_estilos).
    """
    try:
        st.session_state["login_bg_applied"] = False
    except Exception:
        pass

def show_logo(logo_filename: str, width: int = 120, use_caption: bool = False):
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
    CSS para o cartão de login. Não altera html/body overflow global;
    controla apenas o wrapper do login para evitar rolagem indesejada.
    """
    css = """
    <style id="login-css">
    .login-wrapper {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 100vh;
        padding: 4vh 16px;
        box-sizing: border-box;
    }
    .login-card {
        width: 420px;
        max-width: calc(100% - 32px);
        background: rgba(15, 23, 42, 0.90);
        border-radius: 12px;
        padding: 20px 22px;
        box-shadow: 0 8px 30px rgba(0,0,0,0.55);
        border: 1px solid rgba(255,255,255,0.04);
    }
    .login-logo { display:flex; align-items:center; justify-content:center; margin-bottom:8px; }
    .login-title { text-align:center; margin-top:8px; margin-bottom:4px; color: #E5E7EB; }
    .login-subtitle { text-align:center; color: rgba(255,255,255,0.65); margin-bottom:14px; }

    .login-links {
        display:flex;
        justify-content:space-between;
        gap:12px;
        max-width:420px;
        margin:12px auto 0 auto;
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

    @media (max-width: 480px) {
        .login-card { width: 92%; padding: 16px; }
        .login-links { flex-direction: column; gap: 8px; align-items: center; }
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
