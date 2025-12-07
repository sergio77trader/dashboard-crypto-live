import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import re
import time
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

STOCK_GROUPS = {
    '🇦🇷 Argentina (ADRs)': ['GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI'],
    '🇺🇸 ETFs (Índices)': ['SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'XLE', 'XLF', 'ARKK', 'EWZ'],
    '🇺🇸 Magnificent 7 + Tech': ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NFLX', 'CRM'],
    '🇺🇸 Semiconductores & AI': ['AMD', 'INTC', 'QCOM', 'AVGO', 'TSM', 'MU', 'ARM', 'SMCI', 'PLTR'],
    '🇺🇸 Financiero': ['JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'BRK-B', 'PYPL'],
    '🇺🇸 Consumo & Dividendos': ['KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'PG', 'JNJ', 'XOM', 'CVX'],
    '🇺🇸 Crypto & Volatilidad': ['COIN', 'MSTR', 'UBER', 'ABNB', 'SQ', 'TSLA'],
    '🌎 Brasil & China': ['PBR', 'VALE', 'ITUB', 'BABA', 'JD', 'BIDU']
}

# --- FUNCIONES AUXILIARES ---
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

# --- PROTOCOLO DE CONEXIÓN ROBUSTA (V14.0) ---
def get_robust_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    return session

@st.cache_data(ttl=900)
def analyze_options_chain(ticker):
    try:
        session = get_robust_session()
        tk = yf.Ticker(ticker, session=session)
        
        # 1. Obtener Precio (Con reintentos internos)
        current_price = 0
        try:
            if hasattr(tk, 'fast_info') and tk.fast_info.last_price:
                current_price = float(tk.fast_info.last_price)
        except: pass
        
        if current_price == 0:
            try:
                hist = tk.history(period="5d")
                if not hist.empty: current_price = hist['Close'].iloc[-1]
            except: pass
            
        if current_price == 0: return None # No se pudo obtener precio

        # 2. Obtener Cadena de Opciones
        try:
            exps = tk.options
        except: return None
            
        if not exps: return None
        
        # Estrategia Multi-Vencimiento (Miramos los primeros 3)
        target_date = None
        calls, puts = pd.DataFrame(), pd.DataFrame()
        
        for date in exps[:3]:
            try:
                opts = tk.option_chain(date)
                c, p = opts.calls, opts.puts
                if not c.empty or not p.empty:
                    calls, puts = c, p
                    target_date = date
                    break
            except: continue
        
        if target_date is None: return None
        
        # 3. Cálculos Métricos
        total_call_oi = calls['openInterest'].sum()
        total_put_oi = puts['openInterest'].sum()
        if total_call_oi == 0: total_call_oi = 1
        
        pc_ratio = total_put_oi / total_call_oi
        
        call_wall = calls.loc[calls['openInterest'].idxmax()]['strike'] if not calls.empty else 0
        put_wall = puts.loc[puts['openInterest'].idxmax()]['strike'] if not puts.empty else 0
        
        data_quality = "OK"
        market_consensus = (call_wall + put_wall) / 2
        calculation_price = current_price
        
        if market_consensus > 0 and current_price > 0:
            if abs(current_price - market_consensus) / market_consensus > 0.6:
                data_quality = "ERROR_PRECIO"

        strikes = sorted(list(set(calls['strike'].tolist() + puts['strike'].tolist())))
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
            'Data_Quality': data_quality, 'Calculated_Price_Ref': calculation_price,
            'Calls_DF': calls, 'Puts_DF': puts
        }
    except Exception: return None

def get_batch_analysis(ticker_list):
    results = []
    prog = st.progress(0, text="Iniciando...")
    total = len(ticker_list)
    status_log = st.empty()
    
    for i, t in enumerate(ticker_list):
        status_log.caption(f"⏳ Procesando: **{t}**")
        data = analyze_options_chain(t)
        if data: 
            results.append(data)
        
        # Pausa aleatoria para parecer humano
        time.sleep(random.uniform(0.3, 0.8))
        prog.progress((i + 1) / total)
        
    prog.empty()
    status_log.empty()
    return results

# --- INTERFAZ DE USUARIO ---
st.title("🌎 SystemaTrader: Escáner de Opciones (Anti-Bloqueo)")

# Inicializar Estado de Resultados Acumulados
if 'analysis_results' not in st.session_state:
    st.session_state['analysis_results'] = [] # Lista vacía inicial
if 'current_view' not in st.session_state:
    st.session_state['current_view'] = "Esperando..."

# --- SIDEBAR: CENTRO DE MANDO ---
with st.sidebar:
    st.header("⚙️ Configuración")
    proximity_threshold = st.slider("Alerta Proximidad (%)", 1, 10, 3)
    
    st.divider()
    
    # MODO 1: GRUPOS PREDEFINIDOS
    st.header("1. Grupos Rápidos")
    sel_group = st.selectbox("Elegir Grupo:", list(STOCK_GROUPS.keys()))
    if st.button("🔎 Escanear Grupo"):
        st.session_state['analysis_results'] = [] # Limpiamos anterior
        st.session_state['current_view'] = sel_group
        st.session_state['analysis_results'] = get_batch_analysis(STOCK_GROUPS[sel_group])

    st.divider()

    # MODO 2: FRAGMENTACIÓN (LA SOLUCIÓN CLAVE)
    st.header("2. Escaneo Fragmentado")
    st.info("Divide y vencerás. Escanea por lotes para evitar bloqueos.")
    
    # Preparar lotes
    all_tickers = sorted(list(CEDEAR_DATABASE))
    batch_size = 20 # Tamaño seguro
    # Dividir lista en chunks
    batches = [all_tickers[i:i + batch_size] for i in range(0, len(all_tickers), batch_size)]
    
    batch_labels = [f"Lote {i+1} ({b[0]} - {b[-1]})" for i, b in enumerate(batches)]
    
    selected_batch_idx = st.selectbox("Seleccionar Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    accumulate = st.checkbox("➕ Acumular Resultados", value=True, help="Si marcas esto, los nuevos escaneos se suman a la tabla. Si no, la reemplazan.")
    
    if st.button("🚀 Escanear Lote Seleccionado"):
        target_tickers = batches[selected_batch_idx]
        st.session_state['current_view'] = f"Lote {selected_batch_idx + 1}"
        
        with st.spinner(f"Analizando {len(target_tickers)} activos..."):
            new_results = get_batch_analysis(target_tickers)
            
            if accumulate:
                # Evitar duplicados si se escanea lo mismo
                existing_tickers = {r['Ticker'] for r in st.session_state['analysis_results']}
                for item in new_results:
                    if item['Ticker'] not in existing_tickers:
                        st.session_state['analysis_results'].append(item)
                st.success(f"Lote agregado. Total activos: {len(st.session_state['analysis_results'])}")
            else:
                st.session_state['analysis_results'] = new_results

    if st.button("🗑️ Limpiar Tabla"):
        st.session_state['analysis_results'] = []
        st.rerun()

    st.divider()
    
    # MODO 3: MANUAL
    st.header("3. Manual")
    custom_in = st.text_area("Tickers:", height=70)
    if st.button("Analizar Manual"):
        if custom_in:
            manual_tickers = [t.strip().upper() for t in re.split(r'[,\s]+', custom_in) if t.strip()]
            st.session_state['current_view'] = "Manual"
            st.session_state['analysis_results'] = get_batch_analysis(manual_tickers)

# --- VISUALIZACIÓN DE RESULTADOS ---
st.subheader(f"📊 Resultados: {len(st.session_state['analysis_results'])} Activos Cargados")

if st.session_state['analysis_results']:
    results = st.session_state['analysis_results']
    df_table = pd.DataFrame(results)
    
    if not df_table.empty:
        # Lógica de Alertas
        def get_alert(row):
            if row['Data_Quality'] == 'ERROR_PRECIO': return "❌ ERROR"
            alerts = []
            if check_proximity(row['Price'], row['Call_Wall'], proximity_threshold): alerts.append("🧱 TECHO")
            if check_proximity(row['Price'], row['Put_Wall'], proximity_threshold): alerts.append("🟢 PISO")
            return " + ".join(alerts) if alerts else "OK"

        df_show = df_table.copy()
        df_show['Alerta'] = df_show.apply(get_alert, axis=1)
        df_show['Sentimiento'] = df_show['PC_Ratio'].apply(get_sentiment_label)
        
        # Filtros visuales
        col_f1, col_f2 = st.columns([1, 4])
        with col_f1:
            only_alerts = st.checkbox("🔥 Solo Alertas", value=False)
        
        if only_alerts:
            df_final = df_show[df_show['Alerta'] != "OK"]
        else:
            df_final = df_show.sort_values(by=['Alerta', 'Ticker'], ascending=[False, True])

        # Tabla Principal
        st.dataframe(
            df_final[['Ticker', 'Price', 'Max_Pain', 'Alerta', 'Call_Wall', 'Put_Wall', 'Sentimiento']],
            column_config={
                "Ticker": "Activo",
                "Price": st.column_config.NumberColumn("Precio", format="$%.2f"),
                "Max_Pain": st.column_config.NumberColumn("Max Pain", format="$%.2f"),
                "Call_Wall": st.column_config.NumberColumn("Techo", format="$%.2f"),
                "Put_Wall": st.column_config.NumberColumn("Piso", format="$%.2f")
            },
            use_container_width=True, hide_index=True, height=500
        )
    else:
        st.warning("El escaneo no devolvió datos válidos. Intenta con otro lote.")

    # --- DETALLE INDIVIDUAL ---
    st.divider()
    st.subheader("🔍 Microscopio de Gamma")
    
    opts = sorted([r['Ticker'] for r in results])
    if opts:
        sel = st.selectbox("Seleccionar Activo:", opts)
        dat = next((r for r in results if r['Ticker'] == sel), None)
        
        if dat:
            # Enlaces
            l_y, l_t = generate_links(sel)
            st.markdown(f"🔗 [Yahoo Finance]({l_y}) | [TradingView]({l_t})")
            
            # Métricas
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Precio", f"${dat['Price']:.2f}")
            k2.metric("Max Pain", f"${dat['Max_Pain']:.2f}")
            k3.metric("Ratio P/C", f"{dat['PC_Ratio']:.2f}")
            k4.metric("Techo", f"${dat['Call_Wall']:.2f}")
            k5.metric("Piso", f"${dat['Put_Wall']:.2f}")
            
            # Gráficos
            c1, c2 = st.columns([1, 2])
            with c1:
                fig_pie = go.Figure(data=[go.Pie(labels=['Calls', 'Puts'], values=[dat['Call_OI'], dat['Put_OI']], hole=.4)])
                fig_pie.update_layout(height=250, margin=dict(t=0,b=0,l=0,r=0), showlegend=False)
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with c2:
                # Graficar Muros
                c_df, p_df = dat['Calls_DF'], dat['Puts_DF']
                pr = dat['Price']
                # Zoom inteligente (20% arriba y abajo del precio)
                c_filt = c_df[(c_df['strike'] > pr*0.8) & (c_df['strike'] < pr*1.2)]
                p_filt = p_df[(p_df['strike'] > pr*0.8) & (p_df['strike'] < pr*1.2)]
                
                fig = go.Figure()
                fig.add_trace(go.Bar(x=c_filt['strike'], y=c_filt['openInterest'], name='Calls', marker_color='#00CC96'))
                fig.add_trace(go.Bar(x=p_filt['strike'], y=p_filt['openInterest'], name='Puts', marker_color='#EF553B'))
                fig.add_vline(x=pr, line_dash="dash", line_color="white", annotation_text="Precio")
                fig.add_vline(x=dat['Max_Pain'], line_dash="dash", line_color="yellow", annotation_text="Max Pain")
                fig.update_layout(barmode='overlay', height=350, margin=dict(t=20))
                st.plotly_chart(fig, use_container_width=True)
