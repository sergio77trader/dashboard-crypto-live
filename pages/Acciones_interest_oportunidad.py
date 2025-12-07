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

# --- PROTOCOLO DE CONEXIÓN ROBUSTA (V13.0) ---
def get_robust_session():
    """
    Crea una sesión con reintentos automáticos (Retry Strategy).
    Si Yahoo da error 429 (Too Many Requests), espera y reintenta.
    """
    session = requests.Session()
    
    # Estrategia de reintento: 3 intentos totales
    # backoff_factor=1 significa: espera 1s, luego 2s, luego 4s...
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    # Headers rotativos básicos (Chrome estándar)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    })
    return session

@st.cache_data(ttl=900)
def analyze_options_chain(ticker):
    try:
        # Inyectamos la sesión robusta
        session = get_robust_session()
        tk = yf.Ticker(ticker, session=session)
        
        # 1. PRECIO
        current_price = 0
        try:
            # Fast info suele ser lo primero que falla con throttling
            if hasattr(tk, 'fast_info') and tk.fast_info.last_price:
                current_price = float(tk.fast_info.last_price)
        except: pass
        
        # Fallback a histórico si fast_info falla
        if current_price == 0:
            try:
                hist = tk.history(period="5d")
                if not hist.empty: current_price = hist['Close'].iloc[-1]
            except: pass
        
        if current_price == 0: return None

        # 2. OPCIONES (El punto crítico)
        try:
            exps = tk.options
        except:
            return None
            
        if not exps: return None
        
        target_date = None
        calls, puts = pd.DataFrame(), pd.DataFrame()
        
        # Miramos hasta 3 vencimientos
        for date in exps[:3]:
            try:
                opts = tk.option_chain(date)
                c, p = opts.calls, opts.puts
                if not c.empty or not p.empty:
                    calls, puts = c, p
                    target_date = date
                    break
            except:
                continue
        
        if target_date is None: return None
        
        # 3. CÁLCULOS
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
    prog = st.progress(0, text="Iniciando motor de extracción...")
    total = len(ticker_list)
    
    # Creamos un contenedor vacío para mostrar logs en vivo
    status_log = st.empty()
    
    for i, t in enumerate(ticker_list):
        # Actualizamos log visual
        status_log.caption(f"⏳ Procesando: **{t}** ({i+1}/{total})")
        
        data = analyze_options_chain(t)
        if data: 
            results.append(data)
        
        # --- RETARDO ALEATORIO HUMANIZADO ---
        # No usamos tiempo fijo. Usamos aleatorio entre 0.5s y 1.5s
        # Esto engaña mejor a los algoritmos de bloqueo que un intervalo fijo
        sleep_time = random.uniform(0.5, 1.5)
        time.sleep(sleep_time)
        
        prog.progress((i + 1) / total)
        
    prog.empty()
    status_log.empty()
    return results

# --- INTERFAZ ---
st.title("🌎 SystemaTrader: Escáner Global de Oportunidades")

if 'analysis_results' not in st.session_state:
    st.session_state['analysis_results'] = {}
    st.session_state['current_view'] = "Esperando escaneo..."

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuración")
    proximity_threshold = st.slider("Alerta Proximidad (%)", 1, 10, 3)
    
    st.divider()
    
    # SECCIÓN 1
    st.header("1. Escaneo Masivo")
    st.warning("⚠️ El escaneo masivo es lento en la nube para garantizar que lleguen todos los datos.")
    if st.button("ESCANEAR BASE DE DATOS ENTERA", type="primary"):
        st.session_state['current_view'] = "Mercado Completo (ADRs + CEDEARs)"
        sorted_tickers = sorted(list(CEDEAR_DATABASE))
        with st.spinner("Ejecutando 'The Bulldozer' Protocol..."):
            st.session_state['analysis_results'] = get_batch_analysis(sorted_tickers)

    st.divider()

    # SECCIÓN 2
    st.header("2. Lista Personalizada")
    custom_input = st.text_area("Ingresa Activos (Ej: AAPL, MELI, GGAL):", height=100)
    
    if st.button("🎯 ANALIZAR MI LISTA"):
        if custom_input:
            custom_tickers = re.split(r'[,\s\n]+', custom_input)
            custom_tickers = [t.strip().upper() for t in custom_tickers if t.strip()]
            
            if custom_tickers:
                st.session_state['current_view'] = "Lista Personalizada"
                with st.spinner(f"Analizando {len(custom_tickers)} activos..."):
                    st.session_state['analysis_results'] = get_batch_analysis(custom_tickers)
            else:
                st.error("Lista inválida.")

    st.markdown("---")
    st.caption("SystemaTrader v13.0 | Retry & Backoff Engine")

# --- RESULTADOS ---
st.subheader(f"1️⃣ Resultados: {st.session_state.get('current_view', 'Sin Datos')}")

if st.session_state['analysis_results']:
    results = st.session_state['analysis_results']
    df_table = pd.DataFrame(results)
    
    if not df_table.empty:
        st.success(f"✅ Extracción completada: {len(df_table)} activos recuperados.")

        def get_alert_status(row):
            if row['Data_Quality'] == 'ERROR_PRECIO': return "❌ ERROR DATA"
            status = []
            if check_proximity(row['Price'], row['Call_Wall'], proximity_threshold): status.append("🧱 TECHO")
            if check_proximity(row['Price'], row['Put_Wall'], proximity_threshold): status.append("🟢 PISO")
            return " + ".join(status) if status else "OK"

        df_display = df_table.copy()
        df_display['Alerta'] = df_display.apply(get_alert_status, axis=1)
        df_display['Sentimiento'] = df_display['PC_Ratio'].apply(get_sentiment_label)
        
        df_display['% Techo'] = ((df_display['Call_Wall'] - df_display['Price']) / df_display['Price']) * 100
        df_display['% Piso'] = ((df_display['Put_Wall'] - df_display['Price']) / df_display['Price']) * 100

        col_filter1, col_filter2 = st.columns([1, 4])
        with col_filter1:
            show_only_alerts = st.checkbox("🔥 Mostrar solo Alertas", value=False)
        
        if show_only_alerts:
            df_final = df_display[df_display['Alerta'] != "OK"]
        else:
            df_final = df_display.sort_values(by=['Alerta', 'Ticker'], ascending=[False, True])

        st.dataframe(
            df_final[['Ticker', 'Price', 'Max_Pain', 'Alerta', 'Call_Wall', '% Techo', 'Put_Wall', '% Piso', 'Sentimiento']],
            column_config={
                "Ticker": "Activo", 
                "Price": st.column_config.NumberColumn("Precio", format="$%.2f"),
                "Max_Pain": st.column_config.NumberColumn("Max Pain", format="$%.2f"),
                "Alerta": st.column_config.TextColumn("Estado"),
                "Call_Wall": st.column_config.NumberColumn("Techo", format="$%.2f"),
                "% Techo": st.column_config.NumberColumn("Dist. Techo %", format="%.2f%%"),
                "Put_Wall": st.column_config.NumberColumn("Piso", format="$%.2f"),
                "% Piso": st.column_config.NumberColumn("Dist. Piso %", format="%.2f%%"),
            },
            use_container_width=True, hide_index=True, height=600
        )
    else: st.error("No se pudieron recuperar datos. Yahoo ha bloqueado temporalmente la IP del servidor. Intenta en 10 minutos.")

    # --- DETALLE ---
    st.divider()
    st.subheader("2️⃣ Análisis Profundo")
    ticker_options = sorted([r['Ticker'] for r in results])
    if ticker_options:
        selected_ticker = st.selectbox("Selecciona Activo:", ticker_options)
        asset_data = next((i for i in results if i["Ticker"] == selected_ticker), None)
        
        if asset_data:
            if asset_data['Data_Quality'] == 'ERROR_PRECIO':
                st.error(f"🚨 **ERROR DE PRECIO:** Yahoo reporta ${asset_data['Price']:.2f} pero el mercado de opciones apunta a ${asset_data['Max_Pain']:.2f}.")

            k1, k2, k3, k4, k5 = st.columns(5)
            
            dist_max_pain = ((asset_data['Max_Pain'] - asset_data['Price']) / asset_data['Price']) * 100
            dist_techo = ((asset_data['Call_Wall'] - asset_data['Price']) / asset_data['Price']) * 100
            dist_piso = ((asset_data['Put_Wall'] - asset_data['Price']) / asset_data['Price']) * 100

            k1.metric("Precio", f"${asset_data['Price']:.2f}")
            k2.metric("Max Pain (Imán)", f"${asset_data['Max_Pain']:.2f}", delta=f"{dist_max_pain:.1f}%", delta_color="off")
            k3.metric("Sentimiento", get_sentiment_label(asset_data['PC_Ratio']), delta=f"Ratio: {asset_data['PC_Ratio']:.2f}")
            k4.metric("Techo (Resistencia)", f"${asset_data['Call_Wall']:.2f}", delta=f"{dist_techo:.1f}%", delta_color="normal")
            k5.metric("Piso (Soporte)", f"${asset_data['Put_Wall']:.2f}", delta=f"{dist_piso:.1f}%", delta_color="normal")

            c1, c2 = st.columns([1, 2])
            with c1:
                labels = ['Calls', 'Puts']
                values = [asset_data['Call_OI'], asset_data['Put_OI']]
                fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.4, marker=dict(colors=['#00CC96', '#EF553B']))])
                fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, showlegend=False)
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with c2:
                calls, puts = asset_data['Calls_DF'], asset_data['Puts_DF']
                center_price = asset_data['Calculated_Price_Ref']
                min_s, max_s = center_price * 0.85, center_price * 1.15
                c_filt = calls[(calls['strike'] >= min_s) & (calls['strike'] <= max_s)]
                p_filt = puts[(puts['strike'] >= min_s) & (puts['strike'] <= max_s)]
                
                fig_wall = go.Figure()
                fig_wall.add_trace(go.Bar(x=c_filt['strike'], y=c_filt['openInterest'], name='Calls (Techo)', marker_color='#00CC96'))
                fig_wall.add_trace(go.Bar(x=p_filt['strike'], y=p_filt['openInterest'], name='Puts (Piso)', marker_color='#EF553B'))
                
                if asset_data['Data_Quality'] == "OK":
                    fig_wall.add_vline(x=asset_data['Price'], line_dash="dash", line_color="white", annotation_text="Precio")
                fig_wall.add_vline(x=asset_data['Max_Pain'], line_dash="dash", line_color="yellow", annotation_text="Max Pain")
                
                fig_wall.update_layout(barmode='overlay', height=350, margin=dict(t=20), xaxis_title="Strike ($)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_wall, use_container_width=True)
            
            link_yahoo, link_tv = generate_links(selected_ticker)
            st.markdown(f"[Auditar en Yahoo]({link_yahoo}) | [Ver Gráfico]({link_tv})")

else:
    st.info("Dale al botón 'ESCANEAR' en la barra lateral.")
