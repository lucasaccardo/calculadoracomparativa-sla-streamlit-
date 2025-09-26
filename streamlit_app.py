# streamlit_app.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# --- CONFIGURAÇÃO DA PÁGINA E TEMA ---
st.set_page_config(
    page_title="Calculadora SLA | Vamos",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="auto"
)

# --- Funções Auxiliares (sem alterações) ---
@st.cache_data
def carregar_base():
    try:
        return pd.read_excel("Base De Clientes Faturamento.xlsx")
    except FileNotFoundError:
        return None

def buscar_placa(df_base):
    placa_digitada = st.session_state.input_placa.strip().upper()
    if not placa_digitada:
        st.session_state.cliente_info = None
        return
    cliente_row = df_base[df_base["PLACA"].astype(str).str.upper() == placa_digitada]
    if not cliente_row.empty:
        st.session_state.cliente_info = {
            "cliente": cliente_row.iloc[0]["CLIENTE"],
            "mensalidade": moeda_para_float(cliente_row.iloc[0]["VALOR MENSALIDADE"])
        }
    else:
        st.session_state.cliente_info = None

def calcular_dias_uteis(data_inicio, data_fim, feriados=0):
    dias = 0; data_atual = data_inicio + timedelta(days=1)
    while data_atual <= data_fim:
        if data_atual.weekday() < 5: dias += 1
        data_atual += timedelta(days=1)
