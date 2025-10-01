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

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Calculadora SLA | Vamos",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="auto"
)

# --- FUNÇÕES DE GERENCIAMENTO DE USUÁRIOS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(hashed_password, user_password):
    return hashed_password == hash_password(user_password)

@st.cache_data
def load_user_db():
    try:
        df = pd.read_csv("users.csv")
        if df.empty: raise pd.errors.EmptyDataError
        if "full_name" not in df.columns: df["full_name"] = "N/A"
        if "matricula" not in df.columns: df["matricula"] = "N/A"
        if "accepted_terms_on" not in df.columns: df["accepted_terms_on"] = None
        return df
    except (FileNotFoundError, pd.errors.EmptyDataError):
        admin_user = {
            "username": ["lucas.sureira"], "password": [hash_password("Brasil@@2609")], "role": ["admin"],
            "full_name": ["Administrador Principal"], "matricula": ["N/A"], "accepted_terms_on": [None]
        }
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
    dias = np.busday_count(data_entrada.strftime('%Y-%m-%d'), (saida + timedelta(days=1)).strftime('%Y-%m-%d'))
    dias_uteis = max(dias - feriados, 0)
    if dias_uteis <= prazo_sla:
        status, desconto, dias_excedente = "Dentro do SLA", 0, 0
    else:
        status, dias_excedente = "Fora do SLA", dias_uteis - prazo_sla
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

df_users = load_user_db()
if st.session_state.tela == "login":
    try: st.image("logo.png", width=200)
    except: st.header("🚛 Vamos Locação")
    st.title("Plataforma de Calculadoras SLA"); st.write("Faça o login para acessar as ferramentas.")
    with st.form("login_form"):
        username = st.text_input("Usuário", label_visibility="collapsed", placeholder="Usuário")
        password = st.text_input("Senha", type="password", label_visibility="collapsed", placeholder="Senha")
        if st.form_submit_button("Entrar 🚀"):
            user_data = df_users[df_users["username"] == username]
            if not user_data.empty and check_password(user_data.iloc[0]["password"], password):
                st.session_state.logado = True
                st.session_state.username = user_data.iloc[0]["username"]
                st.session_state.role = user_data.iloc[0]["role"]
                if "accepted_terms_on" in user_data.columns and pd.isna(user_data.iloc[0]["accepted_terms_on"]):
                    st.session_state.tela = "terms_consent"
                else:
                    st.session_state.tela = "home"
                st.rerun()
            else: st.error("❌ Usuário ou senha incorretos.")

elif st.session_state.tela == "terms_consent":
    st.title("Termos e Condições de Uso e Política de Privacidade (LGPD)")
    st.info("Para seu primeiro acesso, é necessário ler e aceitar os termos de uso da plataforma.")
    st.markdown("""
    **Termos e Condições de Uso da Plataforma de Calculadoras SLA**

    *Última atualização: 28 de Setembro de 2025*

    Bem-vindo à Plataforma de Calculadoras SLA da Vamos Locação. Ao acessar e utilizar esta ferramenta, você concorda em cumprir os seguintes termos e condições.

    **1. Finalidade da Ferramenta**
    Esta plataforma foi desenvolvida como uma ferramenta interna para auxiliar nos cálculos de Service Level Agreement (SLA), não possuindo valor fiscal ou contratual. Os resultados gerados são estimativas e devem ser usados apenas como referência.

    **2. Uso de Dados e Conformidade com a LGPD**
    A Lei Geral de Proteção de Dados (LGPD), Lei nº 13.709/2018, é a legislação brasileira que regula as atividades de tratamento de dados pessoais.
    - **Dados Coletados:** Para o funcionamento da ferramenta, utilizamos dados previamente cadastrados, como informações de clientes, placas de veículos e valores de mensalidade. Nenhum novo dado pessoal é coletado através da interação com as calculadoras.
    - **Finalidade:** O uso desses dados é restrito à finalidade específica do cálculo de SLA, conforme as necessidades operacionais da Vamos Locação.
    - **Segurança:** As senhas de acesso são armazenadas de forma criptografada (hashed), garantindo que não possam ser lidas em texto puro.
    - **Não Compartilhamento:** Os dados processados por esta ferramenta não são compartilhados com terceiros.

    **3. Responsabilidades do Usuário**
    - O usuário é responsável por manter a confidencialidade de suas credenciais de acesso (usuário e senha).
    - O uso da ferramenta deve ser estritamente profissional e limitado às atividades para as quais foi designada.

    **4. Aceite dos Termos**
    Ao marcar a caixa abaixo e continuar, você declara que leu, compreendeu e concorda com estes Termos e Condições de Uso e com a forma que seus dados são tratados.
    """)
    st.markdown("---")
    consent = st.checkbox("Eu li e concordo com os Termos e Condições.")
    if st.button("Continuar", disabled=not consent, type="primary"):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user_index = df_users.index[df_users['username'] == st.session_state.username][0]
        df_users.loc[user_index, 'accepted_terms_on'] = now
        save_user_db(df_users)
        st.session_state.tela = "home"
        st.rerun()

elif st.session_state.tela == "home":
    renderizar_sidebar()
    st.title(f"🏠 Home"); st.write(f"### Bem-vindo, {st.session_state.username}!")
    st.write("Selecione abaixo a ferramenta que deseja utilizar.")
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📊 Calculadora Comparativa de SLA"); st.write("Calcule e compare múltiplos cenários.")
        st.button("Acessar Calculadora Comparativa", on_click=ir_para_calc_comparativa, use_container_width=True)
    with col2:
        st.subheader("🖩 Calculadora de SLA Simples"); st.write("Calcule rapidamente o desconto de SLA para um único serviço.")
        st.button("Acessar Calculadora Simples", on_click=ir_para_calc_simples, use_container_width=True)

elif st.session_state.tela == "admin_users":
    renderizar_sidebar()
    st.title("👤 Gerenciamento de Usuários")
    st.subheader("Adicionar Novo Usuário")
    with st.form("add_user_form", clear_on_submit=True):
        new_username = st.text_input("Usuário (para login)")
        new_full_name = st.text_input("Nome Completo")
        new_matricula = st.text_input("Matrícula")
        new_password = st.text_input("Senha Temporária", type="password")
        new_role = st.selectbox("Tipo de Acesso", ["user", "admin"])
        if st.form_submit_button("Adicionar Usuário"):
            if new_username in df_users["username"].values: st.error("Este nome de usuário já existe.")
            elif not all([new_username, new_password, new_full_name, new_matricula]):
                st.error("Todos os campos são obrigatórios.")
            else:
                new_user_data = pd.DataFrame({
                    "username": [new_username], "password": [hash_password(new_password)], "role": [new_role],
                    "full_name": [new_full_name], "matricula": [new_matricula], "accepted_terms_on": [None]
                })
                df_users = pd.concat([df_users, new_user_data], ignore_index=True)
                save_user_db(df_users)
                st.success(f"Usuário '{new_username}' adicionado com sucesso!")
    st.markdown("---"); st.subheader("Usuários Existentes")
    st.dataframe(df_users[["username", "full_name", "matricula", "role", "accepted_terms_on"]], use_container_width=True)
    with st.expander("⚠️ Remover Usuários Existentes"):
        usuarios_deletaveis = [user for user in df_users["username"] if user != st.session_state.username]
        if not usuarios_deletaveis:
            st.info("Não há outros usuários para remover.")
        else:
            usuarios_para_remover = st.multiselect("Selecione um ou mais usuários para remover:", options=usuarios_deletaveis)
            if st.button("Remover Usuários Selecionados", type="primary"):
                if usuarios_para_remover:
                    df_users = df_users[~df_users["username"].isin(usuarios_para_remover)]
                    save_user_db(df_users)
                    st.success("Usuários removidos com sucesso!"); st.rerun()
                else:
                    st.warning("Nenhum usuário selecionado.")

elif st.session_state.tela == "calc_comparativa":
    renderizar_sidebar()
    st.title("📊 Calculadora Comparativa de Cenários")
    if "cenarios" not in st.session_state: st.session_state.cenarios = []
    if "pecas_atuais" not in st.session_state: st.session_state.pecas_atuais = []
    if "mostrar_comparativo" not in st.session_state: st.session_state.mostrar_comparativo = False
    df_base = carregar_base()
    if df_base is None: st.error("❌ Arquivo 'Base De Clientes Faturamento.xlsx' não encontrado."); st.stop()
    if st.session_state.cenarios:
        st.markdown("---"); st.header("📈 Cenários Calculados")
        df_cenarios = pd.DataFrame(st.session_state.cenarios)
        st.table(df_cenarios.drop(columns=["Detalhe Peças"]))
        if len(st.session_state.cenarios) >= 2 and not st.session_state.mostrar_comparativo:
            if st.button("🏆 Comparar Cenários", type="primary"):
                st.session_state.mostrar_comparativo = True; st.rerun()
    if st.session_state.mostrar_comparativo:
        st.header("Análise Comparativa Final")
        df_cenarios = pd.DataFrame(st.session_state.cenarios)
        melhor = df_cenarios.loc[df_cenarios["Total Final (R$)"].apply(moeda_para_float).idxmin()]
        st.success(f"🏆 Melhor cenário: **{melhor['Serviço']}** | Placa **{melhor['Placa']}** | Total Final: **{melhor['Total Final (R$)']}**")
        pdf_buffer = gerar_pdf_comparativo(df_cenarios, melhor)
        st.download_button("📥 Baixar Relatório PDF", pdf_buffer, "comparacao_cenarios_sla.pdf", "application/pdf")
        st.button("🔄 Reiniciar Comparação", on_click=limpar_dados_comparativos, use_container_width=True, type="primary")
    else:
        st.markdown("---"); st.header(f"📝 Preencher Dados para o Cenário {len(st.session_state.cenarios) + 1}")
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
                    cliente_info = {"cliente": cliente_row.iloc[0]["CLIENTE"], "mensalidade": moeda_para_float(cliente_row.iloc[0]["VALOR MENSALIDADE"])}
                    st.info(f"✅ **Cliente:** {cliente_info['cliente']} | **Mensalidade:** {formatar_moeda(cliente_info['mensalidade'])}")
                else: st.warning("❌ Placa não encontrada.")
            with st.form(key=f"form_cenario_{len(st.session_state.cenarios)}", clear_on_submit=True):
                st.subheader("2. Detalhes do Serviço")
                subcol1, subcol2 = st.columns(2)
                entrada = subcol1.date_input("📅 Data de entrada:", datetime.now())
                saida = subcol2.date_input("📅 Data de saída:", datetime.now() + timedelta(days=5))
                feriados = subcol1.number_input("📌 Feriados no período:", min_value=0, step=1)
                servico = subcol2.selectbox("🛠️ Tipo de serviço:", ["Preventiva – 2 dias úteis", "Corretiva – 3 dias úteis", "Preventiva + Corretiva – 5 dias úteis", "Motor – 15 dias úteis"])
                with st.expander("Verificar Peças Adicionadas"):
                    if st.session_state.pecas_atuais:
                        for peca in st.session_state.pecas_atuais:
                            col_peca_nome, col_peca_valor = st.columns([3, 1]); col_peca_nome.write(peca['nome']); col_peca_valor.write(formatar_moeda(peca['valor']))
                    else: st.info("Nenhuma peça adicionada na coluna da direita.")
                submitted = st.form_submit_button(f"➡️ Calcular Cenário {len(st.session_state.cenarios) + 1}", use_container_width=True, type="primary")
                if submitted:
                    if cliente_info:
                        if entrada >= saida: st.error("A data de saída deve ser posterior à de entrada.")
                        else:
                            cenario = calcular_cenario_comparativo(cliente_info["cliente"], placa.upper(), entrada, saida, feriados, servico, st.session_state.pecas_atuais, cliente_info["mensalidade"])
                            st.session_state.cenarios.append(cenario); st.session_state.pecas_atuais = []; st.rerun()
                    else: st.error("Placa inválida ou não encontrada para submeter.")
        with col_pecas:
            st.subheader("3. Gerenciar Peças")
            nome_peca = st.text_input("Nome da Peça", key="nome_peca_input")
            valor_peca = st.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f", key="valor_peca_input")
            if st.button("➕ Adicionar Peça", use_container_width=True):
                if nome_peca and valor_peca > 0:
                    st.session_state.pecas_atuais.append({"nome": nome_peca, "valor": valor_peca}); st.rerun()
                else: st.warning("Preencha o nome e o valor da peça.")
            if st.session_state.pecas_atuais:
                st.markdown("---"); st.write("**Peças adicionadas:**")
                opcoes_pecas = [f"{p['nome']} - {formatar_moeda(p['valor'])}" for p in st.session_state.pecas_atuais]
                pecas_para_remover = st.multiselect("Selecione para remover:", options=opcoes_pecas)
                if st.button("🗑️ Remover Selecionadas", type="secondary", use_container_width=True):
                    if pecas_para_remover:
                        nomes_para_remover = [item.split(' - ')[0] for item in pecas_para_remover]
                        st.session_state.pecas_atuais = [p for p in st.session_state.pecas_atuais if p['nome'] not in nomes_para_remover]; st.rerun()
                    else: st.warning("⚠️ Nenhuma peça foi selecionada.")

elif st.session_state.tela == "calc_simples":
    renderizar_sidebar()
    st.title("🖩 Calculadora de SLA Simples")
    if "resultado_sla" not in st.session_state: st.session_state.resultado_sla = None
    if "pesquisa_cliente" not in st.session_state: st.session_state.pesquisa_cliente = ""
    df_base = carregar_base()
    if df_base is None: st.error("❌ Arquivo 'Base De Clientes Faturamento.xlsx' não encontrado."); st.stop()
    if st.session_state.resultado_sla:
        st.markdown("---"); st.header("✅ Resultado do Cálculo")
        r = st.session_state.resultado_sla
        st.metric(label="Status", value="Fora do SLA" if r["dias_excedente"] > 0 else "Dentro do SLA")
        st.metric(label="Valor do Desconto", value=formatar_moeda(r['desconto']))
        col1, col2, col3 = st.columns(3)
        col1.metric("Dias Úteis na Manutenção", f"{r['dias']} dias")
        col2.metric("Prazo SLA", f"{r['prazo_sla']} dias")
        col3.metric("Dias Excedentes", f"{r['dias_excedente']} dias")
        pdf_buffer = gerar_pdf_sla_simples(r['cliente'], r['placa'], r['tipo_servico'], r['dias'], r['prazo_sla'], r['dias_excedente'], r['valor_mensalidade'], r['desconto'])
        st.download_button(label="📥 Baixar resultado em PDF", data=pdf_buffer, file_name=f"SLA_{r['placa']}.pdf", mime="application/pdf", use_container_width=True)
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
            if registro.empty: st.error("❌ Placa não encontrada!")
            else:
                registro = registro.iloc[0]
                cliente, valor_mensalidade = registro["CLIENTE"], registro["VALOR MENSALIDADE"]
                st.info(f"**Cliente:** {cliente} | **Placa:** {placa_selecionada} | **Mensalidade:** {formatar_moeda(valor_mensalidade)}")
                st.markdown("---"); st.subheader("2. Detalhes do Serviço")
                sla_opcoes = {"Preventiva": 2, "Corretiva": 3, "Preventiva + Corretiva": 5, "Motor": 15}
                tipo_sla_selecionado = st.selectbox("⚙️ Escolha o tipo de SLA:", [f"{k}: {v} dias úteis" for k, v in sla_opcoes.items()])
                prazo_sla = sla_opcoes[tipo_sla_selecionado.split(":")[0]]
                col1, col2 = st.columns(2)
                data_entrada = col1.date_input("📅 Data de entrada na oficina", datetime.today())
                data_saida = col2.date_input("📅 Data de saída da oficina", datetime.today())
                feriados = st.number_input("🗓️ Quantos feriados no período?", min_value=0, step=1)
                if st.button("Calcular SLA", use_container_width=True, type="primary"):
                    dias, status, desconto, dias_excedente = calcular_sla_simples(data_entrada, data_saida, prazo_sla, valor_mensalidade, feriados)
                    st.session_state.resultado_sla = {"cliente": cliente, "placa": placa_selecionada, "tipo_servico": tipo_sla_selecionado.split(":")[0], "dias": dias, "prazo_sla": prazo_sla, "dias_excedente": dias_excedente, "valor_mensalidade": valor_mensalidade, "desconto": desconto}
                    st.rerun()

