import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import re
import time
import random

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Options Screener Ultimate")

# --- BASE DE DATOS MAESTRA ---
CEDEAR_DATABASE = {
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX',
    'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'XLE', 'XLF', 'ARKK', 'EWZ', 'GLD', 'SLV',
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'AMD', 'NFLX', 'INTC', 'QCOM', 'AVGO', 'CRM', 'CSCO', 'ORCL', 'IBM', 'UBER', 'ABNB', 'PLTR', 'SPOT', 'TSM', 'MU', 'ARM', 'SMCI',
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B', 'PYPL', 'SQ',
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'PG', 'JNJ', 'PFE', 'MRK', 'LLY', 'XOM', 'CVX', 'SLB', 'BA', 'CAT', 'MMM', 'GE', 'DE', 'F', 'GM', 'TM',
    'COIN', 'MSTR', 'HUT', 'BITF',
    'PBR', 'VALE', 'ITUB', 'BBD', 'BABA', 'JD', 'BIDU'
}

# --- FUNCIONES ---
def get_sentiment_label(ratio):
    if ratio < 0.7: return "🚀 ALCISTA"
    elif ratio > 1.0: return "🐻 BAJISTA"
    else: return "⚖️ NEUTRAL"

def generate_links(ticker):
    yahoo_link = f"https://finance.yahoo.com/quote/{ticker}/options"
    tv_link = f"https://es.tradingview.com/chart/?symbol=BCBA%3A{ticker}"
    return yahoo_link, tv_link

def check_proximity(price, wall_price, threshold_pct):
    if wall_price == 0 or price == 0: return False
    distance = abs(price - wall_price) / price * 100
    return distance <= threshold_pct

@st.cache_data(ttl=900)
def analyze_options_chain(ticker):
    try:
        # 1. INTENTO DE DESCARGA DE PRECIO (MÉTODO ROBUSTO)
        # Usamos yf.download en lugar de Ticker.fast_info porque es menos propenso a fallar en cloud
        try:
            df_price = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
            if df_price.empty:
                return {'Ticker': ticker, 'Error': 'No Price Data'}
            current_price = df_price['Close'].iloc[-1]
            if isinstance(current_price, pd.Series): 
                current_price = current_price.iloc[0]
            current_price = float(current_price)
        except Exception as e:
            return {'Ticker': ticker, 'Error': f'Price Error: {str(e)}'}

        # 2. INTENTO DE OPCIONES
        tk = yf.Ticker(ticker)
        try:
            exps = tk.options
        except Exception as e:
            return {'Ticker': ticker, 'Error': f'Options Block: {str(e)}'}
            
        if not exps: 
            return {'Ticker': ticker, 'Error': 'No Expirations Found'}
        
        target_date = None
        calls, puts = pd.DataFrame(), pd.DataFrame()
        
        # Iteramos fechas
        for date in exps[:2]: # Solo miramos 2 para ir rápido
            try:
                opts = tk.option_chain(date)
                c, p = opts.calls, opts.puts
                if not c.empty or not p.empty:
                    calls, puts = c, p
                    target_date = date
                    break
            except: continue
        
        if target_date is None: 
            return {'Ticker': ticker, 'Error': 'Empty Chains'}
        
        # 3. CÁLCULOS
        total_call_oi = calls['openInterest'].sum()
        total_put_oi = puts['openInterest'].sum()
        if total_call_oi == 0: total_call_oi = 1
        
        pc_ratio = total_put_oi / total_call_oi
        
        call_wall = 0
        put_wall = 0
        
        if not calls.empty:
            call_wall = calls.loc[calls['openInterest'].idxmax()]['strike']
        if not puts.empty:
            put_wall = puts.loc[puts['openInterest'].idxmax()]['strike']
        
        market_consensus = (call_wall + put_wall) / 2
        calculation_price = current_price
        
        # Validación de integridad
        data_quality = "OK"
        if market_consensus > 0 and current_price > 0:
            if abs(current_price - market_consensus) / market_consensus > 0.7:
                data_quality = "ERROR_PRECIO"

        strikes = sorted(list(set(calls['strike'].tolist() + puts['strike'].tolist())))
        # Filtro de strikes
        strikes = [s for s in strikes if calculation_price * 0.5 < s < calculation_price * 1.5]
        
        cash_values = []
        for strike in strikes:
            intrinsic_calls = calls.apply(lambda row: max(0, strike - row['strike']) * row.get('openInterest', 0), axis=1).sum()
            intrinsic_puts = puts.apply(lambda row: max(0, row['strike'] - strike) * row.get('openInterest', 0), axis=1).sum()
            cash_values.append(intrinsic_calls + intrinsic_puts)
        
        max_pain = strikes[np.argmin(cash_values)] if cash_values else calculation_price
        
        return {
            'Ticker': ticker, 'Price': current_price, 'Max_Pain': max_pain,
            'PC_Ratio': pc_ratio, 'Call_OI': total_call_oi, 'Put_OI': total_put_oi,
            'Expiration': target_date,
            'Call_Wall': call_wall, 'Put_Wall': put_wall,
            'Data_Quality': data_quality, 
            'Calls_DF': calls, 'Puts_DF': puts,
            'Error': 'OK'
        }
    except Exception as e:
        return {'Ticker': ticker, 'Error': f'Critial: {str(e)}'}

def get_batch_analysis(ticker_list):
    results = []
    prog = st.progress(0, text="Iniciando...")
    total = len(ticker_list)
    status_box = st.empty()
    
    for i, t in enumerate(ticker_list):
        status_box.caption(f"🔎 Analizando: {t}")
        data = analyze_options_chain(t)
        results.append(data)
        
        # Si dio error, dormimos más tiempo (backoff)
        if data['Error'] != 'OK':
            time.sleep(1.0) 
        else:
            time.sleep(0.1) # Si fue bien, vamos más rápido
            
        prog.progress((i + 1) / total)
        
    prog.empty()
    status_box.empty()
    return results

# --- INTERFAZ ---
st.title("🌎 SystemaTrader: Escáner Global (Modo Diagnóstico)")

if 'analysis_results' not in st.session_state:
    st.session_state['analysis_results'] = []

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Preparar lotes
    all_tickers = sorted(list(CEDEAR_DATABASE))
    batch_size = 10 # Bajamos a 10 para probar
    batches = [all_tickers[i:i + batch_size] for i in range(0, len(all_tickers), batch_size)]
    batch_labels = [f"Lote {i+1} ({b[0]} - {b[-1]})" for i, b in enumerate(batches)]
    
    selected_batch_idx = st.selectbox("Seleccionar Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    accumulate = st.checkbox("➕ Acumular", value=True)
    
    if st.button("🚀 Escanear Lote"):
        target_tickers = batches[selected_batch_idx]
        with st.spinner(f"Analizando {len(target_tickers)} activos..."):
            new_results = get_batch_analysis(target_tickers)
            if accumulate:
                # Evitar duplicados
                existing = {r['Ticker'] for r in st.session_state['analysis_results']}
                for item in new_results:
                    if item['Ticker'] not in existing:
                        st.session_state['analysis_results'].append(item)
            else:
                st.session_state['analysis_results'] = new_results

    if st.button("Limpiar"):
        st.session_state['analysis_results'] = []

# --- RESULTADOS ---
if st.session_state['analysis_results']:
    df = pd.DataFrame(st.session_state['analysis_results'])
    
    # Separar Éxitos de Fallos
    df_ok = df[df['Error'] == 'OK'].copy()
    df_fail = df[df['Error'] != 'OK'].copy()
    
    st.metric("Tasa de Éxito", f"{len(df_ok)} / {len(df)}")
    
    if not df_fail.empty:
        with st.expander("⚠️ Ver Errores de Conexión (Diagnóstico)", expanded=True):
            st.dataframe(df_fail[['Ticker', 'Error']], use_container_width=True)
            st.caption("Si ves 'Price Error' o 'Options Block', Yahoo está bloqueando la IP de Streamlit.")

    if not df_ok.empty:
        df_ok['Sentimiento'] = df_ok['PC_Ratio'].apply(get_sentiment_label)
        
        st.subheader("✅ Resultados Válidos")
        st.dataframe(
            df_ok[['Ticker', 'Price', 'Max_Pain', 'PC_Ratio', 'Call_Wall', 'Put_Wall', 'Sentimiento']],
            column_config={
                "Ticker": "Activo",
                "Price": st.column_config.NumberColumn("Precio", format="$%.2f"),
                "Max_Pain": st.column_config.NumberColumn("Max Pain", format="$%.2f"),
                "Call_Wall": st.column_config.NumberColumn("Techo", format="$%.2f"),
                "Put_Wall": st.column_config.NumberColumn("Piso", format="$%.2f")
            },
            use_container_width=True, height=500
        )
    else:
        st.error("Ningún activo pudo ser procesado correctamente.")
