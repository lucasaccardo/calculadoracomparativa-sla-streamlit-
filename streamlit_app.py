import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
import hashlib
import os
import base64
import secrets
import smtplib
from email.message import EmailMessage

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Calculadora SLA | Vamos",
    page_icon="logo_sidebar.png" if os.path.exists("logo_sidebar.png") else "🚛",
    layout="wide",
    initial_sidebar_state="auto"
)

# --- UTILS QUERY PARAMS ---
def get_query_params():
    try:
        return dict(st.query_params)
    except Exception:
        return {k: v[0] if isinstance(v, list) else v for k, v in st.experimental_get_query_params().items()}

def get_app_base_url():
    url = (st.secrets.get("APP_BASE_URL", "") or "").strip()
    if url.endswith("/"):
        url = url[:-1]
    return url

# --- EMAIL / SMTP HELPERS ---
def smtp_available():
    host = st.secrets.get("EMAIL_HOST", "")
    user = st.secrets.get("EMAIL_USERNAME", "")
    password = st.secrets.get("EMAIL_PASSWORD", "")
    return bool(host and user and password)

def send_email(dest_email: str, subject: str, body: str):
    host = st.secrets.get("EMAIL_HOST", "")
    port = int(st.secrets.get("EMAIL_PORT", 587))
    user = st.secrets.get("EMAIL_USERNAME", "")
    password = st.secrets.get("EMAIL_PASSWORD", "")
    use_tls = bool(st.secrets.get("EMAIL_USE_TLS", True))
    sender = st.secrets.get("EMAIL_FROM", user or "no-reply@example.com")

    if not host or not user or not password:
        st.warning("Configurações de e-mail não definidas em st.secrets. Exibindo conteúdo do e-mail abaixo (teste).")
        st.code(f"Para: {dest_email}\nAssunto: {subject}\n\n{body}", language="text")
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = dest_email
        msg.set_content(body)
        server = smtplib.SMTP(host, port, timeout=20)
        if use_tls:
            server.starttls()
        server.login(user, password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Falha ao enviar e-mail: {e}")
        st.code(f"Para: {dest_email}\nAssunto: {subject}\n\n{body}", language="text")
        return False

def send_reset_email(dest_email: str, reset_link: str):
    subject = "Redefinição de senha - Vamos Fleet SLA"
    body = f"""Olá,

Recebemos uma solicitação para redefinição de senha da sua conta no Vamos Fleet SLA.

Para redefinir sua senha, acesse o link abaixo (válido por 30 minutos):
{reset_link}

Se você não solicitou, ignore este e-mail.

Atenciosamente,
Equipe Vamos
"""
    return send_email(dest_email, subject, body)

def send_approved_email(dest_email: str, base_url: str):
    subject = "Conta aprovada - Vamos Fleet SLA"
    body = f"""Olá,

Sua conta no Vamos Fleet SLA foi aprovada pelo administrador.

Você já pode acessar: {base_url}

Atenciosamente,
Equipe Vamos
"""
    return send_email(dest_email, subject, body)

def send_invite_to_set_password(dest_email: str, reset_link: str):
    subject = "Sua conta foi aprovada - Defina sua senha"
    body = f"""Olá,

Sua conta no Vamos Fleet SLA foi aprovada.
Para definir sua senha e começar a usar, acesse (válido por 30 minutos):
{reset_link}

Atenciosamente,
Equipe Vamos
"""
    return send_email(dest_email, subject, body)

# --- FUNÇÃO PARA APLICAR O FUNDO E CSS ---
def aplicar_estilos():
    try:
        with open("background.png", "rb") as f:
            data = f.read()
        bg_image_base64 = base64.b64encode(data).decode()
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-image: url(data:image/jpeg;base64,{bg_image_base64});
                background-size: cover;
                background-repeat: no-repeat;
                background-attachment: fixed;
            }}
            .main-container, [data-testid="stForm"] {{
                background-color: rgba(13, 17, 23, 0.85);
                padding: 25px;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            .main-container, .main-container * {{
                color: white !important;
            }}
            a, .as-link {{
                color: #91c9ff !important;
                text-decoration: underline !important;
                cursor: pointer;
            }}
            .terms-box {{
                max-height: 65vh;
                overflow-y: auto;
                padding: 18px 20px;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 10px;
                margin-top: 10px;
            }}
            .terms-box h3, .terms-box h4 {{
                margin-top: 1.2em;
                margin-bottom: 0.4em;
            }}
            .terms-box p, .terms-box li {{
                line-height: 1.5em;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )
    except FileNotFoundError:
        pass

# --- AUTENTICAÇÃO E USUÁRIOS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(hashed_password, user_password):
    return hashed_password == hash_password(user_password)

REQUIRED_USER_COLUMNS = [
    "username", "password", "role", "full_name", "matricula",
    "email", "status", "accepted_terms_on", "reset_token", "reset_expires_at"
]

@st.cache_data
def load_user_db():
    admin_username = "lucas.sureira"
    admin_defaults = {
        "username": admin_username,
        "password": hash_password("Brasil@@2609"),
        "role": "admin",
        "full_name": "Lucas Mateus Sureira",
        "matricula": "30159179",
        "email": "lucas.sureira@grupovamos.com.br",
        "status": "aprovado",
        "accepted_terms_on": "",
        "reset_token": "",
        "reset_expires_at": ""
    }

    if os.path.exists("users.csv") and os.path.getsize("users.csv") > 0:
        df = pd.read_csv("users.csv", dtype=str).fillna("")
    else:
        df = pd.DataFrame([admin_defaults])
        df.to_csv("users.csv", index=False)
        return df

    for col in REQUIRED_USER_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Garante admin principal
    if admin_username in df["username"].values:
        idx = df.index[df["username"] == admin_username][0]
        for k, v in admin_defaults.items():
            if k == "accepted_terms_on" and str(df.loc[idx, k]).strip():
                continue
            df.loc[idx, k] = v
    else:
        df = pd.concat([df, pd.DataFrame([admin_defaults])], ignore_index=True)

    df.to_csv("users.csv", index=False)
    return df

def save_user_db(df_users):
    for col in REQUIRED_USER_COLUMNS:
        if col not in df_users.columns:
            df_users[col] = ""
    df_users = df_users[REQUIRED_USER_COLUMNS]
    df_users.to_csv("users.csv", index=False)
    st.cache_data.clear()

# --- FUNÇÕES AUXILIARES COMUNS ---
@st.cache_data
def carregar_base():
    try:
        return pd.read_excel("Base De Clientes Faturamento.xlsx")
    except FileNotFoundError:
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

# --- FUNÇÕES DAS CALCULADORAS ---
def calcular_cenario_comparativo(cliente, placa, entrada, saida, feriados, servico, pecas, mensalidade):
    dias = np.busday_count(entrada.strftime('%Y-%m-%d'), (saida + timedelta(days=1)).strftime('%Y-%m-%d'))
    dias_uteis = max(dias - feriados, 0)
    sla_dict = {"Preventiva – 2 dias úteis": 2, "Corretiva – 3 dias úteis": 3,
                "Preventiva + Corretiva – 5 dias úteis": 5, "Motor – 15 dias úteis": 15}
    sla_dias = sla_dict.get(servico, 0)
    excedente = max(0, dias_uteis - sla_dias)
    desconto = (mensalidade / 30) * excedente if excedente > 0 else 0
    total_pecas = sum(p["valor"] for p in pecas)
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

def gerar_pdf_comparativo(df_cenarios, melhor_cenario):
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
        if row["Detalhe Peças"]:
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
    dias = np.busday_count(
        np.datetime64(to_date(data_entrada)),
        np.datetime64(to_date(data_saida + timedelta(days=1)))
    )
    dias -= feriados
    dias = max(dias, 0)
    if dias <= prazo_sla:
        status = "Dentro do prazo"
        desconto = 0
        dias_excedente = 0
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
        c.drawString(50, y, line)
        y -= 20
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- NAV STATE HELPERS ---
def ir_para_home(): st.session_state.tela = "home"
def ir_para_calc_comparativa(): st.session_state.tela = "calc_comparativa"
def ir_para_calc_simples(): st.session_state.tela = "calc_simples"
def ir_para_admin(): st.session_state.tela = "admin_users"
def ir_para_login(): st.session_state.tela = "login"
def ir_para_register(): st.session_state.tela = "register"
def ir_para_forgot(): st.session_state.tela = "forgot_password"
def ir_para_reset(): st.session_state.tela = "reset_password"

def limpar_dados_comparativos():
    for key in ["cenarios", "pecas_atuais", "mostrar_comparativo"]:
        if key in st.session_state: del st.session_state[key]

def limpar_dados_simples():
    for key in ["resultado_sla", "pesquisa_cliente"]:
        if key in st.session_state: del st.session_state[key]

def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]

def renderizar_sidebar():
    with st.sidebar:
        try:
            st.image("logo_sidebar.png", width=100)
        except:
            pass
        st.header("Menu de Navegação")
        if st.session_state.get("role") == "admin":
            st.button("👤 Gerenciar Usuários", on_click=ir_para_admin, use_container_width=True)
        st.button("🏠 Voltar para Home", on_click=ir_para_home, use_container_width=True)
        if st.session_state.tela == "calc_comparativa":
            st.button("🔄 Limpar Comparação", on_click=limpar_dados_comparativos, use_container_width=True)
        if st.session_state.tela == "calc_simples":
            st.button("🔄 Limpar Cálculo", on_click=limpar_dados_simples, use_container_width=True)
        st.button("🚪 Sair (Logout)", on_click=logout, use_container_width=True, type="secondary")

# --- ESTADO INICIAL ---
if "tela" not in st.session_state:
    st.session_state.tela = "login"

# Aplica estilos
aplicar_estilos()

# Detecta token de redefinição vindo por URL e direciona para tela de reset
qp = get_query_params()
incoming_token = qp.get("reset_token") or qp.get("token") or ""
if incoming_token:
    st.session_state.incoming_reset_token = incoming_token
    st.session_state.tela = "reset_password"

# --- TELAS ---
if st.session_state.tela == "login":
    # Linha no topo: logo no canto direito
    col1, col2, col3 = st.columns([6, 1, 1])
    with col3:
        try:
            st.image("fleetvamossla.png", width=120)
        except:
            pass

    st.markdown("<br><br><br><br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Usuário", label_visibility="collapsed", placeholder="Usuário")
            password = st.text_input("Senha", type="password", label_visibility="collapsed", placeholder="Senha")
            submit_login = st.form_submit_button("Entrar 🚀", use_container_width=True)

        # Links de ação
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
                if not check_password(row["password"], password):
                    st.error("❌ Usuário ou senha incorretos.")
                else:
                    if row.get("status", "") != "aprovado":
                        st.warning("⏳ Seu cadastro ainda está pendente de aprovação pelo administrador.")
                    else:
                        st.session_state.logado = True
                        st.session_state.username = row["username"]
                        st.session_state.role = row.get("role", "user")
                        # Termos LGPD
                        if pd.isna(row.get("accepted_terms_on", "")) or str(row.get("accepted_terms_on", "")).strip() == "":
                            st.session_state.tela = "terms_consent"
                        else:
                            st.session_state.tela = "home"
                        st.rerun()

elif st.session_state.tela == "register":
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)
    st.title("🆕 Criar cadastro")
    st.info("Se a sua empresa já realizou um pré-cadastro, informe seu e-mail para pré-preencher os dados.")
    # Passo 1: localizar pré-cadastro por e-mail
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

    # Regras de preenchimento/lock: se veio do admin, trava estes campos
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
        password = col5.text_input("Senha", type="password")
        password2 = col6.text_input("Confirmar senha", type="password")
        submit_reg = st.form_submit_button("Enviar cadastro", type="primary", use_container_width=True)

    st.button("⬅️ Voltar ao login", on_click=ir_para_login)

    if submit_reg:
        df = load_user_db()
        # Validações básicas
        if not all([(username or pre and pre.get("username")), (full_name or pre and pre.get("full_name")),
                    (email or pre and pre.get("email")), password.strip(), password2.strip()]):
            st.error("Preencha todos os campos obrigatórios.")
        elif password != password2:
            st.error("As senhas não conferem.")
        else:
            # Se existe pré-cadastro por e-mail, atualiza o registro existente
            idxs = df.index[df["email"].str.strip().str.lower() == (email or pre.get("email", "")).strip().lower()]
            if len(idxs) > 0:
                idx = idxs[0]
                # username: se admin já definiu, mantemos; senão, usa o informado
                if not df.loc[idx, "username"]:
                    # se username já existe em outro usuário, erro
                    if (username.strip() in df["username"].values) and (df.loc[idx, "username"] != username.strip()):
                        st.error("Nome de usuário já existe.")
                        st.stop()
                    df.loc[idx, "username"] = username.strip()
                # full_name e matricula: mantém admin se vierem, senão usa informado
                if not df.loc[idx, "full_name"]:
                    df.loc[idx, "full_name"] = full_name.strip()
                if not df.loc[idx, "matricula"]:
                    df.loc[idx, "matricula"] = matricula.strip()
                # sempre define/atualiza a senha
                df.loc[idx, "password"] = hash_password(password)
                # mantém status atual (pode estar pendente ou aprovado)
                if df.loc[idx, "status"] == "":
                    df.loc[idx, "status"] = "pendente"
                save_user_db(df)
                st.success("Cadastro atualizado! Aguarde aprovação do administrador (se ainda estiver pendente).")
            else:
                # Cadastro novo normal
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
                    "reset_expires_at": ""
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
    colb2.button("⬅️ Voltar ao login", on_click=ir_para_login, use_container_width=True)

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
    new_pass = colp1.text_input("Nova senha", type="password")
    new_pass2 = colp2.text_input("Confirmar nova senha", type="password")
    colb1, colb2 = st.columns(2)
    confirmar = colb1.button("Redefinir senha", type="primary", use_container_width=True)
    colb2.button("⬅️ Voltar ao login", on_click=ir_para_login, use_container_width=True)

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
                    df.loc[idx, "password"] = hash_password(new_pass)
                    df.loc[idx, "reset_token"] = ""
                    df.loc[idx, "reset_expires_at"] = ""
                    save_user_db(df)
                    st.success("Senha redefinida com sucesso! Faça login novamente.")
                    st.button("Ir para login", on_click=ir_para_login, type="primary")

elif st.session_state.tela == "terms_consent":
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)
    st.title("Termos e Condições de Uso e Política de Privacidade (LGPD)")
    st.info("Para seu primeiro acesso, é necessário ler e aceitar os termos de uso e a política de privacidade desta plataforma.")
    st.markdown("""
    <div class="terms-box">
        <p><b>Última atualização:</b> 28 de Setembro de 2025</p>

        <h3>1. Finalidade da Ferramenta</h3>
        <p>
            Esta plataforma é um sistema interno para simulação e referência de cálculos de
            Service Level Agreement (SLA) e apoio operacional. Os resultados são estimativas
            destinadas ao uso profissional e não substituem documentos contratuais, fiscais
            ou aprovados formalmente pela empresa.
        </p>

        <h3>2. Base Legal e Conformidade com a LGPD</h3>
        <p>
            O tratamento de dados pessoais nesta plataforma observa a Lei nº 13.709/2018
            (Lei Geral de Proteção de Dados Pessoais – LGPD), adotando medidas técnicas e
            administrativas para proteger os dados contra acessos não autorizados e situações
            acidentais ou ilícitas de destruição, perda, alteração, comunicação ou difusão.
        </p>

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
        <p>
            Os dados processados são de uso interno e não são compartilhados com terceiros,
            exceto quando necessários para cumprimento de obrigações legais ou ordem de
            autoridades competentes.
        </p>

        <h3>6. Segurança da Informação</h3>
        <ul>
            <li>Senhas armazenadas com algoritmo de hash (não reversível).</li>
            <li>Acesso restrito a usuários autorizados e administradores.</li>
            <li>Envio de e-mails mediante configurações autenticadas de SMTP corporativo.</li>
        </ul>

        <h3>7. Direitos dos Titulares</h3>
        <p>
            Nos termos da LGPD, o titular possui direitos como confirmação de tratamento,
            acesso, correção, anonimização, bloqueio, eliminação de dados desnecessários,
            portabilidade (quando aplicável) e informação sobre compartilhamentos.
        </p>

        <h3>8. Responsabilidades do Usuário</h3>
        <ul>
            <li>Manter a confidencialidade de suas credenciais de acesso.</li>
            <li>Utilizar a plataforma apenas para fins profissionais internos.</li>
            <li>Respeitar as políticas internas e as legislações aplicáveis.</li>
        </ul>

        <h3>9. Retenção e Eliminação</h3>
        <p>
            Os dados são mantidos pelo período necessário ao atendimento das finalidades
            acima e das políticas internas. Após esse período, poderão ser eliminados ou
            anonimizados, salvo obrigações legais de retenção.
        </p>

        <h3>10. Alterações dos Termos</h3>
        <p>
            Estes termos podem ser atualizados a qualquer tempo, mediante publicação
            de nova versão na própria plataforma. Recomenda-se a revisão periódica.
        </p>

        <h3>11. Contato</h3>
        <p>
            Em caso de dúvidas sobre estes Termos ou sobre o tratamento de dados pessoais,
            procure o time responsável pela ferramenta ou o canal corporativo de Privacidade/DPD.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    consent = st.checkbox("Eu li e concordo com os Termos e Condições.")
    if st.button("Continuar", disabled=not consent, type="primary"):
        df_users = load_user_db()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        username = st.session_state.get("username", "")
        if username:
            user_index = df_users.index[df_users['username'] == username]
            if len(user_index) > 0:
                df_users.loc[user_index[0], 'accepted_terms_on'] = now
                save_user_db(df_users)
        st.session_state.tela = "home"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

else:
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
        with st.expander("✉️ Testar envio de e-mail (SMTP)"):
            st.write("Use este teste para validar rapidamente as credenciais de e-mail em st.secrets.")
            test_to = st.text_input("Enviar e-mail de teste para:")
            if st.button("Enviar e-mail de teste"):
                ok = send_email(test_to.strip(), "Teste SMTP - Vamos Fleet SLA", "E-mail de teste enviado pelo aplicativo.")
                if ok:
                    st.success("E-mail de teste enviado com sucesso!")

            # Status das configs
            st.write("Status configurações:")
            st.write(f"- APP_BASE_URL: {'OK' if get_app_base_url() else 'NÃO CONFIGURADO'}")
            st.write(f"- SMTP: {'OK' if smtp_available() else 'NÃO CONFIGURADO'}")

        # Aprovação de cadastros pendentes
        st.subheader("Aprovar Cadastros Pendentes")
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
                    # aprova e envia notificação (ou convite p/ definir senha)
                    for uname in to_approve:
                        idx = df_users.index[df_users["username"] == uname][0]
                        df_users.loc[idx, "status"] = "aprovado"
                        email = df_users.loc[idx, "email"].strip()
                        if email:
                            # Se não tem senha definida, envia convite para definir senha
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
                    df_users = df_users[~df_users["username"].isin(to_approve)]
                    save_user_db(df_users)
                    st.success("Usuários removidos com sucesso!")
                    st.rerun()
                else:
                    st.warning("Selecione ao menos um usuário.")

        st.markdown("---")
        st.subheader("Adicionar Novo Usuário (admin)")
        with st.form("add_user_form", clear_on_submit=True):
            new_username = st.text_input("Usuário (para login)")
            new_full_name = st.text_input("Nome Completo")
            new_matricula = st.text_input("Matrícula")
            new_email = st.text_input("E-mail")
            new_password = st.text_input("Senha Temporária (opcional)", type="password")
            new_role = st.selectbox("Tipo de Acesso", ["user", "admin"])
            aprovar_agora = st.checkbox("Aprovar agora", value=True)
            if st.form_submit_button("Adicionar Usuário"):
                if new_username in df_users["username"].values:
                    st.error("Este nome de usuário já existe.")
                elif not all([new_username.strip(), new_full_name.strip(), new_email.strip()]):
                    st.error("Usuário, nome completo e e-mail são obrigatórios.")
                else:
                    status = "aprovado" if aprovar_agora else "pendente"
                    pwd_hash = hash_password(new_password) if new_password.strip() else ""
                    new_user_data = pd.DataFrame([{
                        "username": new_username.strip(),
                        "password": pwd_hash,
                        "role": new_role,
                        "full_name": new_full_name.strip(),
                        "matricula": new_matricula.strip(),
                        "email": new_email.strip(),
                        "status": status,
                        "accepted_terms_on": "",
                        "reset_token": "",
                        "reset_expires_at": ""
                    }])
                    df_users = pd.concat([df_users, new_user_data], ignore_index=True)
                    save_user_db(df_users)

                    # Envia e-mail imediatamente se aprovado
                    if status == "aprovado" and new_email.strip():
                        base_url = get_app_base_url() or "https://SEU_DOMINIO"
                        if not pwd_hash:
                            # enviar convite p/ definir senha
                            idx = df_users.index[df_users["username"] == new_username.strip()][0]
                            token = secrets.token_urlsafe(32)
                            expires = (datetime.utcnow() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
                            df_users.loc[idx, "reset_token"] = token
