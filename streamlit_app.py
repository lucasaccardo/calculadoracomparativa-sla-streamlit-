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

# --- EMAIL / RESET DE SENHA ---
def send_reset_email(dest_email: str, reset_link: str):
    try:
        host = st.secrets.get("EMAIL_HOST", "")
        port = int(st.secrets.get("EMAIL_PORT", 587))
        user = st.secrets.get("EMAIL_USERNAME", "")
        password = st.secrets.get("EMAIL_PASSWORD", "")
        use_tls = bool(st.secrets.get("EMAIL_USE_TLS", True))
        sender = st.secrets.get("EMAIL_FROM", user or "no-reply@example.com")

        if not host or not user or not password:
            st.warning("Configurações de e-mail não definidas em st.secrets. Exibindo link de teste na tela.")
            st.code(reset_link, language="text")
            return

        msg = EmailMessage()
        msg["Subject"] = "Redefinição de senha - Vamos Fleet SLA"
        msg["From"] = sender
        msg["To"] = dest_email
        msg.set_content(f"""
Olá,

Recebemos uma solicitação para redefinição de senha da sua conta no Vamos Fleet SLA.

Para redefinir sua senha, acesse o link abaixo (válido por 30 minutos):
{reset_link}

Se você não solicitou, ignore este e-mail.

Atenciosamente,
Equipe Vamos
""")
        server = smtplib.SMTP(host, port)
        if use_tls:
            server.starttls()
        server.login(user, password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        st.error(f"Falha ao enviar e-mail: {e}")
        st.code(reset_link, language="text")  # fallback

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
            .login-container h1, .login-container h2 {{
                color: white;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.7);
                text-align: center;
            }}
            .login-logo {{
                display: flex;
                justify-content: center;
                margin-bottom: 20px;
            }}
            a, .as-link {{
                color: #91c9ff !important;
                text-decoration: underline !important;
                cursor: pointer;
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
        # Cria arquivo já com o admin principal pronto
        df = pd.DataFrame([admin_defaults])
        df.to_csv("users.csv", index=False)
        return df

    # Garante colunas
    for col in REQUIRED_USER_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Garante que o admin principal existe e está correto
    if admin_username in df["username"].values:
        idx = df.index[df["username"] == admin_username][0]
        # Atualiza/garante os dados do admin (mantém accepted_terms_on se já houver)
        for k, v in admin_defaults.items():
            if k == "accepted_terms_on" and str(df.loc[idx, k]).strip():
                continue  # não sobrescreve aceite existente
            df.loc[idx, k] = v
    else:
        df = pd.concat([df, pd.DataFrame([admin_defaults])], ignore_index=True)

    # Persiste correções, se houver
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
    keys_to_clear = ["cenarios", "pecas_atuais", "mostrar_comparativo"]
    for key in keys_to_clear:
        if key in st.session_state: del st.session_state[key]

def limpar_dados_simples():
    keys_to_clear = ["resultado_sla", "pesquisa_cliente"]
    for key in keys_to_clear:
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

aplicar_estilos()

# Detecta token de redefinição vindo por URL
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

                base_url = st.secrets.get("APP_BASE_URL", "")
                if not base_url:
                    st.info("APP_BASE_URL não definido em st.secrets. Exibindo link gerado.")
                    base_url = "https://SEU_DOMINIO/"
                if not base_url.endswith("/"):
                    base_url += "/"
                reset_link = f"{base_url}?reset_token={token}"

                send_reset_email(email.strip(), reset_link)
                st.success("Se o e-mail existir e estiver aprovado, um link foi enviado. Verifique sua caixa de entrada.")

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
    st.info("Para seu primeiro acesso, é necessário ler e aceitar os termos de uso da plataforma.")
    st.markdown("""
    **Termos e Condições de Uso da Plataforma de Calculadoras SLA**
    *Última atualização: 28 de Setembro de 2025*

    Bem-vindo à Plataforma de Calculadoras SLA da Vamos Locação. Ao acessar e utilizar esta ferramenta, você concorda em cumprir os seguintes termos.

    **1. Finalidade da Ferramenta**
    Esta plataforma é uma ferramenta interna para simulação e referência de cálculos de Service Level Agreement (SLA). Os resultados são estimativas para apoio operacional e não possuem valor fiscal ou contratual definitivo.

    **2. Política de Privacidade e Conformidade com a LGPD**
    Em conformidade com a Lei Geral de Proteção de Dados (LGPD, Lei nº 13.709/2018), detalhamos como os dados são tratados:
    - **Dados Tratados:** A ferramenta utiliza dados cadastrais da empresa, como nomes de clientes, placas de veículos e valores contratuais, além de seus dados de login (nome de usuário, nome completo, matrícula).
    - **Finalidade do Tratamento:** Os dados são utilizados exclusivamente para as finalidades da ferramenta: autenticação de acesso e realização dos cálculos de SLA.
    - **Segurança:** Suas credenciais de acesso são armazenadas com criptografia (hash), e o acesso aos dados é restrito a usuários autorizados.
    - **Não Compartilhamento:** Os dados aqui processados são de uso interno da Vamos Locação e não são compartilhados com terceiros.

    **3. Responsabilidades do Usuário**
    - Você é responsável por manter a confidencialidade de seu usuário e senha.
    - O uso da ferramenta deve ser estritamente profissional e limitado às atividades da empresa.

    **4. Aceite dos Termos**
    Ao marcar a caixa abaixo e continuar, você declara que leu, compreendeu e concorda com estes Termos e Condições de Uso e com a forma que seus dados são tratados.
    """)
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
        st.title(f"🏠 Home")
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
                    df_users.loc[df_users["username"].isin(to_approve), "status"] = "aprovado"
                    save_user_db(df_users)
                    st.success("Usuários aprovados com sucesso!")
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
                    st.success(f"Usuário '{new_username}' adicionado com sucesso!")

        st.markdown("---")
        st.subheader("Usuários Existentes")
        for col in ["full_name", "matricula", "accepted_terms_on", "email", "status"]:
            if col not in df_users.columns:
                df_users[col] = ""
        st.dataframe(
            df_users[["username", "full_name", "matricula", "email", "role", "status", "accepted_terms_on"]],
            use_container_width=True
        )
        with st.expander("⚠️ Remover Usuários Existentes"):
            usuarios_deletaveis = [user for user in df_users["username"] if user != st.session_state.get("username", "")]
            if not usuarios_deletaveis:
                st.info("Não há outros usuários para remover.")
            else:
                usuarios_para_remover = st.multiselect("Selecione para remover:", options=usuarios_deletaveis)
                if st.button("Remover Usuários Selecionados", type="primary"):
                    if usuarios_para_remover:
                        df_users = df_users[~df_users["username"].isin(usuarios_para_remover)]
                        save_user_db(df_users)
                        st.success("Usuários removidos com sucesso!")
                        st.rerun()
                    else:
                        st.warning("Nenhum usuário selecionado.")

    elif st.session_state.tela == "calc_comparativa":
        st.title("📊 Calculadora Comparativa de Cenários")
        if "cenarios" not in st.session_state: st.session_state.cenarios = []
        if "pecas_atuais" not in st.session_state: st.session_state.pecas_atuais = []
        if "mostrar_comparativo" not in st.session_state: st.session_state.mostrar_comparativo = False
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
            st.success(f"🏆 Melhor cenário: **{melhor['Serviço']}** | Placa **{melhor['Placa']}** | Total Final: **{melhor['Total Final (R$)']}**")
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
                        st.info(f"✅ **Cliente:** {cliente_info['cliente']} | **Mensalidade:** {formatar_moeda(cliente_info['mensalidade'])}")
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
                                col_peca_nome, col_peca_valor = st.columns([3, 1])
                                col_peca_nome.write(peca['nome'])
                                col_peca_valor.write(formatar_moeda(peca['valor']))
                        else:
                            st.info("Nenhuma peça adicionada na coluna da direita.")
                    submitted = st.form_submit_button(
                        f"➡️ Calcular Cenário {len(st.session_state.cenarios) + 1}",
                        use_container_width=True, type="primary"
                    )
                    if submitted:
                        if cliente_info:
                            if entrada >= saida:
                                st.error("A data de saída deve ser posterior à de entrada.")
                            else:
                                cenario = calcular_cenario_comparativo(
                                    cliente_info["cliente"], placa.upper(), entrada, saida,
                                    feriados, servico, st.session_state.pecas_atuais, cliente_info["mensalidade"]
                                )
                                st.session_state.cenarios.append(cenario)
                                st.session_state.pecas_atuais = []
                                st.rerun()
                        else:
                            st.error("Placa inválida ou não encontrada para submeter.")

            with col_pecas:
                st.subheader("3. Gerenciar Peças")
                nome_peca = st.text_input("Nome da Peça", key="nome_peca_input")
                valor_peca = st.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f", key="valor_peca_input")
                if st.button("➕ Adicionar Peça", use_container_width=True):
                    if nome_peca and valor_peca > 0:
                        st.session_state.pecas_atuais.append({"nome": nome_peca, "valor": valor_peca})
                        st.rerun()
                    else:
                        st.warning("Preencha o nome e o valor da peça.")
                if st.session_state.pecas_atuais:
                    st.markdown("---")
                    st.write("**Peças adicionadas:**")
                    opcoes_pecas = [f"{p['nome']} - {formatar_moeda(p['valor'])}" for p in st.session_state.pecas_atuais]
                    pecas_para_remover = st.multiselect("Selecione para remover:", options=opcoes_pecas)
                    if st.button("🗑️ Remover Selecionadas", type="secondary", use_container_width=True):
                        if pecas_para_remover:
                            nomes_para_remover = [item.split(' - ')[0] for item in pecas_para_remover]
                            st.session_state.pecas_atuais = [p for p in st.session_state.pecas_atuis if p['nome'] not in nomes_para_remover]
                            st.rerun()
                        else:
                            st.warning("⚠️ Nenhuma peça foi selecionada.")

    elif st.session_state.tela == "calc_simples":
        st.title("🖩 Calculadora de SLA Simples")
        if "resultado_sla" not in st.session_state:
            st.session_state.resultado_sla = None
        if "pesquisa_cliente" not in st.session_state:
            st.session_state.pesquisa_cliente = ""
        df_base = carregar_base()
        if df_base is None:
            st.error("❌ Arquivo 'Base De Clientes Faturamento.xlsx' não encontrado.")
            st.stop()

        if st.session_state.resultado_sla:
            st.markdown("---")
            st.header("✅ Resultado do Cálculo")
            r = st.session_state.resultado_sla
            st.metric(label="Status", value="Fora do SLA" if r["dias_excedente"] > 0 else "Dentro do SLA")
            st.metric(label="Valor do Desconto", value=formatar_moeda(r['desconto']))
            col1, col2, col3 = st.columns(3)
            col1.metric("Dias Úteis na Manutenção", f"{r['dias']} dias")
            col2.metric("Prazo SLA", f"{r['prazo_sla']} dias")
            col3.metric("Dias Excedentes", f"{r['dias_excedente']} dias")
            pdf_buffer = gerar_pdf_sla_simples(
                r['cliente'], r['placa'], r['tipo_servico'], r['dias'],
                r['prazo_sla'], r['dias_excedente'], r['valor_mensalidade'], r['desconto']
            )
            st.download_button(
                label="📥 Baixar resultado em PDF", data=pdf_buffer,
                file_name=f"SLA_{r['placa']}.pdf", mime="application/pdf", use_container_width=True
            )
            st.button("🔄 Iniciar Novo Cálculo", on_click=limpar_dados_simples, use_container_width=True, type="primary")
        else:
            st.subheader("1. Consulta de Cliente ou Placa")
            buscar_cliente = st.radio("Deseja procurar o cliente pelo nome?", ("Não", "Sim"), horizontal=True)
            placa_selecionada = ""
            if buscar_cliente == "Sim":
                pesquisa = st.text_input("🔍 Pesquise o nome do cliente:", key="pesquisa_cliente")
                if pesquisa:
                    df_filtrado = df_base[df_base["CLIENTE"].str.contains(pesquisa, case=False, na=False)]
                    st.dataframe(df_filtrado[["CLIENTE", "PLACA", "VALOR MENSALIDADE"]])
                    placa_selecionada = st.selectbox("Selecione a placa:", df_filtrado["PLACA"].tolist())
            else:
                placa_selecionada = st.text_input("📌 Digite a PLACA do ativo:")

            if placa_selecionada:
                registro = df_base[df_base["PLACA"].astype(str).str.upper() == str(placa_selecionada).strip().upper()]
                if registro.empty:
                    st.error("❌ Placa não encontrada!")
                else:
                    registro = registro.iloc[0]
                    cliente, valor_mensalidade = registro["CLIENTE"], registro["VALOR MENSALIDADE"]
                    st.info(f"**Cliente:** {cliente} | **Placa:** {placa_selecionada} | **Mensalidade:** {formatar_moeda(valor_mensalidade)}")
                    st.markdown("---")
                    st.subheader("2. Detalhes do Serviço")
                    sla_opcoes = {"Preventiva": 2, "Corretiva": 3, "Preventiva + Corretiva": 5, "Motor": 15}
                    tipo_sla_selecionado = st.selectbox("⚙️ Escolha o tipo de SLA:", [f"{k}: {v} dias úteis" for k, v in sla_opcoes.items()])
                    prazo_sla = sla_opcoes[tipo_sla_selecionado.split(":")[0]]
                    col1, col2 = st.columns(2)
                    data_entrada = col1.date_input("📅 Data de entrada na oficina", datetime.today())
                    data_saida = col2.date_input("📅 Data de saída da oficina", datetime.today())
                    feriados = st.number_input("🗓️ Quantos feriados no período?", min_value=0, step=1)
                    if st.button("Calcular SLA", use_container_width=True, type="primary"):
                        dias, status, desconto, dias_excedente = calcular_sla_simples(
                            data_entrada, data_saida, prazo_sla, valor_mensalidade, feriados
                        )
                        st.session_state.resultado_sla = {
                            "cliente": cliente,
                            "placa": placa_selecionada,
                            "tipo_servico": tipo_sla_selecionado.split(":")[0],
                            "dias": dias,
                            "prazo_sla": prazo_sla,
                            "dias_excedente": dias_excedente,
                            "valor_mensalidade": valor_mensalidade,
                            "desconto": desconto
                        }
                        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
