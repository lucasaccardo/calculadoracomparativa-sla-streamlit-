# streamlit_app.py

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

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Calculadora SLA | Vamos",
    page_icon="logo_sidebar.png",
    layout="wide",
    initial_sidebar_state="auto"
)

# --- FUNÇÃO PARA APLICAR O FUNDO E CSS (VERSÃO CORRIGIDA) ---
def aplicar_estilos():
    try:
        with open("background.jpg", "rb") as f:
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
            /* Container principal para as telas pós-login */
            .main-container {{
                background-color: rgba(13, 17, 23, 0.85);
                padding: 25px;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                color: white; /* Garante que o texto dentro seja branco */
            }}
            .main-container h1, .main-container h2, .main-container h3, .main-container strong {{
                color: white; /* Força os títulos a serem brancos */
            }}
            /* Remove fundos duplicados de colunas dentro do container principal */
            .main-container .st-emotion-cache-1v0fkm {{
                background-color: transparent;
                border: none;
            }}
            /* Estilo para o formulário de login */
            [data-testid="stForm"] {{
                background-color: rgba(13, 17, 23, 0.85);
                padding: 25px;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            /* Deixa os títulos na tela de login brancos e com sombra para legibilidade */
            .login-container h1, .login-container h2 {{
                color: white;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
                text-align: center;
            }}
            .login-logo {{
                display: flex;
                justify-content: center;
                margin-bottom: 20px;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )
    except FileNotFoundError:
        pass

# --- FUNÇÕES DE GERENCIAMENTO DE USUÁRIOS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(hashed_password, user_password):
    return hashed_password == hash_password(user_password)

@st.cache_data
def load_user_db():
    if os.path.exists("users.csv") and os.path.getsize("users.csv") > 0:
        return pd.read_csv("users.csv")
    else:
        admin_user = {"username": ["lucas.sureira"], "password": [hash_password("Brasil@@2609")], "role": ["admin"]}
        df_users = pd.DataFrame(admin_user)
        df_users.to_csv("users.csv", index=False)
        return df_users

def save_user_db(df_users):
    df_users.to_csv("users.csv", index=False)
    st.cache_data.clear()

# --- FUNÇÕES AUXILIARES COMUNS ---
@st.cache_data
def carregar_base():
    try: return pd.read_excel("Base De Clientes Faturamento.xlsx")
    except FileNotFoundError: return None

def formatar_moeda(valor):
    return f"R${valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def moeda_para_float(valor_str):
    if isinstance(valor_str, (int, float)): return float(valor_str)
    if isinstance(valor_str, str):
        valor_str = valor_str.replace("R$", "").replace(".", "").replace(",", ".").strip()
        return float(valor_str)
    return 0.0

# --- FUNÇÕES DAS CALCULADORAS ---
def calcular_cenario_comparativo(cliente, placa, entrada, saida, feriados, servico, pecas, mensalidade):
    dias = np.busday_count(entrada.strftime('%Y-%m-%d'), (saida + timedelta(days=1)).strftime('%Y-%m-%d'))
    dias_uteis = max(dias - feriados, 0)
    sla_dict = {"Preventiva – 2 dias úteis": 2, "Corretiva – 3 dias úteis": 3, "Preventiva + Corretiva – 5 dias úteis": 5, "Motor – 15 dias úteis": 15}
    sla_dias = sla_dict.get(servico, 0)
    excedente = max(0, dias_uteis - sla_dias)
    desconto = (mensalidade / 30) * excedente if excedente > 0 else 0
    total_pecas = sum(p["valor"] for p in pecas)
    total_final = (mensalidade - desconto) + total_pecas
    return {"Cliente": cliente, "Placa": placa, "Data Entrada": entrada.strftime("%d/%m/%Y"), "Data Saída": saida.strftime("%d/%m/%Y"), "Serviço": servico, "Dias Úteis": dias_uteis, "SLA (dias)": sla_dias, "Excedente": excedente, "Mensalidade": formatar_moeda(mensalidade), "Desconto": formatar_moeda(round(desconto, 2)), "Peças (R$)": formatar_moeda(round(total_pecas, 2)), "Total Final (R$)": formatar_moeda(round(total_final, 2)), "Detalhe Peças": pecas}

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
            if col != "Detalhe Peças": elementos.append(Paragraph(f"<b>{col}:</b> {valor}", styles['Normal']))
        if row["Detalhe Peças"]:
            elementos.append(Paragraph("<b>Detalhe de Peças:</b>", styles['Normal']))
            for peca in row["Detalhe Peças"]: elementos.append(Paragraph(f"- {peca['nome']}: {formatar_moeda(peca['valor'])}", styles['Normal']))
        elementos.append(Spacer(1, 12)); elementos.append(Paragraph("─" * 90, styles['Normal'])); elementos.append(Spacer(1, 12))
    texto_melhor = f"<b>🏆 Melhor Cenário (Menor Custo Final)</b><br/>Serviço: {melhor_cenario['Serviço']}<br/>Placa: {melhor_cenario['Placa']}<br/><b>Total Final: {melhor_cenario['Total Final (R$)']}</b>"
    elementos.append(Spacer(1, 12)); elementos.append(Paragraph(texto_melhor, styles['Heading2']))
    doc.build(elementos); buffer.seek(0)
    return buffer

def calcular_sla_simples(data_entrada, data_saida, prazo_sla, valor_mensalidade, feriados=0):
    dias = np.busday_count(data_entrada.strftime('%Y-%m-%d'), (data_saida + timedelta(days=1)).strftime('%Y-%m-%d'))
    dias_uteis = max(dias - feriados, 0)
    if dias_uteis <= prazo_sla:
        status, desconto, dias_excedente = "Dentro do SLA", 0, 0
    else:
        status, dias_excedente = "Fora do SLA", dias_uteis - sla_dias
        desconto = (valor_mensalidade / 30) * dias_excedente
    return dias_uteis, status, desconto, dias_excedente

def gerar_pdf_sla_simples(cliente, placa, tipo_servico, dias_uteis_manut, prazo_sla, dias_excedente, valor_mensalidade, desconto):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    largura, altura = letter
    c.setFont("Helvetica-Bold", 14); c.drawString(50, altura - 50, "Resultado SLA - Vamos Locação")
    c.setFont("Helvetica", 12); y = altura - 80
    text_lines = [f"Cliente: {cliente}", f"Placa: {placa}", f"Tipo de serviço: {tipo_servico}", f"Dias úteis da manutenção: {dias_uteis_manut} dias", f"Prazo SLA: {prazo_sla} dias", f"Dias excedido de SLA: {dias_excedente} dias", f"Valor Mensalidade: {formatar_moeda(valor_mensalidade)}", f"Valor do desconto: {formatar_moeda(desconto)}"]
    for line in text_lines:
        c.drawString(50, y, line); y -= 20
    c.showPage(); c.save(); buffer.seek(0)
    return buffer

def ir_para_home(): st.session_state.tela = "home"
def ir_para_calc_comparativa(): st.session_state.tela = "calc_comparativa"
def ir_para_calc_simples(): st.session_state.tela = "calc_simples"
def ir_para_admin(): st.session_state.tela = "admin_users"
def limpar_dados_comparativos():
    keys_to_clear = ["cenarios", "pecas_atuais", "mostrar_comparativo"]
    for key in keys_to_clear:
        if key in st.session_state: del st.session_state[key]
def limpar_dados_simples():
    keys_to_clear = ["resultado_sla", "pesquisa_cliente"]
    for key in keys_to_clear:
        if key in st.session_state: del st.session_state[key]
def logout():
    for key in list(st.session_state.keys()): del st.session_state[key]

def renderizar_sidebar():
    with st.sidebar:
        try: st.image("logo_sidebar.png", width=100)
        except: pass
        st.header("Menu de Navegação")
        if st.session_state.get("role") == "admin":
            st.button("👤 Gerenciar Usuários", on_click=ir_para_admin, use_container_width=True)
        st.button("🏠 Voltar para Home", on_click=ir_para_home, use_container_width=True)
        if st.session_state.tela == "calc_comparativa":
            st.button("🔄 Limpar Comparação", on_click=limpar_dados_comparativos, use_container_width=True)
        if st.session_state.tela == "calc_simples":
            st.button("🔄 Limpar Cálculo", on_click=limpar_dados_simples, use_container_width=True)
        st.button("🚪 Sair (Logout)", on_click=logout, use_container_width=True, type="secondary")

if "tela" not in st.session_state: st.session_state.tela = "login"

aplicar_estilos()

if st.session_state.tela == "login":
    st.markdown("<div class='login-container'>", unsafe_allow_html=True)
    st.markdown("<div class='login-logo'>", unsafe_allow_html=True)
    try: st.image("logo.png", width=300)
    except: st.header("🚛 Vamos Locação")
    st.markdown("</div>", unsafe_allow_html=True)
    st.title("Plataforma de Calculadoras SLA", anchor=False)
    st.markdown("</div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Usuário", label_visibility="collapsed", placeholder="Usuário")
            password = st.text_input("Senha", type="password", label_visibility="collapsed", placeholder="Senha")
            if st.form_submit_button("Entrar 🚀"):
                df_users = load_user_db()
                user_data = df_users[df_users["username"] == username]
                if not user_data.empty and check_password(user_data.iloc[0]["password"], password):
                    st.session_state.logado = True; st.session_state.tela = "home"
                    st.session_state.username = user_data.iloc[0]["username"]; st.session_state.role = user_data.iloc[0]["role"]
                    st.rerun()
                else: st.error("❌ Usuário ou senha incorretos.")

else:
    # Este container agora só é aplicado em telas que não são a de login
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)
    
    if st.session_state.tela == "home":
        renderizar_sidebar()
        st.title(f"🏠 Home"); st.write(f"### Bem-vindo, {st.session_state.username}!")
        st.write("Selecione abaixo a ferramenta que deseja utilizar.")
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📊 Calculadora Comparativa de SLA")
            st.write("Calcule e compare múltiplos cenários para encontrar a opção com o menor custo final.")
            st.button("Acessar Calculadora Comparativa", on_click=ir_para_calc_comparativa, use_container_width=True)
        with col2:
            st.subheader("🖩 Calculadora de SLA Simples")
            st.write("Calcule rapidamente o desconto de SLA para um único serviço ou veículo.")
            st.button("Acessar Calculadora Simples", on_click=ir_para_calc_simples, use_container_width=True)
    
    elif st.session_state.tela == "admin_users":
        renderizar_sidebar()
        st.title("👤 Gerenciamento de Usuários")
        # O resto do código do admin...
    
    elif st.session_state.tela == "calc_comparativa":
        renderizar_sidebar()
        st.title("📊 Calculadora Comparativa de Cenários")
        # O resto do código da calculadora...
    
    elif st.session_state.tela == "calc_simples":
        renderizar_sidebar()
        st.title("🖩 Calculadora de SLA Simples")
        # O resto do código da calculadora...

    # ... (O restante do código completo para as telas admin_users, calc_comparativa, e calc_simples vai aqui, 
    # garantindo que eles fiquem dentro do else e, portanto, dentro do .main-container)

    st.markdown("</div>", unsafe_allow_html=True) # Fecha o container principal
