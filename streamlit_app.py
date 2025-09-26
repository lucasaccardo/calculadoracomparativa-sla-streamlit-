# streamlit_app.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Calculadora SLA | Vamos",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="auto"
)

# --- Funções Auxiliares ---
@st.cache_data
def carregar_base():
    try:
        return pd.read_excel("Base De Clientes Faturamento.xlsx")
    except FileNotFoundError:
        return None

def calcular_dias_uteis(data_inicio, data_fim, feriados=0):
    dias = 0; data_atual = data_inicio + timedelta(days=1)
    while data_atual <= data_fim:
        if data_atual.weekday() < 5: dias += 1
        data_atual += timedelta(days=1)
    return max(dias - feriados, 0)

def obter_sla(servico):
    sla_dict = {"Preventiva – 2 dias úteis": 2, "Corretiva – 3 dias úteis": 3, "Preventiva + Corretiva – 5 dias úteis": 5, "Motor – 15 dias úteis": 15}
    return sla_dict.get(servico, 0)

def formatar_moeda(valor):
    return f"R${valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def moeda_para_float(valor_str):
    if isinstance(valor_str, (int, float)): return float(valor_str)
    if isinstance(valor_str, str):
        valor_str = valor_str.replace("R$", "").replace(".", "").replace(",", ".").strip()
        return float(valor_str)
    return 0.0

def calcular_cenario(cliente, placa, entrada, saida, feriados, servico, pecas, mensalidade):
    sla_dias = obter_sla(servico)
    dias_uteis = calcular_dias_uteis(entrada, saida, feriados)
    excedente = max(0, dias_uteis - sla_dias)
    desconto = (mensalidade / 30) * excedente if excedente > 0 else 0
    total_pecas = sum(p["valor"] for p in pecas)
    total_final = (mensalidade - desconto) + total_pecas
    return {
        "Cliente": cliente, "Placa": placa, "Data Entrada": entrada.strftime("%d/%m/%Y"),
        "Data Saída": saida.strftime("%d/%m/%Y"), "Serviço": servico, "Dias Úteis": dias_uteis,
        "SLA (dias)": sla_dias, "Excedente": excedente, "Mensalidade": formatar_moeda(mensalidade),
        "Desconto": formatar_moeda(round(desconto, 2)), "Peças (R$)": formatar_moeda(round(total_pecas, 2)),
        "Total Final (R$)": formatar_moeda(round(total_final, 2)), "Detalhe Peças": pecas
    }

def gerar_pdf(df_cenarios, melhor_cenario):
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

def ir_para_home(): st.session_state.tela = "home"
def ir_para_calculadora(): st.session_state.tela = "calculadora"
def limpar_dados():
    keys_to_clear = ["cenarios", "pecas_atuais", "cliente_info", "input_placa", "estado_calculo", "mostrar_comparativo"]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

def logout():
    for key in st.session_state.keys(): del st.session_state[key]

def renderizar_sidebar():
    with st.sidebar:
        st.header("Menu de Navegação")
        st.button("🏠 Voltar para Home", on_click=ir_para_home, use_container_width=True)
        if st.session_state.tela == "calculadora":
            # ALTERAÇÃO: Texto do botão alterado conforme solicitado
            st.button("🔄 Reiniciar Comparação", on_click=limpar_dados, use_container_width=True)
        st.button("🚪 Sair (Logout)", on_click=logout, use_container_width=True, type="secondary")

# Inicialização do session_state
if "tela" not in st.session_state: st.session_state.tela = "login"
if "cenarios" not in st.session_state: st.session_state.cenarios = []
if "pecas_atuais" not in st.session_state: st.session_state.pecas_atuais = []
if "mostrar_comparativo" not in st.session_state: st.session_state.mostrar_comparativo = False

# --- LÓGICA DE RENDERIZAÇÃO DAS TELAS ---
if st.session_state.tela == "login":
    try: st.image("logo.png", width=200)
    except: st.header("🚛 Vamos Locação")
    st.title("Calculadora Comparativa"); st.write("Faça o login para acessar a ferramenta.")
    with st.form("login_form"):
        usuario = st.text_input("👤 **Usuário**", label_visibility="collapsed", placeholder="Usuário")
        senha = st.text_input("🔑 **Senha**", type="password", label_visibility="collapsed", placeholder="Senha")
        if st.form_submit_button("Entrar 🚀"):
            if usuario == "calculadorasla" and senha == "Vamos@@sla":
                st.session_state.logado = True; st.session_state.tela = "home"; st.rerun()
            else: st.error("❌ Usuário ou senha incorretos.")

elif st.session_state.tela == "home":
    renderizar_sidebar()
    st.title("🏠 Home"); st.write("### Bem-vindo à Calculadora Comparativa de SLA!")
    st.write("Esta ferramenta ajuda a calcular e comparar diferentes cenários de custos baseados nos SLAs de serviço.")
    if st.button("🖩 Acessar Calculadora", on_click=ir_para_calculadora, type="primary"): pass

elif st.session_state.tela == "calculadora":
    renderizar_sidebar()
    st.title("📊 Calculadora Comparativa de Cenários")
    
    df_base = carregar_base()
    if df_base is None: st.error("❌ Arquivo 'Base De Clientes Faturamento.xlsx' não encontrado."); st.stop()
    
    if st.session_state.cenarios:
        st.markdown("---"); st.header("📈 Cenários Calculados")
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
        pdf_buffer = gerar_pdf(df_cenarios, melhor)
        st.download_button("📥 Baixar Relatório PDF", pdf_buffer, "comparacao_cenarios_sla.pdf", "application/pdf")
        st.button("🔄 Reiniciar e Fazer Nova Comparação", on_click=limpar_dados, use_container_width=True, type="primary")

    else:
        st.markdown("---")
        st.header(f"📝 Preencher Dados para o Cenário {len(st.session_state.cenarios) + 1}")
        
        with st.expander("🔍 Consultar Clientes e Placas"):
            df_display = df_base[['CLIENTE', 'PLACA', 'VALOR MENSALIDADE']].copy()
            df_display['VALOR MENSALidade'] = df_display['VALOR MENSALIDADE'].apply(formatar_moeda)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

        col_form, col_pecas = st.columns([2, 1])
        with col_form:
            # CORREÇÃO: Removido o parâmetro 'key' para evitar conflitos de estado
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
                            cenario = calcular_cenario(cliente_info["cliente"], placa.upper(), entrada, saida, feriados, servico, st.session_state.pecas_atuais, cliente_info["mensalidade"])
                            st.session_state.cenarios.append(cenario)
                            st.session_state.pecas_atuais = []
                            st.rerun()
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
