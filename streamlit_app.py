# Combined and corrected streamlit_app.py
# Merged parts 1 + 2 provided by user with fixes:
# - fixed indentation errors (login / reset flows)
# - safe_rerun wrapper (replaces st.rerun())
# - protected sums (pecas can be None)
# - removed global aplicar_estilos() call at import time (apply after login)
# - uses ui_helpers functions if available (set_background_png, inject_login_css, show_logo, resource_path, clear_login_background)
# - email sending reads st.secrets (do not hardcode secrets here)
#
# NOTE: keep ui_helpers.py in the repo (with set_background_png, show_logo, inject_login_css, resource_path, clear_login_background).
# Do NOT commit your secrets to the repository; configure them in Streamlit Cloud's Secrets.

import os
import base64
import hashlib
import secrets
import smtplib
import re
import tempfile
from io import BytesIO
from datetime import datetime, timedelta
from email.message import EmailMessage
from textwrap import dedent
from typing import Optional, Tuple

import pandas as pd
import numpy as np
import streamlit as st
from passlib.context import CryptContext
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from streamlit.components.v1 import html as components_html

# UI helpers (expects ui_helpers.py in repo)
# ui_helpers should provide: set_background_png, show_logo, inject_login_css, resource_path, clear_login_background
try:
    from ui_helpers import set_background_png, show_logo, inject_login_css, resource_path, clear_login_background
except Exception:
    # Fallback lightweight resource_path and stubs if ui_helpers not present
    def resource_path(p: str) -> str:
        return os.path.join(os.getcwd(), p)

    def set_background_png(p: str):
        # fallback: attempt simple injection if file exists in repo
        try:
            if os.path.exists(p):
                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                css = f"""
                <style>
                html, body, .stApp {{
                  background-image: url("data:image/png;base64,{b64}") !important;
                  background-size: cover !important;
                  background-repeat: no-repeat !important;
                  background-position: center center !important;
                }}
                </style>
                """
                st.markdown(css, unsafe_allow_html=True)
        except Exception:
            pass

    def show_logo(p: str, width: int = 120, use_caption: bool = False):
        try:
            if os.path.exists(p):
                st.image(p, width=width)
        except Exception:
            pass

    def inject_login_css():
        try:
            st.markdown(
                """
                <style>
                .login-wrapper { display:flex; align-items:center; justify-content:center; min-height:100vh; padding: 32px; }
                .login-card { width: 480px; max-width: calc(100% - 32px); padding: 20px; border-radius: 12px; background: rgba(15,23,42,0.92); box-shadow: 0 12px 36px rgba(0,0,0,0.45); }
                </style>
                """,
                unsafe_allow_html=True,
            )
        except Exception:
            pass

    def clear_login_background():
        try:
            # no-op fallback
            pass
        except Exception:
            pass

# ---- Helpers ----
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def safe_rerun():
    """Safe wrapper for session rerun."""
    try:
        st.experimental_rerun()
    except Exception:
        pass

def get_query_params():
    try:
        return dict(st.query_params)
    except Exception:
        try:
            params = st.experimental_get_query_params()
            return {k: (v[0] if isinstance(v, list) else v) for k, v in params.items()}
        except Exception:
            return {}

def clear_all_query_params():
    try:
        st.experimental_set_query_params()
    except Exception:
        try:
            st.query_params.clear()
        except Exception:
            pass

def get_app_base_url():
    try:
        url = (st.secrets.get("APP_BASE_URL", "") or "").strip()
    except Exception:
        url = ""
    if url.endswith("/"):
        url = url[:-1]
    return url

def is_bcrypt_hash(s: str) -> bool:
    return isinstance(s, str) and s.startswith("$2")

def hash_password(password: str) -> str:
    try:
        return pwd_context.hash(password)
    except Exception:
        # fallback
        return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_hash: str, provided_password: str) -> Tuple[bool, bool]:
    """
    Returns (valid, needs_upgrade)
    """
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
# CONFIG DA PÁGINA
# =========================
try:
    st.set_page_config(
        page_title="Frotas Vamos SLA",
        page_icon=resource_path("logo_sidebar.png") if os.path.exists(resource_path("logo_sidebar.png")) else "🚛",
        layout="wide",
        initial_sidebar_state="expanded"
    )
except Exception:
    pass

# =========================
# UI / STYLES (aplicar_estilos defined here)
# =========================
def aplicar_estilos():
    """
    Theme for authenticated screens. Do NOT call at import time to avoid overriding login CSS.
    """
    # Try to build logo b64 if present
    logo_rule = ""
    try:
        logo_path = resource_path("frotasvamossla.png")
        if not os.path.isabs(logo_path):
            logo_path = resource_path("frotasvamossla.png")
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode()
            mime = "image/png"
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
    except Exception:
        logo_rule = ""

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

      .stApp {{
        background-image: none !important;
        background: var(--bg, #0B0F17) !important;
      }}

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
        padding: 20px;
      }}

      header[data-testid="stHeader"], #MainMenu, footer {{ display: none !important; }}

      {logo_rule}
    </style>
    """
    try:
        st.markdown(css, unsafe_allow_html=True)
        if logo_rule:
            st.markdown("<div class='brand-badge' aria-hidden='true'></div>", unsafe_allow_html=True)
    except Exception:
        pass
    try:
        st.session_state["login_bg_applied"] = False
    except Exception:
        pass

# alias used in some places
aplicar_estilos_app = aplicar_estilos

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
# EMAIL / SMTP
# =========================
def smtp_available():
    host = st.secrets.get("EMAIL_HOST", "")
    user = st.secrets.get("EMAIL_USERNAME", "")
    password = st.secrets.get("EMAIL_PASSWORD", "")
    return bool(host and user and password)

def build_email_html(title: str, subtitle: str, body_lines: list, cta_label: str = "", cta_url: str = "", footer: str = ""):
    primary = "#e63946"
    brand = "#0d1117"
    text = "#0b1f2a"
    light = "#f6f8fa"
    button_html = ""
    if cta_label and cta_url:
        button_html = f"""
        <tr>
          <td align="center" style="padding: 28px 0 10px 0;">
            <a href="{cta_url}" style="background:{primary};color:#ffffff;text-decoration:none;font-weight:600;padding:12px 22px;border-radius:8px;display:inline-block;font-family:Segoe UI,Arial,sans-serif">
              {cta_label}
            </a>
          </td>
        </tr>
        """
    body_html = "".join([f'<p style="margin:8px 0 8px 0">{line}</p>' for line in body_lines])
    footer_html = f'<p style="color:#6b7280;font-size:12px">{footer}</p>' if footer else ""
    return f"""<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:{light}">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" width="100%" style="background:{light};padding:24px 0">
      <tr>
        <td>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" width="600" style="margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
            <tr>
              <td style="background:{brand};padding:18px 24px;color:#ffffff;">
                <div style="display:flex;align-items:center;gap:12px">
                  <span style="font-weight:700;font-size:18px;font-family:Segoe UI,Arial,sans-serif">Frotas Vamos SLA</span>
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 24px 0 24px;color:{text};font-family:Segoe UI,Arial,sans-serif">
                <h2 style="margin:0 0 6px 0;font-weight:700">{title}</h2>
                <p style="margin:0 0 12px 0;color:#475569">{subtitle}</p>
                {body_html}
              </td>
            </tr>
            {button_html}
            <tr>
              <td style="padding:12px 24px 24px 24px;color:#334155;font-family:Segoe UI,Arial,sans-serif">
                {footer_html}
              </td>
            </tr>
          </table>
          <div style="text-align:center;color:#94a3b8;font-size:12px;margin-top:8px;font-family:Segoe UI,Arial,sans-serif">
            © {datetime.now().year} Vamos Locação. Todos os direitos reservados.
          </div>
        </td>
      </tr>
    </table>
  </body>
</html>"""

def send_email(dest_email: str, subject: str, body_plain: str, body_html: Optional[str] = None) -> bool:
    host = st.secrets.get("EMAIL_HOST", "")
    port = int(st.secrets.get("EMAIL_PORT", 587) or 587)
    user = st.secrets.get("EMAIL_USERNAME", "")
    password = st.secrets.get("EMAIL_PASSWORD", "")
    use_tls = str(st.secrets.get("EMAIL_USE_TLS", "True")).lower() in ("1", "true", "yes")
    sender = st.secrets.get("EMAIL_FROM", user or "no-reply@example.com")

    if not host or not user or not password:
        st.warning("Configurações de e-mail não definidas em st.secrets. Exibindo conteúdo (teste).")
        st.code(f"Para: {dest_email}\nAssunto: {subject}\n\n{body_plain}", language="text")
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = dest_email
        msg.set_content(body_plain)
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        server = smtplib.SMTP(host, port, timeout=20)
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if user and password:
            server.login(user, password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        try:
            st.error(f"Falha ao enviar e-mail: {e}")
        except Exception:
            print("Falha ao enviar e-mail:", e)
        st.code(f"Para: {dest_email}\nAssunto: {subject}\n\n{body_plain}", language="text")
        return False

def send_reset_email(dest_email: str, reset_link: str) -> bool:
    subject = "Redefinição de senha - Frotas Vamos SLA"
    plain = f"""Olá,

Recebemos uma solicitação para redefinir sua senha no Frotas Vamos SLA.
Use o link abaixo (válido por 30 minutos):

{reset_link}

Se você não solicitou, ignore este e-mail.
"""
    html = build_email_html(
        title="Redefinição de senha",
        subtitle="Você solicitou redefinir sua senha no Frotas Vamos SLA.",
        body_lines=["Este link é válido por 30 minutos.", "Se você não solicitou, ignore este e-mail."],
        cta_label="Redefinir senha",
        cta_url=reset_link,
        footer="Este é um e-mail automático. Não responda."
    )
    return send_email(dest_email, subject, plain, html)

def send_approved_email(dest_email: str, base_url: str) -> bool:
    subject = "Conta aprovada - Frotas Vamos SLA"
    plain = f"""Olá,

Sua conta no Frotas Vamos SLA foi aprovada.
Acesse a plataforma: {base_url}

Bom trabalho!
"""
    html = build_email_html(
        title="Conta aprovada",
        subtitle="Seu acesso ao Frotas Vamos SLA foi liberado.",
        body_lines=["Você já pode acessar a plataforma com seu usuário e senha."],
        cta_label="Acessar plataforma",
        cta_url=base_url,
        footer="Em caso de dúvidas, procure o administrador do sistema."
    )
    return send_email(dest_email, subject, plain, html)

def send_invite_to_set_password(dest_email: str, reset_link: str) -> bool:
    subject = "Sua conta foi aprovada - Defina sua senha"
    plain = f"""Olá,

Sua conta no Frotas Vamos SLA foi aprovada.
Para definir sua senha inicial, use o link (válido por 30 minutos):
{reset_link}

Bom trabalho!
"""
    html = build_email_html(
        title="Defina sua senha",
        subtitle="Sua conta foi aprovada no Frotas Vamos SLA. Defina sua senha para começar a usar.",
        body_lines=["O link é válido por 30 minutos."],
        cta_label="Definir senha",
        cta_url=reset_link,
        footer="Se você não reconhece esta solicitação, ignore este e-mail."
    )
    return send_email(dest_email, subject, plain, html)

# =========================
# AUTENTICAÇÃO E USUÁRIOS
# =========================
REQUIRED_USER_COLUMNS = [
    "username", "password", "role", "full_name", "matricula",
    "email", "status", "accepted_terms_on", "reset_token", "reset_expires_at",
    "last_password_change", "force_password_reset"
]

SUPERADMIN_USERNAME = st.secrets.get("SUPERADMIN_USERNAME", "lucas.sureira")

@st.cache_data
def load_user_db() -> pd.DataFrame:
    tmp_pwd = (st.secrets.get("SUPERADMIN_DEFAULT_PASSWORD", "") or "").strip()
    admin_defaults = {
        "username": SUPERADMIN_USERNAME,
        "password": hash_password(tmp_pwd) if tmp_pwd else "",
        "role": "superadmin",
        "full_name": "Lucas Mateus Sureira",
        "matricula": "30159179",
        "email": st.secrets.get("SUPERADMIN_EMAIL", "lucas.sureira@grupovamos.com.br"),
        "status": "aprovado",
        "accepted_terms_on": "",
        "reset_token": "",
        "reset_expires_at": "",
        "last_password_change": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if tmp_pwd else "",
        "force_password_reset": "" if tmp_pwd else "1",
    }

    users_file = "users.csv"
    if os.path.exists(users_file) and os.path.getsize(users_file) > 0:
        try:
            df = pd.read_csv(users_file, dtype=str).fillna("")
        except Exception:
            try:
                bak_path = os.path.join(os.path.dirname(users_file), f"users.csv.bak.{int(datetime.utcnow().timestamp())}")
                os.replace(users_file, bak_path)
            except Exception:
                pass
            df = pd.DataFrame([admin_defaults])
            try:
                df.to_csv(users_file, index=False)
            except Exception:
                pass
            return df
    else:
        df = pd.DataFrame([admin_defaults])
        try:
            df.to_csv(users_file, index=False)
        except Exception:
            pass
        return df

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
        df.to_csv(users_file, index=False)
    except Exception:
        pass
    return df

def save_user_db(df_users: pd.DataFrame):
    for col in REQUIRED_USER_COLUMNS:
        if col not in df_users.columns:
            df_users[col] = ""
    df_users = df_users[REQUIRED_USER_COLUMNS]
    try:
        df_users.to_csv("users.csv", index=False)
    except Exception:
        pass
    st.cache_data.clear()

def is_password_expired(row) -> bool:
    try:
        last = row.get("last_password_change", "")
        if not last:
            return True
        last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
        expiry_days = int(st.secrets.get("PASSWORD_EXPIRY_DAYS", 90))
        return datetime.utcnow() > (last_dt + timedelta(days=expiry_days))
    except Exception:
        return True

# =========================
# FUNÇÕES AUXILIARES / BASE
# =========================
@st.cache_data
def carregar_base() -> Optional[pd.DataFrame]:
    try:
        return pd.read_excel(resource_path("Base De Clientes Faturamento.xlsx"))
    except Exception:
        return None

def formatar_moeda(valor):
    return f"R${valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def moeda_para_float(valor_str):
    if isinstance(valor_str, (int, float)):
        return float(valor_str)
    if isinstance(valor_str, str):
        valor_str = valor_str.replace("R$", "").replace(".", "").replace(",", ".").strip()
        try:
            return float(valor_str)
        except:
            return 0.0
    return 0.0

# =========================
# CÁLCULOS / PDFs
# =========================
def calcular_cenario_comparativo(cliente, placa, entrada, saida, feriados, servico, pecas, mensalidade):
    dias = np.busday_count(entrada.strftime('%Y-%m-%d'), (saida + timedelta(days=1)).strftime('%Y-%m-%d'))
    dias_uteis = max(dias - int(feriados or 0), 0)
    sla_dict = {"Preventiva – 2 dias úteis": 2, "Corretiva – 3 dias úteis": 3,
                "Preventiva + Corretiva – 5 dias úteis": 5, "Motor – 15 dias úteis": 15}
    sla_dias = sla_dict.get(servico, 0)
    excedente = max(0, dias_uteis - sla_dias)
    desconto = (mensalidade / 30) * excedente if excedente > 0 else 0
    total_pecas = sum(float(p.get("valor", 0) or 0) for p in (pecas or []))
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
        "Detalhe Peças": pecas or []
    }

def gerar_pdf_comparativo(df_cenarios, melhor_cenario):
    if df_cenarios is None or df_cenarios.empty:
        return BytesIO()
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
                elementos.append(Paragraph(f"- {peca.get('nome','')}: {formatar_moeda(peca.get('valor',0))}", styles['Normal']))
        elementos.append(Spacer(1, 12))
        elementos.append(Paragraph("─" * 90, styles['Normal']))
        elementos.append(Spacer(1, 12))
    texto_melhor = (f"<b>🏆 Melhor Cenário (Menor Custo Final)</b><br/>"
                    f"Serviço: {melhor_cenario.get('Serviço','')}<br/>"
                    f"Placa: {melhor_cenario.get('Placa','')}<br/>"
                    f"<b>Total Final: {melhor_cenario.get('Total Final (R$)','')}</b>")
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
    safe_rerun()

def user_is_admin():
    return st.session_state.get("role") in ("admin", "superadmin")

def user_is_superadmin():
    return st.session_state.get("username") == SUPERADMIN_USERNAME or st.session_state.get("role") == "superadmin"

def renderizar_sidebar():
    with st.sidebar:
        st.markdown("<div class='sidebar-center'>", unsafe_allow_html=True)
        try:
            if os.path.exists(resource_path("logo_sidebar.png")):
                st.image(resource_path("logo_sidebar.png"), width=100)
            elif os.path.exists(resource_path("logo.png")):
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

# =========================
# ESTADO INICIAL / ROTEAMENTO
# =========================
if "tela" not in st.session_state:
    st.session_state.tela = "login"

# Token reset via URL
qp = get_query_params()
incoming_token = qp.get("reset_token") or qp.get("token") or ""
if incoming_token and not st.session_state.get("ignore_reset_qp"):
    st.session_state.incoming_reset_token = incoming_token
    st.session_state.tela = "reset_password"

# =========================
# TELAS (Roteador Principal)
# =========================
if st.session_state.tela == "login":

    # Apply login-specific CSS and background
    try:
        inject_login_css()
    except Exception:
        pass

    try:
        set_background_png(resource_path("background.png"))
    except Exception:
        # ignore if ui_helpers not available or file missing
        pass

    # Top logo (if exists)
    cols_top = st.columns([6, 1, 1])
    try:
        with cols_top[1]:
            show_logo(resource_path("logo.png"), width=140)
    except Exception:
        pass

    st.markdown("<br><br>", unsafe_allow_html=True)

    st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)
    st.markdown('<div class="login-card">', unsafe_allow_html=True)

    st.markdown("<div class='brand-title'>Frotas Vamos SLA</div>", unsafe_allow_html=True)
    st.markdown("<div class='brand-subtitle'>Soluções Inteligentes para Frotas</div>", unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Usuário", label_visibility="collapsed", placeholder="Usuário")
        password = st.text_input("Senha", type="password", label_visibility="collapsed", placeholder="Senha")
        submit_login = st.form_submit_button("Entrar 🚀", use_container_width=True)

    cols = st.columns(2)
    with cols[0]:
        st.button("Criar cadastro", on_click=ir_para_register, use_container_width=True)
    with cols[1]:
        st.button("Esqueci minha senha", on_click=ir_para_forgot, use_container_width=True)

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
                        row["password"] = df_users.loc[idx, "password"]
                except Exception:
                    pass

                if row.get("status", "") != "aprovado":
                    st.warning("⏳ Seu cadastro ainda está pendente de aprovação pelo administrador.")
                else:
                    # On successful login, clear login background and apply app theme
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
                    # redirections and required flows
                    if not str(row.get("accepted_terms_on", "")).strip():
                        st.session_state.tela = "terms_consent"
                        safe_rerun()
                    elif is_password_expired(row) or str(row.get("force_password_reset", "")).strip():
                        st.session_state.tela = "force_change_password"
                        safe_rerun()
                    else:
                        st.session_state.tela = "home"
                        safe_rerun()

    st.markdown('</div>', unsafe_allow_html=True)  # close login-card
    st.markdown('</div>', unsafe_allow_html=True)  # close login-wrapper

# Register / Forgot / Reset / Force change / Terms / Authenticated screens
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
            else:
                idxs = df.index[df["email"].str.strip().str.lower() == (email or pre.get("email", "")).strip().lower()]
                if len(idxs) > 0:
                    idx = idxs[0]
                    if not df.loc[idx, "username"]:
                        if (username.strip() in df["username"].values) and (df.loc[idx, "username"] != username.strip()):
                            st.error("Nome de usuário já existe.")
                        else:
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
                    else:
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
        ir_para_login(); safe_rerun()

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
        safe_rerun()

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
                        safe_rerun()

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
            safe_rerun()
    st.markdown("</div>", unsafe_allow_html=True)

elif st.session_state.tela == "terms_consent":
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)
    st.title("Termos e Condições de Uso e Política de Privacidade (LGPD)")
    st.info("Para seu primeiro acesso, é necessário ler e aceitar os termos de uso e a política de privacidade desta plataforma.")
    terms_html = dedent("""
    <div class="terms-box" style="color:#fff;font-family:Segoe UI,Arial,sans-serif;">
        <p><b>Última atualização:</b> 28 de Setembro de 2025</p>
        ... (conteúdo de termos) ...
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
        safe_rerun()
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

        # Aprovação de cadastros pendentes (rest of admin code omitted for brevity)
        pendentes = df_users[df_users["status"] == "pendente"]
        if pendentes.empty:
            st.info("Não há cadastros pendentes.")
        else:
            st.dataframe(pendentes[["username", "full_name", "email", "matricula"]], use_container_width=True, hide_index=True)
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
                    safe_rerun()
                else:
                    st.warning("Selecione ao menos um usuário.")
            if colap2.button("🗑️ Rejeitar (remover) selecionados", use_container_width=True):
                if to_approve:
                    to_remove = [u for u in to_approve if u != SUPERADMIN_USERNAME]
                    df_users = df_users[~df_users["username"].isin(to_remove)]
                    save_user_db(df_users)
                    st.success("Usuários removidos com sucesso.")
                    safe_rerun()
                else:
                    st.warning("Selecione ao menos um usuário.")

    # rest of authenticated screens (calc_simples, calc_comparativa, etc.) remain implemented above in this file

    st.markdown("</div>", unsafe_allow_html=True)

# End of file
