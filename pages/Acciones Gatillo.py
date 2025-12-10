import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import time
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader 360: Master Database")

# --- ESTILOS CSS ---
st.markdown("""
<style>
    div[data-testid="stMetric"], .metric-card {
        background-color: transparent !important;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    @media (prefers-color-scheme: dark) {
        div[data-testid="stMetric"], .metric-card {
            border: 1px solid #404040;
        }
    }
    .big-score { font-size: 2.5rem; font-weight: 800; margin: 0; }
    .score-label { font-size: 0.9rem; font-weight: 500; opacity: 0.8; }
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS MAESTRA ---
DB_CATEGORIES = {
    '🇦🇷 Argentina (ADRs & Unicornios)': [
        'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 
        'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX'
    ],
    '🇺🇸 Mag 7 & Big Tech': [
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NFLX', 
        'CRM', 'ORCL', 'ADBE', 'IBM', 'CSCO', 'PLTR', 'SNOW', 'SHOP', 'SPOT'
    ],
    '🤖 Semiconductores & AI': [
        'AMD', 'INTC', 'QCOM', 'AVGO', 'TXN', 'MU', 'ADI', 'AMAT', 'LRCX', 
        'ARM', 'SMCI', 'TSM', 'ASML'
    ],
    '🏦 Financiero (USA)': [
        'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B', 
        'BLK', 'PYPL', 'SQ', 'COIN', 'HOOD'
    ],
    '💊 Salud & Pharma': [
        'LLY', 'NVO', 'JNJ', 'PFE', 'MRK', 'ABBV', 'UNH', 'BMY', 'AMGN', 
        'GILD', 'AZN', 'NVS', 'SNY'
    ],
    '🛒 Consumo & Retail': [
        'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'TGT', 'HD', 
        'LOW', 'PG', 'CL', 'MO', 'PM'
    ],
    '🏭 Industria & Energía': [
        'XOM', 'CVX', 'SLB', 'HAL', 'OXY', 'SHEL', 'BP', 'TTE',
        'BA', 'CAT', 'DE', 'GE', 'MMM', 'HON', 'LMT', 'RTX',
        'F', 'GM', 'TM', 'HMC', 'STLA'
    ],
    '🇧🇷 Brasil': [
        'PBR', 'VALE', 'ITUB', 'BBD', 'ERJ', 'ABEV', 'GGB', 'SID'
    ],
    '🇨🇳 China': [
        'BABA', 'JD', 'BIDU', 'PDD', 'NIO', 'TCOM', 'BEKE'
    ],
    '⛏️ Minería': [
        'GOLD', 'NEM', 'PAAS', 'FCX', 'SCCO', 'RIO', 'BHP'
    ],
    '🪙 Crypto': [
        'MSTR', 'MARA', 'RIOT', 'HUT', 'BITF', 'CLSK'
    ],
    '📈 ETFs': [
        'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EWZ', 'FXI',
        'XLE', 'XLF', 'XLK', 'XLV', 'ARKK', 'SMH',
        'GLD', 'SLV', 'GDX'
    ]
}

CEDEAR_DATABASE = sorted(list(set([item for sublist in DB_CATEGORIES.values() for item in sublist])))

# --- INICIALIZAR ESTADO (NOMBRE CAMBIADO PARA EVITAR CONFLICTO) ---
if 'st360_db_v2' not in st.session_state:
    st.session_state['st360_db_v2'] = []

# --- MOTOR DE CÁLCULO ---

def get_technical_score(df):
    try:
        ha_close = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
        ha_open = (df['Open'].shift(1) + df['Close'].shift(1)) / 2
        
        last = df.index[-1]
        is_green = ha_close[last] > ha_open[last]
        
        price = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        ma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        score = 0
        details = []
        
        if is_green: score += 3; details.append("Vela HA Alcista (+3)")
        else: details.append("Vela HA Bajista")
            
        if price > ma20: score += 2; details.append("> MA20 (+2)")
        if ma20 > ma50: score += 3; details.append("Tendencia Sana (+3)")
        if price > ma200: score += 2; details.append("> MA200 (+2)")
        
        return min(score, 10), ", ".join(details)
    except: return 0, "Datos insuficientes"

def get_options_score(ticker, price):
    try:
        tk = yf.Ticker(ticker)
        exps = tk.options
        if not exps: return 5, "Sin Opciones (Neutral)", 0, 0
        
        opt = tk.option_chain(exps[0])
        calls = opt.calls
        puts = opt.puts
        
        if calls.empty or puts.empty: return 5, "Data Vacía", 0, 0
        
        cw = calls.loc[calls['openInterest'].idxmax()]['strike']
        pw = puts.loc[puts['openInterest'].idxmax()]['strike']
        
        score = 5
        detail = "Rango Medio"
        
        if price > cw: score=10; detail="🚀 Breakout (+10)"
        elif price < pw: score=1; detail="💀 Breakdown (+1)"
        else:
            rng = cw - pw
            if rng > 0:
                pos = (price - pw) / rng
                # Más cerca del piso (pos 0) = Mejor Score (10)
                score = 10 - (pos * 10) 
                
                # Ajustes finos
                if score > 8: detail = "🟢 Soporte (+9)"
                elif score < 2: detail = "🧱 Resistencia (+2)"
                else: detail = f"Rango ${pw}-${cw}"
                
        return score, detail, cw, pw
    except: return 5, "Error API", 0, 0

def get_seasonality_score(df):
    try:
        curr_month = datetime.now().month
        m_ret = df['Close'].resample('ME').last().pct_change()
        hist = m_ret[m_ret.index.month == curr_month]
        
        if len(hist) < 2: return 5, "Sin Historia"
        
        win = (hist > 0).mean()
        score = win * 10
        return score, f"WinRate: {win:.0%}"
    except: return 5, "Error Estacional"

def analyze_complete(ticker):
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="2y")
        if df.empty: return None
        
        price = df['Close'].iloc[-1]
        
        s_tec, d_tec = get_technical_score(df)
        s_opt, d_opt, cw, pw = get_options_score(ticker, price)
        s_sea, d_sea = get_seasonality_score(df)
        
        final = (s_tec * 4) + (s_opt * 3) + (s_sea * 3)
        
        verdict = "NEUTRAL"
        if final >= 75: verdict = "🔥 COMPRA FUERTE"
        elif final >= 60: verdict = "✅ COMPRA"
        elif final <= 25: verdict = "💀 VENTA FUERTE"
        elif final <= 40: verdict = "🔻 VENTA"
        
        return {
            "Ticker": ticker, "Price": price, "Score": final, "Verdict": verdict,
            "S_Tec": s_tec, "D_Tec": d_tec,
            "S_Opt": s_opt, "D_Opt": d_opt,
            "S_Sea": s_sea, "D_Sea": d_sea,
            "CW": cw, "PW": pw, "History": df
        }
    except: return None

# --- UI: BARRA LATERAL ---
with st.sidebar:
    st.header("⚙️ Panel de Control")
    st.info(f"Base de Datos: {len(CEDEAR_DATABASE)} Activos")
    
    batch_size = st.slider("Tamaño del Lote", 1, 15, 5)
    batches = [CEDEAR_DATABASE[i:i + batch_size] for i in range(0, len(CEDEAR_DATABASE), batch_size)]
    batch_labels = [f"Lote {i+1}: {b[0]} ... {b[-1]}" for i, b in enumerate(batches)]
    
    sel_batch = st.selectbox("Seleccionar Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    col_b1, col_b2 = st.columns(2)
    if col_b1.button("▶️ ESCANEAR", type="primary"):
        targets = batches[sel_batch]
        prog = st.progress(0)
        status = st.empty()
        
        # Filtrar duplicados
        mem_tickers = [x['Ticker'] for x in st.session_state['st360_db_v2']]
        to_run = [t for t in targets if t not in mem_tickers]
        
        for i, t in enumerate(to_run):
            status.markdown(f"🔍 Analizando **{t}**...")
            res = analyze_complete(t)
            if res: st.session_state['st360_db_v2'].append(res)
            prog.progress((i+1)/len(to_run))
            time.sleep(0.5)
            
        status.success("✅ Listo")
        time.sleep(1)
        status.empty()
        prog.empty()
        st.rerun()
        
    if col_b2.button("🗑️ Limpiar"):
        st.session_state['st360_db_v2'] = []
        st.rerun()

    st.divider()
    
    st.markdown("### 🎯 Búsqueda Rápida")
    manual_t = st.text_input("Ticker (Ej: NVO, ASML):").upper().strip()
    if st.button("Analizar Individual"):
        if manual_t:
            with st.spinner("Procesando..."):
                res = analyze_complete(manual_t)
                if res:
                    st.session_state['st360_db_v2'] = [x for x in st.session_state['st360_db_v2'] if x['Ticker'] != manual_t]
                    st.session_state['st360_db_v2'].append(res)
                    st.rerun()
                else:
                    st.error("No se encontraron datos.")

# --- VISTA PRINCIPAL ---
st.title("🧠 SystemaTrader 360: Master Database")
st.caption("Algoritmo de Fusión: Técnico (40%) + Estructura Gamma (30%) + Estacionalidad (30%)")

if st.session_state['st360_db_v2']:
    # Dataframe conversion
    df_view = pd.DataFrame(st.session_state['st360_db_v2'])
    
    # Manejo de errores si la columna Score no existe por alguna razón rara
    if 'Score' in df_view.columns:
        df_view = df_view.sort_values("Score", ascending=False)
    
    # --- TABLA ---
    st.subheader("1. Tablero de Comando (Acumulado)")
    st.dataframe(
        df_view[['Ticker', 'Price', 'Score', 'Verdict', 'S_Tec', 'S_Opt', 'S_Sea']],
        column_config={
            "Ticker": "Activo",
            "Price": st.column_config.NumberColumn(format="$%.2f"),
            "Score": st.column_config.ProgressColumn("Puntaje Crítico", min_value=0, max_value=100, format="%.0f"),
            "S_Tec": st.column_config.NumberColumn("Técnico (0-10)", format="%.1f"),
            "S_Opt": st.column_config.NumberColumn("Opciones (0-10)", format="%.1f"),
            "S_Sea": st.column_config.NumberColumn("Estacional (0-10)", format="%.1f"),
        },
        use_container_width=True, hide_index=True, height=350
    )
    
    # --- DETALLE ---
    st.divider()
    st.subheader("2. Inspección de Activo")
    
    options = df_view['Ticker'].tolist()
    selection = st.selectbox("Selecciona para ver detalle:", options)
    
    item = next((x for x in st.session_state['st360_db_v2'] if x['Ticker'] == selection), None)
    
    if item:
        c1, c2, c3 = st.columns(3)
        sc = item['Score']
        clr = "#00C853" if sc >= 70 else "#D32F2F" if sc <= 40 else "#FBC02D"
        
        with c1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="score-label">TÉCNICO (40%)</div>
                <div class="big-score" style="color: #555;">{item['S_Tec']:.1f}<span style="font-size:1rem">/10</span></div>
                <div style="font-size: 0.8rem; color: #888;">{item['D_Tec']}</div>
            </div>""", unsafe_allow_html=True)
            
        with c2:
            st.markdown(f"""
            <div class="metric-card" style="border: 2px solid {clr};">
                <div class="score-label" style="color:{clr};">PUNTAJE CRÍTICO</div>
                <div class="big-score" style="color: {clr};">{sc:.0f}<span style="font-size:1rem">/100</span></div>
                <div style="font-weight:bold; color:{clr};">{item['Verdict']}</div>
            </div>""", unsafe_allow_html=True)
            
        with c3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="score-label">ESTRUCTURA (30%)</div>
                <div class="big-score" style="color: #555;">{item['S_Opt']:.1f}<span style="font-size:1rem">/10</span></div>
                <div style="font-size: 0.8rem; color: #888;">{item['D_Opt']}</div>
            </div>""", unsafe_allow_html=True)
            
        st.caption(f"📅 Estacionalidad: **{item['S_Sea']:.1f}/10** - {item['D_Sea']}")
        
        st.markdown(f"#### 📉 Gráfico: {selection}")
        hist = item['History']
        cw, pw = item['CW'], item['PW']
        
        fig = go.Figure(data=[go.Candlestick(
            x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='Precio'
        )])
        
        if cw > 0:
            fig.add_hline(y=cw, line_dash="dash", line_color="red", annotation_text=f"Call Wall ${cw}")
            fig.add_hline(y=pw, line_dash="dash", line_color="green", annotation_text=f"Put Wall ${pw}")
            
        fig.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_white", margin=dict(t=30, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👈 Selecciona un lote o busca un ticker individual para comenzar.")
