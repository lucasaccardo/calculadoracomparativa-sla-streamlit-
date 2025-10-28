# streamlit_app.py
# Arquivo completo atualizado — aplica background só no login, inclui carregar_base e load_user_db.

import os
import sys
import base64
import secrets
import hashlib
import re
import smtplib
from io import BytesIO
from datetime import datetime, timedelta
from email.message import EmailMessage
from textwrap import dedent
from typing import Optional, Tuple, List

import pandas as pd
import numpy as np
import streamlit as st
from passlib.context import CryptContext
from PIL import Image
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from streamlit.components.v1 import html as components_html

# helpers (arquivo ui_helpers.py)
from ui_helpers import set_background_png, show_logo, inject_login_css, resource_path, clear_login_background

# ==== Senhas e helpers ====
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except Exception:
        return default

USERS_PATH = get_secret("USERS_PATH", os.path.join("/home" if os.path.isdir("/home") else os.getcwd(), "data", "users.csv"))
try:
    os.makedirs(os.path.dirname(USERS_PATH), exist_ok=True)
except Exception:
    fallback_path = os.path.join(os.getcwd(), "data", "users.csv")
    USERS_PATH = fallback_path
    try:
        os.makedirs(os.path.dirname(USERS_PATH), exist_ok=True)
    except Exception:
        import tempfile
        USERS_PATH = os.path.join(tempfile.gettempdir(), "users.csv")

def is_bcrypt_hash(s: str) -> bool:
    return isinstance(s, str) and s.startswith("$2")

def hash_password(password: str) -> str:
    try:
        return pwd_context.hash(password)
    except Exception:
        return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_hash: str, provided_password: str) -> Tuple[bool, bool]:
    if is_bcrypt_hash(stored_hash):
        try:
            ok = pwd_context.verify(provided_password, stored_hash)
            return ok, (ok and pwd_context.needs_update(stored_hash))
        except Exception:
            return False, False
    legacy = hashlib.sha256(provided_password.encode()).hexdigest()
    ok = (stored_hash == legacy)
    return ok, bool(ok)

# =========================
# CONFIGURAÇÃO DA PÁGINA (uma vez)
# =========================
try:
    st.set_page_config(
        page_title="Frotas Vamos SLA",
        page_icon="logo_sidebar.png" if os.path.exists(resource_path("logo_sidebar.png")) else "🚛",
        layout="wide",
        initial_sidebar_state="expanded"
    )
except Exception:
    pass

# =========================
# Funções de carregamento de imagens (cache)
# =========================
@st.cache_data
def load_image_b64(path: str) -> Optional[str]:
    try:
        p = path if os.path.isabs(path) else resource_path(path)
        if os.path.exists(p):
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        pass
    return None

@st.cache_data
def load_logo_image_b64() -> Optional[Tuple[str, str]]:
    candidates = [("image/png", "fleetvamossla.png"), ("image/jpeg", "logo.jpg"), ("image/png", "logo.png")]
    for mime, path in candidates:
        b = load_image_b64(path)
        if b:
            return (mime, b)
    return None

# =========================
# aplicar_estilos: tema neutro e garante remoção do background de login
# =========================
def aplicar_estilos():
    """
    Tema neutro/corporativo aplicado nas telas autenticadas.
    Também força background-image: none para sobrescrever qualquer CSS injetado no login.
    """
    override_bg = """
    .stApp {
        background-image: none !important;
        background: var(--bg, #0B0F17) !important;
    }
    """

    logo_rule = ""
    logo_loaded = load_logo_image_b64()
    if logo_loaded:
        mime, logo_b64 = logo_loaded
        logo_rule = f"""
        .brand-badge {{
          position: fixed;
          top: 16px;
          left: 16px;
          width: 140px;
          height: 44px;
          background-image: url(data:{mime};base64,{logo_b64});
          background-size: contain;
          background-position: left center;
          background-repeat: no-repeat;
          z-index: 1000;
          filter: drop-shadow(0 4px 12px rgba(0,0,0,0.6));
          opacity: 0.98;
          pointer-events: none;
        }}"""

    css = f"""
    <style id="app-theme-override">
      :root {{
        --bg: #0B0F17;
        --sidebar: #111827;
        --card: #0F172A;
        --surface: #0F172A;
        --border: rgba(255,255,255,0.08);
        --text: #E5E7EB;
        --muted: #94A3B8;
        --primary: #2563EB;
      }}

      {override_bg}

      section.main > div.block-container {{
        max-width: 1040px !important;
        margin: 0 auto !important;
        padding-top: 1.0rem !important;
        padding-bottom: 2.0rem !important;
      }}

      .main-container, [data-testid="stForm"], [data-testid="stExpander"] > div {{
        background-color: var(--card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
      }}

      header[data-testid="stHeader"], #MainMenu, footer {{ display: none !important; }}

      {logo_rule}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    if logo_rule:
        st.markdown("<div class='brand-badge' aria-hidden='true'></div>", unsafe_allow_html=True)

    # limpa flag de login bg para permitir reaplicar no próximo logout/login
    try:
        st.session_state["login_bg_applied"] = False
    except Exception:
        pass

# Aplica tema neutro por padrão ao iniciar
try:
    aplicar_estilos()
except Exception:
    pass

# =========================
# POLÍTICA DE SENHA
# =========================
PASSWORD_MIN_LEN = 10
SPECIAL_CHARS = r"!@#$%^&*()_+\-=\[\]{};':\",.<>/?\\|`~"
def validate_password_policy(password: str, username: str = "", email: str = ""):
    errors = []
    if len(password) < PASSWORD_MIN_LEN:
        errors.append(f"Senha deve ter pelo menos {PASSWORD_MIN_LEN} caracteres.")
    if not re.search(r"[A-Z]", password):
        errors.append("Senha deve conter pelo menos 1 letra maiúscula.")
    if not re.search(r"[a-z]", password):
        errors.append("Senha deve conter pelo menos 1 letra minúscula.")
    if not re.search(r"[0-9]", password):
        errors.append("Senha deve conter pelo menos 1 número.")
    if not re.search(rf"[{re.escape(SPECIAL_CHARS)}]", password):
        errors.append("Senha deve conter pelo menos 1 caractere especial.")
    uname = (username or "").strip().lower()
    local_email = (email or "").split("@")[0].strip().lower()
    if uname and uname in password.lower():
        errors.append("Senha não pode conter o seu usuário.")
    if local_email and local_email in password.lower():
        errors.append("Senha não pode conter a parte local do seu e-mail.")
    return (len(errors) == 0), errors

# =========================
# UTILS / DB USERS / BASE
# =========================
REQUIRED_USER_COLUMNS = [
    "username", "password", "role", "full_name", "matricula",
    "email", "status", "accepted_terms_on", "reset_token", "reset_expires_at",
    "last_password_change", "force_password_reset"
]

SUPERADMIN_USERNAME = "lucas.sureira"

@st.cache_data
def load_user_db() -> pd.DataFrame:
    """
    Carrega (ou cria) o CSV de usuários. Mantive compatibilidade com sua lógica original.
    """
    tmp_pwd = (get_secret("SUPERADMIN_DEFAULT_PASSWORD", "") or "").strip()
    admin_defaults = {
        "username": SUPERADMIN_USERNAME,
        "password": hash_password(tmp_pwd) if tmp_pwd else "",
        "role": "superadmin",
        "full_name": "Lucas Mateus Sureira",
        "matricula": "30159179",
        "email": "lucas.sureira@grupovamos.com.br",
        "status": "aprovado",
        "accepted_terms_on": "",
        "reset_token": "",
        "reset_expires_at": "",
        "last_password_change": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if tmp_pwd else "",
        "force_password_reset": "" if tmp_pwd else "1",
    }

    def recreate_df() -> pd.DataFrame:
        df_new = pd.DataFrame([admin_defaults])
        try:
            df_new.to_csv(USERS_PATH, index=False)
        except Exception:
            pass
        return df_new

    if os.path.exists(USERS_PATH) and os.path.getsize(USERS_PATH) > 0:
        try:
            df = pd.read_csv(USERS_PATH, dtype=str).fillna("")
        except Exception:
            try:
                bak_path = os.path.join(os.path.dirname(USERS_PATH), f"users.csv.bak.{int(datetime.utcnow().timestamp())}")
                os.replace(USERS_PATH, bak_path)
            except Exception:
                pass
            df = recreate_df()
            return df
    else:
        return recreate_df()

    for col in REQUIRED_USER_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    if SUPERADMIN_USERNAME in df["username"].values:
        idx = df.index[df["username"] == SUPERADMIN_USERNAME][0]
        df.loc[idx, "role"] = "superadmin"
        df.loc[idx, "status"] = "aprovado"
    else:
        df = pd.concat([df, pd.DataFrame([admin_defaults])], ignore_index=True)

    try:
        df.to_csv(USERS_PATH, index=False)
    except Exception:
        pass
    return df

def save_user_db(df_users: pd.DataFrame):
    for col in REQUIRED_USER_COLUMNS:
        if col not in df_users.columns:
            df_users[col] = ""
    df_users = df_users[REQUIRED_USER_COLUMNS]
    try:
        df_users.to_csv(USERS_PATH, index=False)
    except Exception:
        pass
    st.cache_data.clear()

@st.cache_data
def carregar_base() -> Optional[pd.DataFrame]:
    """
    Carrega a base Excel; usa resource_path para compatibilidade com deploy.
    """
    try:
        return pd.read_excel(resource_path("Base De Clientes Faturamento.xlsx"))
    except Exception:
        return None

# =========================
# FUNÇÕES DE CÁLCULO / PDFs (mantive sua lógica)
# =========================
def formatar_moeda(valor: float) -> str:
    return f"R${valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def moeda_para_float(valor_str) -> float:
    if isinstance(valor_str, (int, float)):
        return float(valor_str)
    if isinstance(valor_str, str):
        valor_str = valor_str.replace("R$", "").replace(".", "").replace(",", ".").strip()
        try:
            return float(valor_str)
        except Exception:
            return 0.0
    return 0.0

def calcular_cenario_comparativo(cliente, placa, entrada, saida, feriados, servico, pecas, mensalidade):
    dias = np.busday_count(entrada.strftime('%Y-%m-%d'), (saida + timedelta(days=1)).strftime('%Y-%m-%d'))
    dias_uteis = max(dias - int(feriados or 0), 0)
    sla_dict = {"Preventiva – 2 dias úteis": 2, "Corretiva – 3 dias úteis": 3,
                "Preventiva + Corretiva – 5 dias úteis": 5, "Motor – 15 dias úteis": 15}
    sla_dias = sla_dict.get(servico, 0)
    excedente = max(0, dias_uteis - sla_dias)
    desconto = (mensalidade / 30) * excedente if excedente > 0 else 0
    total_pecas = sum(float(p["valor"]) for p in pecas) if isinstance(pecas, list) else 0.0
    total_final = (mensalidade - desconto) + total_pecas
    return {
        "Cliente": cliente, "Placa": placa,
        "Data Entrada": entrada.strftime("%d/%m/%Y"),
        "Data Saída": saida.strftime("%d/%m/%Y"),
        "Serviço": servico, "Dias Úteis": dias_uteis,
        "SLA (dias)": sla_dias, "Excedente": excedente,
        "Mensalidade": formatar_moeda(mensalidade),
        "Desconto": formatar_moeda(round(desconto, 2)),
        "Peças (R$)": formatar_moeda(round(total_pecas, 2)),
        "Total Final (R$)": formatar_moeda(round(total_final, 2)),
        "Detalhe Peças": pecas
    }

def gerar_pdf_comparativo(df_cenarios: pd.DataFrame, melhor_cenario: dict):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
    elementos, styles = [], getSampleStyleSheet()
    styles['Normal'].leading = 14
    elementos.append(Paragraph("🚛 Relatório Comparativo de Cenários SLA", styles['Title']))
    elementos.append(Spacer(1, 24))
    for i, row in df_cenarios.iterrows():
        elementos.append(Paragraph(f"<b>Cenário {i+1}</b>", styles['Heading2']))
        for col, valor in row.items():
            if col != "Detalhe Peças":
                elementos.append(Paragraph(f"<b>{col}:</b> {valor}", styles['Normal']))
        if isinstance(row.get("Detalhe Peças", []), list) and row["Detalhe Peças"]:
            elementos.append(Paragraph("<b>Detalhe de Peças:</b>", styles['Normal']))
            for peca in row["Detalhe Peças"]:
                elementos.append(Paragraph(f"- {peca['nome']}: {formatar_moeda(peca['valor'])}", styles['Normal']))
        elementos.append(Spacer(1, 12))
        elementos.append(Paragraph("─" * 90, styles['Normal']))
        elementos.append(Spacer(1, 12))
    texto_melhor = (f"<b>🏆 Melhor Cenário (Menor Custo Final)</b><br/>"
                    f"Serviço: {melhor_cenario['Serviço']}<br/>"
                    f"Placa: {melhor_cenario['Placa']}<br/>"
                    f"<b>Total Final: {melhor_cenario['Total Final (R$)']}</b>")
    elementos.append(Spacer(1, 12))
    elementos.append(Paragraph(texto_melhor, styles['Heading2']))
    doc.build(elementos)
    buffer.seek(0)
    return buffer

def calcular_sla_simples(data_entrada, data_saida, prazo_sla, valor_mensalidade, feriados):
    def to_date(obj):
        if hasattr(obj, "date"):
            return obj.date()
        return obj
    dias = np.busday_count(np.datetime64(to_date(data_entrada)), np.datetime64(to_date(data_saida + timedelta(days=1))))
    dias -= int(feriados or 0)
    dias = max(dias, 0)
    if dias <= prazo_sla:
        status = "Dentro do prazo"; desconto = 0; dias_excedente = 0
    else:
        status = "Fora do prazo"
        dias_excedente = dias - prazo_sla
        desconto = (valor_mensalidade / 30) * dias_excedente
    return dias, status, desconto, dias_excedente

def gerar_pdf_sla_simples(cliente, placa, tipo_servico, dias_uteis_manut, prazo_sla, dias_excedente, valor_mensalidade, desconto):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    largura, altura = letter
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, altura - 50, "Resultado SLA - Vamos Locação")
    c.setFont("Helvetica", 12)
    y = altura - 80
    text_lines = [
        f"Cliente: {cliente}",
        f"Placa: {placa}",
        f"Tipo de serviço: {tipo_servico}",
        f"Dias úteis da manutenção: {dias_uteis_manut} dias",
        f"Prazo SLA: {prazo_sla} dias",
        f"Dias excedido de SLA: {dias_excedente} dias",
        f"Valor Mensalidade: {formatar_moeda(valor_mensalidade)}",
        f"Valor do desconto: {formatar_moeda(desconto)}"
    ]
    for line in text_lines:
        c.drawString(50, y, line); y -= 20
    c.showPage(); c.save(); buffer.seek(0); return buffer

# =========================
# NAV HELPERS / ESTADO
# =========================
def ir_para_home(): st.session_state.tela = "home"
def ir_para_calc_comparativa(): st.session_state.tela = "calc_comparativa"
def ir_para_calc_simples(): st.session_state.tela = "calc_simples"
def ir_para_admin(): st.session_state.tela = "admin_users"
def ir_para_login(): st.session_state.tela = "login"
def ir_para_register(): st.session_state.tela = "register"
def ir_para_forgot(): st.session_state.tela = "forgot_password"
def ir_para_reset(): st.session_state.tela = "reset_password"
def ir_para_force_change(): st.session_state.tela = "force_change_password"

def limpar_dados_comparativos():
    for key in ["cenarios", "pecas_atuais", "mostrar_comparativo"]:
        if key in st.session_state: del st.session_state[key]

def limpar_dados_simples():
    for key in ["resultado_sla", "pesquisa_cliente"]:
        if key in st.session_state: del st.session_state[key]

def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.experimental_rerun()

def user_is_admin():
    return st.session_state.get("role") in ("admin", "superadmin")

def user_is_superadmin():
    return st.session_state.get("username") == SUPERADMIN_USERNAME or st.session_state.get("role") == "superadmin"

def renderizar_sidebar():
    with st.sidebar:
        st.markdown("<div class='sidebar-center'>", unsafe_allow_html=True)
        try:
            st.image(resource_path("logo_sidebar.png"), width=100)
        except Exception:
            try:
                st.image(resource_path("logo.png"), width=100)
            except Exception:
                pass
        st.header("Menu de Navegação")
        if user_is_admin():
            st.button("👤 Gerenciar Usuários", on_click=ir_para_admin, use_container_width=True)
        st.button("🏠 Voltar para Home", on_click=ir_para_home, use_container_width=True)
        if st.session_state.tela == "calc_comparativa":
            st.button("🔄 Limpar Comparação", on_click=limpar_dados_comparativos, use_container_width=True)
        if st.session_state.tela == "calc_simples":
            st.button("🔄 Limpar Cálculo", on_click=limpar_dados_simples, use_container_width=True)
        st.button("🚪 Sair (Logout)", on_click=logout, type="secondary", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

# Inicialização de estado
if "tela" not in st.session_state:
    st.session_state.tela = "login"

# Token reset via URL
qp = {}
try:
    qp = dict(st.query_params)
except Exception:
    try:
        qp = {k: (v[0] if isinstance(v, list) else v) for k, v in st.experimental_get_query_params().items()}
    except Exception:
        qp = {}
incoming_token = qp.get("reset_token") or qp.get("token") or ""
if incoming_token and not st.session_state.get("ignore_reset_qp"):
    st.session_state.incoming_reset_token = incoming_token
    st.session_state.tela = "reset_password"

# =========================
# TELAS (parte principal)
# =========================
if st.session_state.tela == "login":
    # Aplica background e CSS do login (uma única vez)
    try:
        set_background_png(resource_path("background.png"))
    except Exception:
        pass
    try:
        inject_login_css()
    except Exception:
        pass

    st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)
    st.markdown('<div class="login-card">', unsafe_allow_html=True)

    try:
        st.markdown('<div class="login-logo">', unsafe_allow_html=True)
        show_logo(resource_path("logo.png"), width=140)
        st.markdown('</div>', unsafe_allow_html=True)
    except Exception:
        pass

    st.markdown('<h1 class="login-title">Frotas Vamos SLA</h1>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">Acesso restrito | Soluções inteligentes para frotas</div>', unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Usuário", placeholder="Usuário")
        password = st.text_input("Senha", type="password", placeholder="Senha")
        submit_login = st.form_submit_button("Entrar")

    st.markdown('</div>', unsafe_allow_html=True)  # fecha login-card

    st.markdown('<div class="login-links">', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Criar cadastro"):
            st.session_state.tela = "register"
            st.experimental_rerun()
    with c2:
        if st.button("Esqueci minha senha"):
            st.session_state.tela = "forgot_password"
            st.experimental_rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)  # fecha login-wrapper

    if submit_login:
        df_users = load_user_db()
        user_data = df_users[df_users["username"] == username]
        if user_data.empty:
            st.error("❌ Usuário ou senha incorretos.")
        else:
            row = user_data.iloc[0]
            valid, needs_up = verify_password(row["password"], password)
            if not valid:
                st.error("❌ Usuário ou senha incorretos.")
            else:
                try:
                    if needs_up:
                        idx = df_users.index[df_users["username"] == username][0]
                        df_users.loc[idx, "password"] = hash_password(password)
                        df_users.loc[idx, "last_password_change"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                        save_user_db(df_users)
                except Exception:
                    pass

                if row.get("status", "") != "aprovado":
                    st.warning("⏳ Seu cadastro ainda está pendente de aprovação pelo administrador.")
                else:
                    # Limpa background de login e reaplica tema neutro
                    try:
                        clear_login_background()
                    except Exception:
                        pass
                    try:
                        aplicar_estilos()
                    except Exception:
                        pass

                    st.session_state.logado = True
                    st.session_state.username = row["username"]
                    st.session_state.role = row.get("role", "user")
                    st.session_state.email = row.get("email", "")
                    st.session_state.tela = "home"
                    st.experimental_rerun()

else:
    # Conteúdo autenticado (todas as telas)
    renderizar_sidebar()
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)

    # ... resto das telas (register, forgot, reset, force_change, terms_consent, home, admin_users, calc_simples, calc_comparativa)
    # Aqui eu mantenho toda a lógica que você já tinha; caso precise, eu colo 100% do restante inline.
    # Garantimos que carregar_base() e load_user_db() existem antes do uso (resolvido acima).

    # Exemplo: Home (mantido de acordo com sua versão original)
    if st.session_state.tela == "home":
        st.title("🏠 Home")
        st.write(f"### Bem-vindo, {st.session_state.get('username','')}!")
        st.write("Selecione abaixo a ferramenta que deseja utilizar.")
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📊 Análise de Cenários")
            st.write("Calcule e compare múltiplos cenários para encontrar a opção com o menor custo final.")
            st.button("Acessar Análise de Cenários", on_click=ir_para_calc_comparativa, use_container_width=True)
        with col2:
            st.subheader("🖩 SLA Mensal")
            st.write("Calcule rapidamente o desconto de SLA para um único serviço ou veículo.")
            st.button("Acessar SLA Mensal", on_click=ir_para_calc_simples, use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# ESTADO INICIAL / ESTILOS
# =========================
if "tela" not in st.session_state:
    st.session_state.tela = "login"

# Aplica tema + background extra (aplicar_estilos usa imagens locais via resource_path)
try:
    aplicar_estilos()
except Exception:
    pass

# Token reset via URL
qp = get_query_params()
incoming_token = qp.get("reset_token") or qp.get("token") or ""
if incoming_token and not st.session_state.get("ignore_reset_qp"):
    st.session_state.incoming_reset_token = incoming_token
    st.session_state.tela = "reset_password"

# =========================
# TELAS
# =========================
if st.session_state.tela == "login":
    # Exibe logo (se existir) acima do título
    try:
        show_logo(resource_path("logo.png"), width=140)
    except Exception:
        pass

    st.markdown('<h1 class="login-title">Frotas Vamos SLA</h1>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">Acesso restrito | Soluções inteligentes para frotas</div>', unsafe_allow_html=True)

    # Formulário de login (estilizado como card via CSS)
    with st.form("login_form"):
        username = st.text_input("Usuário", placeholder="Usuário")
        password = st.text_input("Senha", type="password", placeholder="Senha")
        submit_login = st.form_submit_button("Entrar")

    # Links discretos abaixo do card (dentro do bloco de login)
    st.markdown('<div class="login-links">', unsafe_allow_html=True)
    # Se sua versão de Streamlit reclamar do vertical_alignment, remova o argumento
    try:
        c1, c2, c3 = st.columns([1, 1, 1], vertical_alignment="center")
    except TypeError:
        c1, c2, c3 = st.columns([1, 1, 1])

    with c1:
        st.write("")  # espaçador
    with c2:
        if st.button("Criar cadastro"):
            ir_para_register()
            st.rerun()
    with c3:
        if st.button("Esqueci minha senha"):
            ir_para_forgot()
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    if submit_login:
        df_users = load_user_db()
        user_data = df_users[df_users["username"] == username]
        if user_data.empty:
            st.error("❌ Usuário ou senha incorretos.")
        else:
            row = user_data.iloc[0]
            valid, needs_up = verify_password(row["password"], password)
            if not valid:
                st.error("❌ Usuário ou senha incorretos.")
            else:
                # Upgrade automático (SHA-256 -> bcrypt) quando possível
                try:
                    if needs_up:
                        idx = df_users.index[df_users["username"] == username][0]
                        df_users.loc[idx, "password"] = hash_password(password)
                        df_users.loc[idx, "last_password_change"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                        save_user_db(df_users)
                        row["password"] = df_users.loc[idx, "password"]
                except Exception:
                    pass

                if row.get("status", "") != "aprovado":
                    st.warning("⏳ Seu cadastro ainda está pendente de aprovação pelo administrador.")
                else:
                    st.session_state.logado = True
                    st.session_state.username = row["username"]
                    st.session_state.role = row.get("role", "user")
                    st.session_state.email = row.get("email", "")
                    if not str(row.get("accepted_terms_on", "")).strip():
                        st.session_state.tela = "terms_consent"
                        st.rerun()
                    if is_password_expired(row) or str(row.get("force_password_reset", "")).strip():
                        st.session_state.tela = "force_change_password"
                        st.rerun()
                    st.session_state.tela = "home"
                    st.rerun()

elif st.session_state.tela == "register":
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)
    st.title("🆕 Criar cadastro")
    st.info("Se a sua empresa já realizou um pré-cadastro, informe seu e-mail para pré-preencher os dados.")

    if "register_prefill" not in st.session_state:
        st.session_state.register_prefill = None

    with st.form("lookup_email_form"):
        lookup_email = st.text_input("E-mail corporativo para localizar pré-cadastro")
        lookup_submit = st.form_submit_button("Buscar pré-cadastro")
    if lookup_submit and lookup_email.strip():
        df = load_user_db()
        rows = df[df["email"].str.strip().str.lower() == lookup_email.strip().lower()]
        if rows.empty:
            st.warning("Nenhum pré-cadastro encontrado para este e-mail. Você poderá preencher os dados normalmente.")
            st.session_state.register_prefill = None
        else:
            r = rows.iloc[0].to_dict()
            st.session_state.register_prefill = r
            st.success("Pré-cadastro encontrado! Os campos abaixo foram preenchidos automaticamente.")
    pre = st.session_state.register_prefill

    lock_username = bool(pre and pre.get("username"))
    lock_fullname = bool(pre and pre.get("full_name"))
    lock_matricula = bool(pre and pre.get("matricula"))
    lock_email = bool(pre and pre.get("email"))

    with st.form("register_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        username = col1.text_input("Usuário (login)", value=(pre.get("username") if pre else ""), disabled=lock_username)
        full_name = col2.text_input("Nome completo", value=(pre.get("full_name") if pre else ""), disabled=lock_fullname)
        col3, col4 = st.columns(2)
        matricula = col3.text_input("Matrícula", value=(pre.get("matricula") if pre else ""), disabled=lock_matricula)
        email = col4.text_input("E-mail corporativo", value=(pre.get("email") if pre else lookup_email or ""), disabled=lock_email)
        col5, col6 = st.columns(2)
        password = col5.text_input("Senha", type="password", help="Mín 10, com maiúscula, minúscula, número e especial.")
        password2 = col6.text_input("Confirmar senha", type="password")
        submit_reg = st.form_submit_button("Enviar cadastro", type="primary", use_container_width=True)

    st.button("⬅️ Voltar ao login", on_click=ir_para_login)

    if submit_reg:
        df = load_user_db()
        if not all([(username or pre and pre.get("username")), (full_name or pre and pre.get("full_name")),
                    (email or pre and pre.get("email")), password.strip(), password2.strip()]):
            st.error("Preencha todos os campos obrigatórios.")
        elif password != password2:
            st.error("As senhas não conferem.")
        else:
            valid, errs = validate_password_policy(password, username=username, email=email)
            if not valid:
                st.error("Regras de senha não atendidas:\n- " + "\n- ".join(errs))
                st.stop()

            idxs = df.index[df["email"].str.strip().str.lower() == (email or pre.get("email", "")).strip().lower()]
            if len(idxs) > 0:
                idx = idxs[0]
                if not df.loc[idx, "username"]:
                    if (username.strip() in df["username"].values) and (df.loc[idx, "username"] != username.strip()):
                        st.error("Nome de usuário já existe.")
                        st.stop()
                    df.loc[idx, "username"] = username.strip()
                if not df.loc[idx, "full_name"]:
                    df.loc[idx, "full_name"] = full_name.strip()
                if not df.loc[idx, "matricula"]:
                    df.loc[idx, "matricula"] = matricula.strip()
                df.loc[idx, "password"] = hash_password(password)
                if df.loc[idx, "status"] == "":
                    df.loc[idx, "status"] = "pendente"
                df.loc[idx, "last_password_change"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                df.loc[idx, "force_password_reset"] = ""
                save_user_db(df)
                st.success("Cadastro atualizado! Aguarde aprovação do administrador (se ainda estiver pendente).")
            else:
                if username.strip() in df["username"].values:
                    st.error("Nome de usuário já existe.")
                    st.stop()
                new_user = {
                    "username": username.strip(),
                    "password": hash_password(password),
                    "role": "user",
                    "full_name": full_name.strip(),
                    "matricula": matricula.strip(),
                    "email": (email or "").strip(),
                    "status": "pendente",
                    "accepted_terms_on": "",
                    "reset_token": "",
                    "reset_expires_at": "",
                    "last_password_change": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    "force_password_reset": ""
                }
                df = pd.concat([df, pd.DataFrame([new_user])], ignore_index=True)
                save_user_db(df)
                st.success("✅ Cadastro enviado! Aguarde aprovação do administrador para acessar o sistema.")

elif st.session_state.tela == "forgot_password":
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)
    st.title("🔐 Esqueci minha senha")
    st.write("Informe seu e-mail cadastrado para enviar um link de redefinição de senha (válido por 30 minutos).")
    email = st.text_input("E-mail")
    colb1, colb2 = st.columns(2)
    enviar = colb1.button("Enviar link", type="primary", use_container_width=True)
    if colb2.button("⬅️ Voltar ao login", use_container_width=True):
        ir_para_login(); st.rerun()

    if enviar and email.strip():
        df = load_user_db()
        user_idx = df.index[df["email"].str.strip().str.lower() == email.strip().lower()]
        if len(user_idx) == 0:
            st.error("E-mail não encontrado.")
        else:
            idx = user_idx[0]
            if df.loc[idx, "status"] != "aprovado":
                st.warning("Seu cadastro ainda não foi aprovado pelo administrador.")
            else:
                token = secrets.token_urlsafe(32)
                expires = (datetime.utcnow() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
                df.loc[idx, "reset_token"] = token
                df.loc[idx, "reset_expires_at"] = expires
                save_user_db(df)

                base_url = get_app_base_url()
                if not base_url:
                    st.info("APP_BASE_URL não definido em st.secrets. Exibindo link gerado.")
                    base_url = "https://SEU_DOMINIO"
                reset_link = f"{base_url}?reset_token={token}"

                if send_reset_email(email.strip(), reset_link):
                    st.success("Enviamos um link para seu e-mail. Verifique sua caixa de entrada (e o SPAM).")
                  elif st.session_state.tela == "reset_password":
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)
    st.title("🔁 Redefinir senha")
    token = st.session_state.get("incoming_reset_token", "")
    token = st.text_input("Token de redefinição (se veio por link, já estará preenchido)", value=token)
    colp1, colp2 = st.columns(2)
    new_pass = colp1.text_input("Nova senha", type="password", help="Mín 10, com maiúscula, minúscula, número e especial.")
    new_pass2 = colp2.text_input("Confirmar nova senha", type="password")
    colb1, colb2 = st.columns(2)
    confirmar = colb1.button("Redefinir senha", type="primary", use_container_width=True)
    voltar = colb2.button("⬅️ Voltar ao login", use_container_width=True)

    if voltar:
        st.session_state.ignore_reset_qp = True
        st.session_state.incoming_reset_token = ""
        clear_all_query_params()
        ir_para_login()
        st.rerun()

    if confirmar:
        if not token.strip():
            st.error("Token é obrigatório.")
        elif not new_pass or not new_pass2:
            st.error("Informe e confirme a nova senha.")
        elif new_pass != new_pass2:
            st.error("As senhas não conferem.")
        else:
            df = load_user_db()
            rows = df[df["reset_token"] == token]
            if rows.empty:
                st.error("Token inválido.")
            else:
                idx = rows.index[0]
                try:
                    exp = datetime.strptime(df.loc[idx, "reset_expires_at"], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    exp = datetime.utcnow() - timedelta(minutes=1)
                if datetime.utcnow() > exp:
                    st.error("Token expirado. Solicite novamente.")
                else:
                    username = df.loc[idx, "username"]
                    email = df.loc[idx, "email"]
                    ok, errs = validate_password_policy(new_pass, username=username, email=email)
                    if not ok:
                        st.error("Regras de senha não atendidas:\n- " + "\n- ".join(errs))
                        st.stop()

                    _same, _ = verify_password(df.loc[idx, "password"], new_pass)
                    if _same:
                        st.error("A nova senha não pode ser igual à senha atual.")
                        st.stop()

                    df.loc[idx, "password"] = hash_password(new_pass)
                    df.loc[idx, "reset_token"] = ""
                    df.loc[idx, "reset_expires_at"] = ""
                    df.loc[idx, "last_password_change"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    df.loc[idx, "force_password_reset"] = ""
                    save_user_db(df)

                    st.success("Senha redefinida com sucesso! Faça login novamente.")
                    if st.button("Ir para login", type="primary"):
                        st.session_state.ignore_reset_qp = True
                        st.session_state.incoming_reset_token = ""
                        clear_all_query_params()
                        ir_para_login()
                        st.rerun()

elif st.session_state.tela == "force_change_password":
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)
    st.title("🔒 Alteração obrigatória de senha")
    st.warning("Sua senha expirou ou foi marcada para alteração. Defina uma nova senha para continuar.")
    col1, col2 = st.columns(2)
    new_pass = col1.text_input("Nova senha", type="password", help="Mín 10, com maiúscula, minúscula, número e especial.")
    new_pass2 = col2.text_input("Confirmar nova senha", type="password")
    if st.button("Atualizar senha", type="primary"):
        df = load_user_db()
        uname = st.session_state.get("username", "")
        rows = df[df["username"] == uname]
        if rows.empty:
            st.error("Sessão inválida. Faça login novamente.")
        else:
            idx = rows.index[0]
            email = df.loc[idx, "email"]

            if not new_pass or not new_pass2:
                st.error("Preencha os campos de senha."); st.stop()
            if new_pass != new_pass2:
                st.error("As senhas não conferem."); st.stop()

            ok, errs = validate_password_policy(new_pass, username=uname, email=email)
            if not ok:
                st.error("Regras de senha não atendidas:\n- " + "\n- ".join(errs)); st.stop()

            same, _ = verify_password(df.loc[idx, "password"], new_pass)
            if same:
                st.error("A nova senha não pode ser igual à senha atual."); st.stop()

            df.loc[idx, "password"] = hash_password(new_pass)
            df.loc[idx, "last_password_change"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            df.loc[idx, "force_password_reset"] = ""
            save_user_db(df)

            st.success("Senha atualizada com sucesso.")
            if not str(df.loc[idx, "accepted_terms_on"]).strip():
                st.session_state.tela = "terms_consent"
            else:
                st.session_state.tela = "home"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

elif st.session_state.tela == "terms_consent":
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)
    st.title("Termos e Condições de Uso e Política de Privacidade (LGPD)")
    st.info("Para seu primeiro acesso, é necessário ler e aceitar os termos de uso e a política de privacidade desta plataforma.")

    terms_html = dedent("""
    <div class="terms-box" style="color:#fff;font-family:Segoe UI,Arial,sans-serif;">
        <p><b>Última atualização:</b> 28 de Setembro de 2025</p>

        <h3>1. Finalidade da Ferramenta</h3>
        <p>Esta plataforma é um sistema interno para simulação e referência de cálculos de
        Service Level Agreement (SLA) e apoio operacional. Os resultados são estimativas
        destinadas ao uso profissional e não substituem documentos contratuais, fiscais
        ou aprovados formalmente pela empresa.</p>

        <h3>2. Base Legal e Conformidade com a LGPD</h3>
        <p>O tratamento de dados pessoais nesta plataforma observa a Lei nº 13.709/2018
        (Lei Geral de Proteção de Dados Pessoais – LGPD), adotando medidas técnicas e
        administrativas para proteger os dados contra acessos não autorizados e situações
        acidentais ou ilícitas de destruição, perda, alteração, comunicação ou difusão.</p>

        <h3>3. Dados Coletados e Tratados</h3>
        <ul>
            <li>Dados de autenticação: usuário (login), senha (armazenada de forma irreversível via hash), perfil de acesso (user/admin).</li>
            <li>Dados cadastrais: nome completo, matrícula, e-mail corporativo.</li>
            <li>Dados operacionais: clientes, placas, valores de mensalidade e informações utilizadas nos cálculos de SLA.</li>
            <li>Registros de aceite: data/hora do aceite dos termos.</li>
        </ul>

        <h3>4. Finalidades do Tratamento</h3>
        <ul>
            <li>Autenticação e autorização de acesso à plataforma.</li>
            <li>Execução dos cálculos de SLA e geração de relatórios.</li>
            <li>Gestão de usuários (aprovação de cadastro por administradores).</li>
            <li>Comunicações operacionais, como e-mail de redefinição de senha e avisos de aprovação de conta.</li>
        </ul>

        <h3>5. Compartilhamento e Acesso</h3>
        <p>Os dados processados são de uso interno e não são compartilhados com terceiros,
        exceto quando necessários para cumprimento de obrigações legais ou ordem de
        autoridades competentes.</p>

        <h3>6. Segurança da Informação</h3>
        <ul>
            <li>Senhas armazenadas com algoritmo de hash (não reversível).</li>
            <li>Acesso restrito a usuários autorizados e administradores.</li>
            <li>Envio de e-mails mediante configurações autenticadas de SMTP corporativo.</li>
        </ul>

        <h3>7. Direitos dos Titulares</h3>
        <p>Nos termos da LGPD, o titular possui direitos como confirmação de tratamento,
        acesso, correção, anonimização, bloqueio, eliminação de dados desnecessários,
        portabilidade (quando aplicável) e informação sobre compartilhamentos.</p>

        <h3>8. Responsabilidades do Usuário</h3>
        <ul>
            <li>Manter a confidencialidade de suas credenciais de acesso.</li>
            <li>Utilizar a plataforma apenas para fins profissionais internos.</li>
            <li>Respeitar as políticas internas e as legislações aplicáveis.</li>
        </ul>

        <h3>9. Retenção e Eliminação</h3>
        <p>Os dados são mantidos pelo período necessário ao atendimento das finalidades
        acima e das políticas internas. Após esse período, poderão ser eliminados ou
        anonimizados, salvo obrigações legais de retenção.</p>

        <h3>10. Alterações dos Termos</h3>
        <p>Estes termos podem ser atualizados a qualquer tempo, mediante publicação
        de nova versão na própria plataforma. Recomenda-se a revisão periódica.</p>

        <h3>11. Contato</h3>
        <p>Em caso de dúvidas sobre estes Termos ou sobre o tratamento de dados pessoais,
        procure o time responsável pela ferramenta ou o canal corporativo de Privacidade/DPD.</p>
    </div>
    """)
    components_html(terms_html, height=520, scrolling=True)

    st.markdown("---")
    consent = st.checkbox("Eu li e concordo com os Termos e Condições.")
    if st.button("Continuar", disabled=not consent, type="primary"):
        df_users = load_user_db()
        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        username = st.session_state.get("username", "")
        if username:
            user_index = df_users.index[df_users['username'] == username]
            if len(user_index) > 0:
                df_users.loc[user_index[0], 'accepted_terms_on'] = now
                save_user_db(df_users)
        row = df_users[df_users['username'] == username].iloc[0]
        if is_password_expired(row) or str(row.get("force_password_reset", "")).strip():
            st.session_state.tela = "force_change_password"
        else:
            st.session_state.tela = "home"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

else:
    # Conteúdo autenticado
    renderizar_sidebar()
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)

    if st.session_state.tela == "home":
        st.title("🏠 Home")
        st.write(f"### Bem-vindo, {st.session_state.get('username','')}!")
        st.write("Selecione abaixo a ferramenta que deseja utilizar.")
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📊 Análise de Cenários")
            st.write("Calcule e compare múltiplos cenários para encontrar a opção com o menor custo final.")
            st.button("Acessar Análise de Cenários", on_click=ir_para_calc_comparativa, use_container_width=True)
        with col2:
            st.subheader("🖩 SLA Mensal")
            st.write("Calcule rapidamente o desconto de SLA para um único serviço ou veículo.")
            st.button("Acessar SLA Mensal", on_click=ir_para_calc_simples, use_container_width=True)

    elif st.session_state.tela == "admin_users":
        st.title("👤 Gerenciamento de Usuários")
        df_users = load_user_db()

        # Teste de SMTP
        with st.expander("✉️ Testar envio de e-mail (SMTP)", expanded=False):
            st.write("Use este teste para validar rapidamente as credenciais de e-mail em st.secrets.")
            test_to = st.text_input("Enviar e-mail de teste para:")
            if st.button("Enviar e-mail de teste"):
                if not test_to.strip():
                    st.warning("Informe um e-mail de destino.")
                else:
                    ok = send_email(
                        test_to.strip(),
                        "Teste SMTP - Frotas Vamos SLA",
                        "E-mail de teste enviado pelo aplicativo.",
                        build_email_html(
                            title="Teste de e-mail",
                            subtitle="Este é um e-mail de teste do Frotas Vamos SLA.",
                            body_lines=["Se você recebeu, o SMTP está funcionando corretamente."],
                            cta_label="Abrir plataforma",
                            cta_url=get_app_base_url() or "https://streamlit.io"
                        )
                    )
                    if ok:
                        st.success("E-mail de teste enviado com sucesso!")
            st.write("Status configurações:")
            st.write(f"- APP_BASE_URL: {'OK' if get_app_base_url() else 'NÃO CONFIGURADO'}")
            st.write(f"- SMTP: {'OK' if smtp_available() else 'NÃO CONFIGURADO'}")

        # Aprovação de cadastros pendentes
        st.subheader("Aprovar Cadastros Pendentes")
        pendentes = df_users[df_users["status"] == "pendente"]
        if pendentes.empty:
            st.info("Não há cadastros pendentes.")
        else:
            st.dataframe(pendentes["username full_name email matricula".split()], use_container_width=True, hide_index=True)
            pendentes_list = pendentes["username"].tolist()
            to_approve = st.multiselect("Selecione usuários para aprovar:", options=pendentes_list)
            colap1, colap2 = st.columns(2)
            if colap1.button("✅ Aprovar selecionados", type="primary", use_container_width=True):
                if to_approve:
                    base_url = get_app_base_url() or "https://SEU_DOMINIO"
                    for uname in to_approve:
                        idx = df_users.index[df_users["username"] == uname][0]
                        df_users.loc[idx, "status"] = "aprovado"
                        email = df_users.loc[idx, "email"].strip()
                        if email:
                            if not df_users.loc[idx, "password"]:
                                token = secrets.token_urlsafe(32)
                                expires = (datetime.utcnow() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
                                df_users.loc[idx, "reset_token"] = token
                                df_users.loc[idx, "reset_expires_at"] = expires
                                reset_link = f"{base_url}?reset_token={token}"
                                send_invite_to_set_password(email, reset_link)
                            else:
                                send_approved_email(email, base_url)
                    save_user_db(df_users)
                    st.success("Usuários aprovados (e e-mails enviados, se configurado).")
                    st.rerun()
                else:
                    st.warning("Selecione ao menos um usuário.")
            if colap2.button("🗑️ Rejeitar (remover) selecionados", use_container_width=True):
                if to_approve:
                    to_remove = [u for u in to_approve if u != SUPERADMIN_USERNAME]
                    df_users = df_users[~df_users["username"].isin(to_remove)]
                    save_user_db(df_users)
                    st.success("Usuários removidos com sucesso.")
                    st.rerun()
                else:
                    st.warning("Selecione ao menos um usuário.")

        st.markdown("---")

        # Adicionar novo usuário
        st.subheader("Adicionar Novo Usuário (admin)")
        with st.form("add_user_form", clear_on_submit=True):
            new_username = st.text_input("Usuário (para login)")
            new_full_name = st.text_input("Nome Completo")
            new_matricula = st.text_input("Matrícula")
            new_email = st.text_input("E-mail")
            new_password = st.text_input("Senha Temporária (opcional)", type="password", help="Se não preencher, o usuário receberá e-mail para definir a senha.")
            new_role = st.selectbox("Tipo de Acesso", ["user", "admin"])
            aprovar_agora = st.checkbox("Aprovar agora", value=True)
            if st.form_submit_button("Adicionar Usuário"):
                if new_username in df_users["username"].values:
                    st.error("Este nome de usuário já existe.")
                elif not all([new_username.strip(), new_full_name.strip(), new_email.strip()]):
                    st.error("Usuário, nome completo e e-mail são obrigatórios.")
                else:
                    status = "aprovado" if aprovar_agora else "pendente"
                    pwd_hash = ""
                    if new_password.strip():
                        ok, errs = validate_password_policy(new_password, username=new_username, email=new_email)
                        if not ok:
                            st.error("Regras de senha não atendidas:\n- " + "\n- ".join(errs))
                            st.stop()
                        pwd_hash = hash_password(new_password)

                    new_user_data = pd.DataFrame([{
                        "username": new_username.strip(),
                        "password": pwd_hash,
                        "role": "admin" if new_role == "admin" else "user",
                        "full_name": new_full_name.strip(),
                        "matricula": new_matricula.strip(),
                        "email": new_email.strip(),
                        "status": status,
                        "accepted_terms_on": "",
                        "reset_token": "",
                        "reset_expires_at": "",
                        "last_password_change": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if pwd_hash else "",
                        "force_password_reset": "" if pwd_hash else "1"
                    }])
                    df_users = pd.concat([df_users, new_user_data], ignore_index=True)
                    save_user_db(df_users)

                    base_url = get_app_base_url() or "https://SEU_DOMINIO"
                    if status == "aprovado" and new_email.strip():
                        if not pwd_hash:
                            idx = df_users.index[df_users["username"] == new_username.strip()][0]
                            token = secrets.token_urlsafe(32)
                            expires = (datetime.utcnow() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
                            df_users.loc[idx, "reset_token"] = token
                            df_users.loc[idx, "reset_expires_at"] = expires
                            save_user_db(df_users)
                            reset_link = f"{base_url}?reset_token={token}"
                            send_invite_to_set_password(new_email.strip(), reset_link)
                        else:
                            send_approved_email(new_email.strip(), base_url)

                    st.success(f"Usuário '{new_username}' adicionado com sucesso!")

        st.markdown("---")

        # Usuários existentes (busca, promoção a admin e remoção)
        st.subheader("Usuários Existentes")
        for col in ["full_name", "matricula", "accepted_terms_on", "email", "status", "last_password_change", "role"]:
            if col not in df_users.columns:
                df_users[col] = ""

        termo = st.text_input("Buscar por usuário, nome, e-mail ou matrícula:")
        df_view = df_users.copy()
        if termo.strip():
            t = termo.strip().lower()
            mask = (
                df_view["username"].str.lower().str.contains(t, na=False) |
                df_view["full_name"].str.lower().str.contains(t, na=False) |
                df_view["email"].str.lower().str.contains(t, na=False) |
                df_view["matricula"].str.lower().str.contains(t, na=False)
            )
            df_view = df_view[mask]

        st.dataframe(
            df_view[["username", "full_name", "matricula", "email", "role", "status", "accepted_terms_on", "last_password_change"]],
            use_container_width=True
        )

        # Promoção a admin
        st.markdown("#### Conceder acesso de administrador")
        promote_candidates = df_users[
            (df_users["role"].str.lower() != "admin") &
            (df_users["role"].str.lower() != "superadmin")
        ]["username"].tolist()
        selected_to_promote = st.multiselect("Selecione usuários (atuais 'user') para promover a admin:", options=promote_candidates)

        if st.button("Conceder admin aos selecionados", type="primary", disabled=not user_is_admin()):
            if not selected_to_promote:
                st.warning("Nenhum usuário selecionado para promoção.")
            else:
                changed = []
                for uname in selected_to_promote:
                    if uname == SUPERADMIN_USERNAME:
                        continue
                    idxs = df_users.index[df_users["username"] == uname]
                    if len(idxs) == 0:
                        continue
                    idx = idxs[0]
                    if df_users.loc[idx, "role"].lower() in ["admin", "superadmin"]:
                        continue
                    df_users.loc[idx, "role"] = "admin"
                    changed.append(uname)
                if changed:
                    save_user_db(df_users)
                    st.success(f"Permissão de admin concedida para: {', '.join(changed)}")
                    st.rerun()
                else:
                    st.info("Nenhuma alteração realizada.")

        st.markdown("---")

        st.markdown("#### Remover usuários")
        candidates = [u for u in df_users["username"].tolist() if u != SUPERADMIN_USERNAME]
        remove_select = st.multiselect("Selecione usuários para remover:", options=candidates)
        can_remove, cannot_remove = [], []
        if st.button("Remover selecionados", type="secondary"):
            if not remove_select:
                st.warning("Nenhum usuário selecionado.")
            else:
                for uname in remove_select:
                    idx = df_users.index[df_users["username"] == uname][0]
                    role = df_users.loc[idx, "role"]
                    if uname == SUPERADMIN_USERNAME:
                        cannot_remove.append(uname)
                        continue
                    if role.lower() in ("admin", "superadmin") and not user_is_superadmin():
                        cannot_remove.append(uname)
                        continue
                    can_remove.append(uname)
                if can_remove:
                    df_users = df_users[~df_users["username"].isin(can_remove)]
                    save_user_db(df_users)
                    st.success(f"Removidos: {', '.join(can_remove)}")
                    if cannot_remove:
                        st.warning(f"Não permitido remover: {', '.join(cannot_remove)}")
                    st.rerun()
                else:
                    st.warning("Nenhum usuário pôde ser removido pelas regras de proteção.")

    # =========================
    # TELA SLA MENSAL (calc_simples)
    # =========================
    elif st.session_state.tela == "calc_simples":
        st.title("🖩 SLA Mensal")

        df_base = carregar_base()
        mensalidade = 0.0
        cliente = ""
        placa = ""

        with st.expander("🔍 Consultar Clientes e Placas"):
            if df_base is not None and not df_base.empty:
                df_display = df_base[['CLIENTE', 'PLACA', 'VALOR MENSALIDADE']].copy()
                df_display['VALOR MENSALIDADE'] = df_display['VALOR MENSALIDADE'].apply(formatar_moeda)
                st.dataframe(df_display, use_container_width=True, hide_index=True)
            else:
                st.info("Base De Clientes Faturamento.xlsx não encontrada. Você poderá digitar os dados manualmente.")

        col_left, col_right = st.columns([2, 1])

        with col_left:
            st.subheader("1) Identificação")
            placa_in = st.text_input("Placa do veículo (digite e tecle Enter)", key="placa_simples").strip().upper()
            if placa_in and df_base is not None and not df_base.empty:
                hit = df_base[df_base["PLACA"].astype(str).str.upper() == placa_in]
                if not hit.empty:
                    placa = placa_in
                    cliente = str(hit.iloc[0]["CLIENTE"])
                    mensalidade = moeda_para_float(hit.iloc[0]["VALOR MENSALIDADE"])
                    st.success(f"Cliente: {cliente} | Mensalidade: {formatar_moeda(mensalidade)}")
                else:
                    st.warning("Placa não encontrada na base. Preencha os dados manualmente abaixo.")

            cliente = st.text_input("Cliente (caso não tenha sido localizado)", value=cliente)
            mensalidade = st.number_input("Mensalidade (R$)", min_value=0.0, step=0.01, format="%.2f",
                                          value=float(mensalidade) if mensalidade else 0.0)

            st.subheader("2) Período e Serviço")
            c1, c2 = st.columns(2)
            data_entrada = c1.date_input("Data de entrada", datetime.now())
            data_saida = c2.date_input("Data de saída", datetime.now() + timedelta(days=3))
            feriados = c1.number_input("Feriados no período", min_value=0, step=1, value=0)

            tipo_servico = c2.selectbox("Tipo de serviço (SLA)", [
                "Preventiva – 2 dias úteis",
                "Corretiva – 3 dias úteis",
                "Preventiva + Corretiva – 5 dias úteis",
                "Motor – 15 dias úteis"
            ])
            sla_map = {
                "Preventiva – 2 dias úteis": 2,
                "Corretiva – 3 dias úteis": 3,
                "Preventiva + Corretiva – 5 dias úteis": 5,
                "Motor – 15 dias úteis": 15
            }
            prazo_sla = sla_map.get(tipo_servico, 0)

            st.markdown("---")
            calc = st.button("Calcular SLA", type="primary")

            if calc:
                if not placa_in and not cliente:
                    st.error("Informe ao menos a placa ou o cliente.")
                elif data_entrada >= data_saida:
                    st.error("A data de saída deve ser posterior à data de entrada.")
                elif mensalidade <= 0:
                    st.error("Informe um valor de mensalidade válido.")
                else:
                    dias_uteis_manut, status, desconto, dias_exc = calcular_sla_simples(
                        data_entrada, data_saida, prazo_sla, mensalidade, feriados
                    )
                    st.session_state.resultado_sla = {
                        "cliente": cliente or "-",
                        "placa": placa_in or "-",
                        "tipo_servico": tipo_servico,
                        "dias_uteis_manut": int(dias_uteis_manut),
                        "prazo_sla": int(prazo_sla),
                        "dias_excedente": int(dias_exc),
                        "mensalidade": float(mensalidade),
                        "desconto": float(desconto),
                        "status": status
                    }
                    st.success("Cálculo realizado com sucesso!")

        with col_right:
            st.subheader("Resultado")
            res = st.session_state.get("resultado_sla")
            if not res:
                st.info("Preencha os dados à esquerda e clique em 'Calcular SLA'.")
            else:
                st.write(f"- Status: {res['status']}")
                st.write(f"- Dias úteis da manutenção: {res['dias_uteis_manut']} dia(s)")
                st.write(f"- Prazo SLA: {res['prazo_sla']} dia(s)")
                st.write(f"- Dias excedidos: {res['dias_excedente']} dia(s)")
                st.write(f"- Mensalidade: {formatar_moeda(res['mensalidade'])}")
                st.write(f"- Desconto: {formatar_moeda(res['desconto'])}")

                pdf_buf = gerar_pdf_sla_simples(
                    res["cliente"], res["placa"], res["tipo_servico"],
                    res["dias_uteis_manut"], res["prazo_sla"], res["dias_excedente"],
                    res["mensalidade"], res["desconto"]
                )
                st.download_button(
                    "📥 Baixar PDF do Resultado",
                    data=pdf_buf,
                    file_name=f"sla_{res['placa'] or 'veiculo'}.pdf",
                    mime="application/pdf"
                )

                if st.button("Limpar resultado"):
                    limpar_dados_simples()
                    st.rerun()

    elif st.session_state.tela == "calc_comparativa":
        st.title("📊 Calculadora Comparativa de Cenários")
        if "cenarios" not in st.session_state:
            st.session_state.cenarios = []
        if "pecas_atuais" not in st.session_state:
            st.session_state.pecas_atuais = []
        if "mostrar_comparativo" not in st.session_state:
            st.session_state.mostrar_comparativo = False

        df_base = carregar_base()
        if df_base is None:
            st.error("❌ Arquivo 'Base De Clientes Faturamento.xlsx' não encontrado.")
            st.stop()

        if st.session_state.cenarios:
            st.markdown("---")
            st.header("📈 Cenários Calculados")
            df_cenarios = pd.DataFrame(st.session_state.cenarios)
            st.table(df_cenarios.drop(columns=["Detalhe Peças"]))
            if len(st.session_state.cenarios) >= 2 and not st.session_state.mostrar_comparativo:
                if st.button("🏆 Comparar Cenários", type="primary"):
                    st.session_state.mostrar_comparativo = True
                    st.rerun()

        if st.session_state.mostrar_comparativo:
            st.header("Análise Comparativa Final")
            df_cenarios = pd.DataFrame(st.session_state.cenarios)
            melhor = df_cenarios.loc[df_cenarios["Total Final (R$)"].apply(moeda_para_float).idxmin()]
            st.success(f"🏆 Melhor cenário: {melhor['Serviço']} | Placa {melhor['Placa']} | Total Final: {melhor['Total Final (R$)']}")
            pdf_buffer = gerar_pdf_comparativo(df_cenarios, melhor)
            st.download_button("📥 Baixar Relatório PDF", pdf_buffer, "comparacao_cenarios_sla.pdf", "application/pdf")
            st.button("🔄 Reiniciar Comparação", on_click=limpar_dados_comparativos, use_container_width=True, type="primary")
        else:
            st.markdown("---")
            st.header(f"📝 Preencher Dados para o Cenário {len(st.session_state.cenarios) + 1}")

            with st.expander("🔍 Consultar Clientes e Placas"):
                df_display = df_base[['CLIENTE', 'PLACA', 'VALOR MENSALIDADE']].copy()
                df_display['VALOR MENSALIDADE'] = df_display['VALOR MENSALIDADE'].apply(formatar_moeda)
                st.dataframe(df_display, use_container_width=True, hide_index=True)

            col_form, col_pecas = st.columns([2, 1])
            with col_form:
                placa = st.text_input("1. Digite a placa e tecle Enter")
                cliente_info = None
                if placa:
                    placa_upper = placa.strip().upper()
                    cliente_row = df_base[df_base["PLACA"].astype(str).str.upper() == placa_upper]
                    if not cliente_row.empty:
                        cliente_info = {
                            "cliente": cliente_row.iloc[0]["CLIENTE"],
                            "mensalidade": moeda_para_float(cliente_row.iloc[0]["VALOR MENSALIDADE"])
                        }
                        st.info(f"✅ Cliente: {cliente_info['cliente']} | Mensalidade: {formatar_moeda(cliente_info['mensalidade'])}")
                    else:
                        st.warning("❌ Placa não encontrada.")

                with st.form(key=f"form_cenario_{len(st.session_state.cenarios)}", clear_on_submit=True):
                    st.subheader("2. Detalhes do Serviço")
                    subcol1, subcol2 = st.columns(2)
                    entrada = subcol1.date_input("📅 Data de entrada:", datetime.now())
                    saida = subcol2.date_input("📅 Data de saída:", datetime.now() + timedelta(days=5))
                    feriados = subcol1.number_input("📌 Feriados no período:", min_value=0, step=1)
                    servico = subcol2.selectbox("🛠️ Tipo de serviço:", [
                        "Preventiva – 2 dias úteis", "Corretiva – 3 dias úteis",
                        "Preventiva + Corretiva – 5 dias úteis", "Motor – 15 dias úteis"
                    ])
                    with st.expander("Verificar Peças Adicionadas"):
                        if st.session_state.pecas_atuais:
                            for peca in st.session_state.pecas_atuais:
                                c1, c2 = st.columns([3, 1])
                                c1.write(peca['nome'])
                                c2.write(formatar_moeda(peca['valor']))
                        else:
                            st.info("Nenhuma peça adicionada na coluna da direita.")

                    submitted = st.form_submit_button(
                        f"➡️ Calcular Cenário {len(st.session_state.cenarios) + 1}",
                        use_container_width=True, type="primary"
                    )
                    if submitted:
                        if not cliente_info:
                            st.error("Placa inválida ou não encontrada para submeter.")
                        elif entrada >= saida:
                            st.error("A data de saída deve ser posterior à de entrada.")
                        else:
                            cenario = calcular_cenario_comparativo(
                                cliente_info["cliente"], placa.upper(), entrada, saida,
                                feriados, servico, st.session_state.pecas_atuais, cliente_info["mensalidade"]
                            )
                            st.session_state.cenarios.append(cenario)
                            st.session_state.pecas_atuais = []
                            st.rerun()

            with col_pecas:
                st.subheader("3. Gerenciar Peças")
                nome_peca = st.text_input("Nome da Peça", key="nome_peca_input")
                valor_peca = st.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f", key="valor_peca_input")
                if st.button("➕ Adicionar Peça", use_container_width=True):
                    if nome_peca and valor_peca > 0:
                        st.session_state.pecas_atuais.append({"nome": nome_peca, "valor": float(valor_peca)})
                        st.rerun()
                    else:
                        st.warning("Preencha o nome e o valor da peça.")
                if st.session_state.pecas_atuais:
                    st.markdown("---")
                    st.write("Peças adicionadas:")
                    opcoes_pecas = [f"{p['nome']} - {formatar_moeda(p['valor'])}" for p in st.session_state.pecas_atuais]
                    pecas_para_remover = st.multiselect("Selecione para remover:", options=opcoes_pecas)
                    if st.button("🗑️ Remover Selecionadas", type="secondary", use_container_width=True):
                        if pecas_para_remover:
                            nomes_para_remover = [item.split(' - ')[0] for item in pecas_para_remover]
                            st.session_state.pecas_atuais = [p for p in st.session_state.pecas_atuais if p['nome'] not in nomes_para_remover]
                            st.rerun()
                        else:
                            st.warning("Nenhuma peça foi selecionada.")

    st.markdown("</div>", unsafe_allow_html=True)

# Fim do arquivo
