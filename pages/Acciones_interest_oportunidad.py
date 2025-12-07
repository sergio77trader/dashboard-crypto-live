import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import time
import requests

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader Debugger")

# --- BASE DE DATOS ---
CEDEAR_DATABASE = sorted([
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'AMD', 'NFLX', 
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'MELI',
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'XOM', 'CVX', 'JPM', 'BAC', 'C', 'WFC',
    'SPY', 'QQQ', 'IWM', 'EEM', 'XLE', 'XLF', 'GLD', 'SLV', 'ARKK'
])

# --- SESIÓN FAKE (Navegador) ---
def get_session():
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'})
    return s

# --- MOTOR DE ANÁLISIS (CON REPORTES DE ERROR) ---
def analyze_ticker_debug(ticker):
    log = {"Ticker": ticker, "Status": "Unknown", "Price": 0.0, "Details": ""}
    
    try:
        # 1. PRECIO (Usando download, mas lento pero seguro)
        df = yf.download(ticker, period="1d", progress=False, session=get_session())
        if df.empty:
            log["Status"] = "❌ Error Precio"
            log["Details"] = "Yahoo devolvió DataFrame vacío."
            return log
            
        current_price = df['Close'].iloc[-1]
        # Manejo de formatos raros de pandas
        if isinstance(current_price, pd.Series): current_price = current_price.iloc[0]
        log["Price"] = float(current_price)

        # 2. OPCIONES
        tk = yf.Ticker(ticker, session=get_session())
        try:
            exps = tk.options
        except Exception as e:
            log["Status"] = "❌ Bloqueo Options"
            log["Details"] = str(e)
            return log
            
        if not exps:
            log["Status"] = "⚠️ Sin Opciones"
            return log

        # Buscamos datos en el primer vencimiento
        found = False
        for date in exps[:2]:
            try:
                opt = tk.option_chain(date)
                calls, puts = opt.calls, opt.puts
                if not calls.empty:
                    # CÁLCULOS BÁSICOS
                    total_call = calls['openInterest'].sum()
                    total_put = puts['openInterest'].sum()
                    
                    # Max Pain Simplificado
                    strikes = calls['strike'].tolist()
                    call_wall = calls.loc[calls['openInterest'].idxmax()]['strike']
                    
                    log["Max_Pain"] = call_wall # Usamos Call Wall como proxy rápido
                    log["Call_OI"] = total_call
                    log["Put_OI"] = total_put
                    log["Status"] = "✅ OK"
                    found = True
                    break
            except: continue
        
        if not found:
            log["Status"] = "⚠️ Cadena Vacía"
            
    except Exception as e:
        log["Status"] = "🔥 Crash"
        log["Details"] = str(e)
        
    return log

# --- INTERFAZ ---
st.title("🛠️ SystemaTrader: Modo Diagnóstico")

# Inicializar memoria
if "debug_results" not in st.session_state:
    st.session_state["debug_results"] = []

with st.sidebar:
    st.header("Control de Lotes")
    
    # Crear lotes de 5 (Muy pequeños para probar)
    batch_size = 5
    batches = [CEDEAR_DATABASE[i:i + batch_size] for i in range(0, len(CEDEAR_DATABASE), batch_size)]
    batch_labels = [f"Lote {i+1}: {b[0]} - {b[-1]}" for i, b in enumerate(batches)]
    
    sel_batch = st.selectbox("Elige Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    if st.button("▶️ EJECUTAR ESCANEO (DEBUG)"):
        targets = batches[sel_batch]
        status_box = st.empty()
        
        for t in targets:
            status_box.info(f"⏳ Procesando {t}...")
            # Analizamos
            data = analyze_ticker_debug(t)
            # Guardamos en memoria
            st.session_state["debug_results"].append(data)
            # Pausa obligatoria
            time.sleep(0.5)
            
        status_box.success("Lote finalizado.")

    if st.button("🗑️ Limpiar Resultados"):
        st.session_state["debug_results"] = []
        st.rerun()

# --- RESULTADOS ---
st.subheader("Bitácora de Ejecución")

if st.session_state["debug_results"]:
    df = pd.DataFrame(st.session_state["debug_results"])
    
    # Colores según estado
    def color_status(val):
        color = 'red' if 'Error' in val or 'Crash' in val or 'Bloqueo' in val else 'green'
        if 'Sin' in val: color = 'orange'
        return f'color: {color}'

    st.dataframe(df, use_container_width=True)
    
    st.divider()
    
    # DIAGNÓSTICO DEL SISTEMA
    errores = len(df[df['Status'].str.contains('Error|Bloqueo|Crash')])
    total = len(df)
    
    if errores == total:
        st.error("🚨 DIAGNÓSTICO: BLOQUEO TOTAL DE IP.")
        st.markdown("""
        **Interpretación:**
        Yahoo Finance ha puesto la IP de este servidor en lista negra.
        
        **Soluciones:**
        1. Esperar 24hs.
        2. Usar el script localmente en tu PC.
        """)
    elif errores > 0:
        st.warning(f"⚠️ Inestabilidad: {errores} fallos de {total} intentos.")
    else:
        st.success("✅ Sistema Operativo. Los datos fluyen.")

else:
    st.info("Selecciona un lote pequeño y ejecuta para ver qué está pasando.")
