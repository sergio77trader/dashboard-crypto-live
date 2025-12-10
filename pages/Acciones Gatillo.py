import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import time
from datetime import datetime
import re

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader 360: Decision Engine")

# --- ESTILOS CSS (CORREGIDO: FONDO TRANSPARENTE) ---
st.markdown("""
<style>
    /* Tarjetas de Métricas Transparentes */
    div[data-testid="stMetric"], .metric-card {
        background-color: transparent !important;
        border: 1px solid #e0e0e0; /* Borde gris suave */
        padding: 15px;
        border-radius: 8px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Ajuste para modo oscuro automático */
    @media (prefers-color-scheme: dark) {
        div[data-testid="stMetric"], .metric-card {
            border: 1px solid #404040;
        }
    }

    .big-score { 
        font-size: 2.5rem; 
        font-weight: 800; 
        margin: 0;
    }
    .score-label {
        font-size: 0.9rem;
        font-weight: 500;
        opacity: 0.8;
    }
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS MAESTRA ---
DB_CATEGORIES = {
    '🇦🇷 Argentina (ADRs)': ['GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI'],
    '🇺🇸 Mag 7 & Tech': ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'AMD', 'NFLX', 'INTC', 'QCOM', 'CRM', 'PLTR'],
    '🇺🇸 ETFs & Índices': ['SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'XLE', 'XLF', 'ARKK', 'GLD', 'SLV'],
    '🇺🇸 Financiero': ['JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'BRK-B'],
    '🇺🇸 Consumo': ['KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'PG', 'XOM', 'CVX'],
    '🌎 China & Brasil': ['BABA', 'JD', 'BIDU', 'PBR', 'VALE', 'ITUB'],
    '🪙 Crypto': ['COIN', 'MSTR', 'MARA', 'RIOT']
}
CEDEAR_DATABASE = sorted(list(set([item for sublist in DB_CATEGORIES.values() for item in sublist])))

# --- INICIALIZAR ESTADO ---
if 'st360_results' not in st.session_state:
    st.session_state['st360_results'] = []

# --- MOTOR DE ANÁLISIS (LOGICA DE PUNTAJE) ---

def get_technical_score(df):
    """Calcula Score Técnico (0-10)"""
    score = 0
    details = []
    try:
        # Heikin Ashi Calc
        ha_close = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
        ha_open = (df['Open'].shift(1) + df['Close'].shift(1)) / 2
        
        last_idx = df.index[-1]
        is_green = ha_close[last_idx] > ha_open[last_idx]
        
        # Medias Móviles
        price = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        ma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        # Puntos
        if is_green: score += 2; details.append("Vela HA Alcista")
        else: details.append("Vela HA Bajista")
            
        if price > ma20: score += 2; details.append("> MA20 (Corto Plazo)")
        if ma20 > ma50: score += 3; details.append("Cruce MA20/50 (Tendencia)")
        if price > ma200: score += 3; details.append("> MA200 (Largo Plazo)")
        
        return score, ", ".join(details)
    except: return 0, "Error Técnico"

def get_seasonality_score(df):
    """Calcula Score Estacional (0-10)"""
    try:
        current_month = datetime.now().month
        monthly_ret = df['Close'].resample('ME').last().pct_change()
        # Filtrar solo el mes actual de años anteriores
        history = monthly_ret[monthly_ret.index.month == current_month]
        
        if len(history) < 2: return 5, "Datos Insuficientes" # Neutral
        
        win_rate = (history > 0).mean()
        avg_ret = history.mean()
        
        score = win_rate * 10
        detail = f"WinRate Histórico {win_rate:.0%} (Avg: {avg_ret:.1%})"
        return score, detail
    except: return 5, "Error Estacional"

def get_options_score(ticker, current_price):
    """Calcula Score Estructural (0-10) y Muros"""
    try:
        tk = yf.Ticker(ticker)
        exps = tk.options
        if not exps: return 5, "Sin Opciones", 0, 0
        
        # Analizar primer vencimiento
        opt = tk.option_chain(exps[0])
        calls = opt.calls
        puts = opt.puts
        
        if calls.empty or puts.empty: return 5, "Data Vacía", 0, 0
        
        call_wall = calls.loc[calls['openInterest'].idxmax()]['strike']
        put_wall = puts.loc[puts['openInterest'].idxmax()]['strike']
        
        # Lógica de Proximidad
        dist_call_pct = (call_wall - current_price) / current_price
        dist_put_pct = (current_price - put_wall) / current_price
        
        score = 5
        detail = "Rango Medio"
        
        if current_price > call_wall:
            score = 10; detail = "🚀 Breakout Gamma (Rompió Techo)"
        elif current_price < put_wall:
            score = 1; detail = "💀 Breakdown (Perdió Piso)"
        elif dist_call_pct < 0.02: # Muy cerca del techo
            score = 2; detail = "🧱 Resistencia Inminente"
        elif dist_put_pct < 0.02: # Muy cerca del piso
            score = 9; detail = "🟢 Soporte Fuerte"
        else:
            # Score proporcional a la posición en el rango
            range_width = call_wall - put_wall
            if range_width > 0:
                pos_in_range = (current_price - put_wall) / range_width
                # Si está abajo (cerca del piso) es mejor compra (score alto)
                score = 10 - (pos_in_range * 10)
                detail = f"Rango: {put_wall} - {call_wall}"
            
        return score, detail, call_wall, put_wall
    except: return 5, "Error API", 0, 0

def analyze_ticker_complete(ticker):
    """Función Maestra que une todo"""
    ticker = ticker.upper().strip()
    try:
        # 1. Bajamos historial (sirve para Técnico y Estacional)
        tk = yf.Ticker(ticker)
        df = tk.history(period="2y") # 2 años para buena estacionalidad
        
        if df.empty: return None
        
        curr_price = df['Close'].iloc[-1]
        
        # 2. Calcular Sub-Scores
        s_tech, d_tech = get_technical_score(df)
        s_season, d_season = get_seasonality_score(df)
        s_opt, d_opt, cw, pw = get_options_score(ticker, curr_price)
        
        # 3. PONDERACIÓN (El secreto de la salsa)
        # Técnico 40% | Estructura 30% | Estacional 30%
        final_score = (s_tech * 4) + (s_opt * 3) + (s_season * 3)
        
        # Diagnóstico de Texto
        verdict = "NEUTRAL"
        if final_score >= 75: verdict = "🔥 COMPRA FUERTE"
        elif final_score >= 60: verdict = "✅ COMPRA"
        elif final_score <= 25: verdict = "💀 VENTA FUERTE"
        elif final_score <= 40: verdict = "🔻 VENTA"
        
        return {
            "Ticker": ticker,
            "Precio": curr_price,
            "Score_Total": final_score,
            "Veredicto": verdict,
            "S_Tecnico": s_tech, "D_Tecnico": d_tech,
            "S_Estructura": s_opt, "D_Estructura": d_opt,
            "S_Estacional": s_season, "D_Estacional": d_season,
            "Call_Wall": cw, "Put_Wall": pw,
            "History": df # Guardamos DF para graficar rápido sin volver a bajar
        }
    except Exception as e:
        return None

# --- UI: BARRA LATERAL ---
with st.sidebar:
    st.header("🎮 Centro de Control")
    st.info("Algoritmo: Técnico (40%) + Estructura (30%) + Estacional (30%)")
    
    # Selección de Lotes
    batch_size = st.slider("Tamaño del Lote", 1, 10, 5)
    batches = [CEDEAR_DATABASE[i:i + batch_size] for i in range(0, len(CEDEAR_DATABASE), batch_size)]
    batch_labels = [f"Lote {i+1}: {b[0]} ... {b[-1]}" for i, b in enumerate(batches)]
    
    idx = st.selectbox("Seleccionar Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    col1, col2 = st.columns(2)
    scan_btn = col1.button("▶️ Escanear Lote", type="primary")
    clear_btn = col2.button("🗑️ Limpiar")
    
    st.divider()
    st.markdown("### 🎯 Análisis Individual")
    custom_t = st.text_input("Ticker Manual (Ej: KO):")
    if st.button("Analizar Ticker"):
        if custom_t:
            with st.spinner(f"Analizando {custom_t}..."):
                res = analyze_ticker_complete(custom_t)
                if res: 
                    # Eliminar si ya existe para actualizar
                    st.session_state['st360_results'] = [x for x in st.session_state['st360_results'] if x['Ticker'] != res['Ticker']]
                    st.session_state['st360_results'].append(res)
                    st.rerun()

    if clear_btn:
        st.session_state['st360_results'] = []
        st.rerun()

# --- LÓGICA DE ESCANEO ---
if scan_btn:
    targets = batches[idx]
    prog = st.progress(0)
    status = st.empty()
    
    # Filtramos ya existentes
    existing = [x['Ticker'] for x in st.session_state['st360_results']]
    to_scan = [t for t in targets if t not in existing]
    
    for i, t in enumerate(to_scan):
        status.markdown(f"🧠 Procesando inteligencia para **{t}**...")
        res = analyze_ticker_complete(t)
        if res:
            st.session_state['st360_results'].append(res)
        prog.progress((i+1)/len(to_scan))
        time.sleep(1) # Pausa anti-bloqueo
        
    status.success("Lote completado.")
    time.sleep(1)
    status.empty()
    prog.empty()
    st.rerun()

# --- VISTA PRINCIPAL ---
st.title("🧠 SystemaTrader 360: Decision Engine")

if st.session_state['st360_results']:
    # Convertir a DF para tabla
    data_list = st.session_state['st360_results']
    df_view = pd.DataFrame(data_list)
    
    # Ordenar por Puntaje Crítico descendente
    df_view = df_view.sort_values("Score_Total", ascending=False)
    
    # --- 1. TABLA ACUMULATIVA ---
    st.subheader("1. Tablero de Oportunidades (Acumulado)")
    
    st.dataframe(
        df_view[['Ticker', 'Precio', 'Score_Total', 'Veredicto', 'S_Tecnico', 'S_Estructura', 'S_Estacional']],
        column_config={
            "Ticker": "Activo",
            "Precio": st.column_config.NumberColumn(format="$%.2f"),
            "Score_Total": st.column_config.ProgressColumn(
                "Puntaje Crítico (0-100)", 
                format="%.0f", 
                min_value=0, max_value=100,
            ),
            "S_Tecnico": st.column_config.NumberColumn("Técnico (0-10)", format="%.1f"),
            "S_Estructura": st.column_config.NumberColumn("Opciones (0-10)", format="%.1f"),
            "S_Estacional": st.column_config.NumberColumn("Estacional (0-10)", format="%.1f"),
        },
        use_container_width=True, hide_index=True, height=350
    )
    
    # --- 2. SELECTOR DE DETALLE (LA "IMAGEN" QUE PEDISTE) ---
    st.divider()
    st.subheader("2. Inspección Profunda")
    
    # Dropdown con los activos cargados
    assets_avail = df_view['Ticker'].tolist()
    
    # Seleccionamos el primero de la lista (el de mejor puntaje) por defecto
    selected_asset = st.selectbox("Selecciona un activo de la lista para ver el detalle:", assets_avail)
    
    # Buscar datos del seleccionado
    item = next((x for x in data_list if x['Ticker'] == selected_asset), None)
    
    if item:
        # TARJETAS DE MÉTRICAS (SIN FONDO NEGRO)
        c1, c2, c3 = st.columns(3)
        
        # Colores dinámicos
        color_score = "#00C853" if item['Score_Total'] > 70 else "#FF3D00" if item['Score_Total'] < 40 else "#FFAB00"
        
        with c1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="score-label">🛠️ Análisis Técnico (40%)</div>
                <div class="big-score" style="color: #424242;">{item['S_Tecnico']:.1f}<span style="font-size:1rem">/10</span></div>
                <div style="font-size: 0.8rem; color: #666;">{item['D_Tecnico']}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with c2:
            st.markdown(f"""
            <div class="metric-card" style="border-color: {color_score}; border-width: 2px;">
                <div class="score-label">🌟 PUNTAJE CRÍTICO</div>
                <div class="big-score" style="color: {color_score};">{item['Score_Total']:.0f}<span style="font-size:1rem">/100</span></div>
                <div style="font-weight: bold; color: {color_score};">{item['Veredicto']}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with c3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="score-label">🧱 Estructura Opciones (30%)</div>
                <div class="big-score" style="color: #424242;">{item['S_Estructura']:.1f}<span style="font-size:1rem">/10</span></div>
                <div style="font-size: 0.8rem; color: #666;">{item['D_Estructura']}</div>
            </div>
            """, unsafe_allow_html=True)
            
        # ESTACIONALIDAD (EXTRA)
        st.caption(f"📅 Factor Estacional (Mes Actual): **{item['S_Estacional']:.1f}/10** - {item['D_Estacional']}")

        # GRÁFICO
        st.markdown(f"#### 📉 Gráfico de Referencia: {selected_asset}")
        
        hist_df = item['History']
        cw, pw = item['Call_Wall'], item['Put_Wall']
        
        fig = go.Figure(data=[go.Candlestick(
            x=hist_df.index,
            open=hist_df['Open'], high=hist_df['High'],
            low=hist_df['Low'], close=hist_df['Close'],
            name="Precio"
        )])
        
        # Muros
        if cw > 0:
            fig.add_hline(y=cw, line_dash="dash", line_color="#F44336", annotation_text=f"Call Wall (Techo) ${cw}")
            fig.add_hline(y=pw, line_dash="dash", line_color="#00C853", annotation_text=f"Put Wall (Piso) ${pw}")
            
        fig.update_layout(
            height=500, 
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis_rangeslider_visible=False,
            template="plotly_white", # Tema claro para coincidir con tu preferencia
            yaxis_title="Precio ($)"
        )
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👋 Selecciona un lote en la barra lateral y presiona 'Escanear' para comenzar a generar inteligencia.")
