import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import time
import re

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Lotes & Acumulación")

# --- ESTILOS CSS (Fondo transparente para métricas) ---
st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: transparent !important;
        border: 1px solid #cccccc;
        padding: 10px;
        border-radius: 5px;
        color: inherit;
    }
    div[data-testid="stMarkdownContainer"] p {
        font-size: 1.05rem;
    }
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS MAESTRA (CEDEARS + ADRs + ETFs) ---
# Seleccionados por liquidez en mercado de opciones USA
DB_CATEGORIES = {
    '🇦🇷 Argentina (ADRs)': [
        'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 
        'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI'
    ],
    '🇺🇸 Mag 7 & Big Tech': [
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NFLX', 
        'AMD', 'INTC', 'QCOM', 'AVGO', 'CRM', 'ORCL', 'IBM', 'CSCO', 'UBER', 'ABNB', 'PLTR'
    ],
    '🇺🇸 ETFs & Índices': [
        'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'XLE', 'XLF', 'ARKK', 'EWZ', 'GLD', 'SLV'
    ],
    '🇺🇸 Financiero & Bancos': [
        'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B', 'PYPL', 'SQ'
    ],
    '🇺🇸 Consumo & Industrial': [
        'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'PG', 'JNJ', 
        'PFE', 'MRK', 'XOM', 'CVX', 'BA', 'CAT', 'GE', 'MMM', 'DE', 'F', 'GM'
    ],
    '🌎 Brasil, China & Emergentes': [
        'PBR', 'VALE', 'ITUB', 'BBD', 'BABA', 'JD', 'BIDU', 'NIO', 'TSM'
    ],
    '🪙 Crypto & Volatilidad': [
        'COIN', 'MSTR', 'MARA', 'RIOT', 'HUT', 'BITF', 'HOOD'
    ]
}

# Aplanamos la lista para los lotes y eliminamos duplicados
CEDEAR_DATABASE = sorted(list(set([item for sublist in DB_CATEGORIES.values() for item in sublist])))

# --- INICIALIZAR ESTADO (ACUMULADOR) ---
if 'accumulated_data' not in st.session_state:
    st.session_state['accumulated_data'] = []

# --- FUNCIONES LÓGICAS ---
def get_sentiment_label(ratio):
    if ratio < 0.7: return "🚀 ALCISTA"
    elif ratio > 1.3: return "🐻 BAJISTA"
    else: return "⚖️ NEUTRAL"

def check_proximity(price, wall_price, threshold_pct):
    if wall_price == 0 or price == 0: return False
    distance = abs(price - wall_price) / price * 100
    return distance <= threshold_pct

def analyze_ticker_safe(ticker):
    """Analiza un solo ticker de forma segura y devuelve un dict completo"""
    ticker = ticker.upper().strip()
    try:
        tk = yf.Ticker(ticker)
        
        # 1. Obtener Precio
        hist = tk.history(period="1d")
        if hist.empty: return None
        current_price = hist['Close'].iloc[-1]
        
        # 2. Obtener Opciones
        exps = tk.options
        if not exps: return None
        
        target_date = exps[0]
        opt = tk.option_chain(target_date)
        calls, puts = opt.calls, opt.puts
        
        if calls.empty or puts.empty: return None
        
        # 3. Cálculos
        total_call_oi = calls['openInterest'].sum()
        total_put_oi = puts['openInterest'].sum()
        
        if total_call_oi == 0: total_call_oi = 1
        pc_ratio = total_put_oi / total_call_oi
        
        # Muros
        call_wall = calls.loc[calls['openInterest'].idxmax()]['strike']
        put_wall = puts.loc[puts['openInterest'].idxmax()]['strike']
        
        # Max Pain Simplificado
        strikes = sorted(list(set(calls['strike'].tolist() + puts['strike'].tolist())))
        relevant_strikes = [s for s in strikes if current_price * 0.7 < s < current_price * 1.3]
        
        cash_values = []
        for strike in relevant_strikes:
            call_loss = calls.apply(lambda r: max(0, strike - r['strike']) * r['openInterest'], axis=1).sum()
            put_loss = puts.apply(lambda r: max(0, r['strike'] - strike) * r['openInterest'], axis=1).sum()
            cash_values.append(call_loss + put_loss)
            
        max_pain = relevant_strikes[np.argmin(cash_values)] if cash_values else current_price
        
        # 4. Calcular Sentimiento
        sentiment_calc = get_sentiment_label(pc_ratio)

        return {
            'Ticker': ticker,
            'Price': current_price,
            'Max_Pain': max_pain,
            'Call_Wall': call_wall,
            'Put_Wall': put_wall,
            'PC_Ratio': pc_ratio,
            'Call_OI': total_call_oi,
            'Put_OI': total_put_oi,
            'Expiration': target_date,
            'Sentimiento': sentiment_calc,
            'Calls_DF': calls, 
            'Puts_DF': puts
        }

    except Exception as e:
        return {'Ticker': ticker, 'Status': 'Error', 'Price': 0}

# --- FUNCIÓN DE ESCANEO REUTILIZABLE ---
def run_scan_process(ticker_list):
    progress_bar = st.progress(0)
    status_text = st.empty()
    existing_tickers = [d.get('Ticker') for d in st.session_state['accumulated_data']]
    
    # Filtramos los que ya existen para no perder tiempo, a menos que sea una lista muy corta
    target_tickers = [t for t in ticker_list if t not in existing_tickers]
    skipped = len(ticker_list) - len(target_tickers)
    
    if skipped > 0:
        st.toast(f"Saltando {skipped} activos ya analizados...", icon="⏭️")

    for i, ticker in enumerate(target_tickers):
        status_text.markdown(f"🔎 Analizando **{ticker}**...")
        
        data = analyze_ticker_safe(ticker)
        
        if data and 'Price' in data and data['Price'] > 0:
            st.session_state['accumulated_data'].append(data)
        
        progress_bar.progress((i + 1) / len(target_tickers))
        time.sleep(1.2) # Pausa de seguridad
        
    status_text.success("✅ Análisis finalizado.")
    time.sleep(1)
    status_text.empty()
    progress_bar.empty()
    st.rerun()

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("⚙️ Configuración")
    proximity_threshold = st.slider("Alerta Proximidad (%)", 1, 10, 3)
    
    st.divider()
    
    # --- SECCIÓN 1: LOTES AUTOMÁTICOS ---
    st.header("📦 Escaneo por Lotes")
    st.caption(f"Base de Datos: {len(CEDEAR_DATABASE)} Activos")
    
    batch_size = st.slider("Tamaño del Lote", 1, 10, 5) 
    batches = [CEDEAR_DATABASE[i:i + batch_size] for i in range(0, len(CEDEAR_DATABASE), batch_size)]
    batch_labels = [f"Lote {i+1}: {b[0]} ... {b[-1]}" for i, b in enumerate(batches)]
    
    sel_batch_idx = st.selectbox("Seleccionar Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    if st.button("▶️ ESCANEAR LOTE SELECCIONADO", type="primary"):
        run_scan_process(batches[sel_batch_idx])

    st.divider()
    
    # --- SECCIÓN 2: PERSONALIZADO ---
    st.header("🎯 Lista Personalizada")
    custom_input = st.text_area("Ingresa tickers (sep. por coma):", placeholder="Ej: KO, MCD, NKE, GGAL")
    
    if st.button("▶️ ANALIZAR MI LISTA"):
        if custom_input:
            # Limpiar input (quitar espacios, comas, saltos de linea)
            custom_list = [t.strip().upper() for t in re.split(r'[,\s\n]+', custom_input) if t.strip()]
            if custom_list:
                run_scan_process(custom_list)
            else:
                st.error("Lista vacía.")
        else:
            st.warning("Escribe al menos un ticker.")

    st.divider()
    
    # --- LIMPIEZA ---
    if st.button("🗑️ Borrar Resultados"):
        st.session_state['accumulated_data'] = []
        st.rerun()
        
    st.metric("Activos en Memoria", len(st.session_state['accumulated_data']))

# --- VISTA PRINCIPAL ---
st.title("SystemaTrader: Scanner de Oportunidades")

if st.session_state['accumulated_data']:
    df = pd.DataFrame(st.session_state['accumulated_data'])
    
    if not df.empty and 'Ticker' in df.columns:
        
        # Procesamiento Tabla
        def get_status(row):
            status = []
            if check_proximity(row['Price'], row['Call_Wall'], proximity_threshold): status.append("🧱 TECHO")
            if check_proximity(row['Price'], row['Put_Wall'], proximity_threshold): status.append("🟢 PISO")
            return " + ".join(status) if status else "OK"

        df['Estado'] = df.apply(get_status, axis=1)
        df['Dist. Techo %'] = ((df['Call_Wall'] - df['Price']) / df['Price'])
        df['Dist. Piso %'] = ((df['Put_Wall'] - df['Price']) / df['Price'])
        
        # Filtros Visuales
        col_filtro1, col_filtro2 = st.columns([1, 4])
        with col_filtro1:
            ver_alertas = st.checkbox("🔥 Solo Alertas")
        
        df_display = df[df['Estado'] != "OK"] if ver_alertas else df

        # --- TABLA ---
        st.subheader("1. Resultados Acumulados")
        st.dataframe(
            df_display[['Ticker', 'Price', 'Max_Pain', 'Estado', 'Call_Wall', 'Dist. Techo %', 'Put_Wall', 'Dist. Piso %', 'Sentimiento']],
            column_config={
                "Ticker": "Activo",
                "Price": st.column_config.NumberColumn("Precio", format="$%.2f"),
                "Max_Pain": st.column_config.NumberColumn("Max Pain", format="$%.2f"),
                "Call_Wall": st.column_config.NumberColumn("Techo", format="$%.2f"),
                "Put_Wall": st.column_config.NumberColumn("Piso", format="$%.2f"),
                "Dist. Techo %": st.column_config.NumberColumn("Dist. Techo", format="%.2f %%"),
                "Dist. Piso %": st.column_config.NumberColumn("Dist. Piso", format="%.2f %%"),
            },
            use_container_width=True, hide_index=True, height=450
        )

        # --- ANÁLISIS PROFUNDO ---
        st.divider()
        st.subheader("2. Análisis Profundo")
        
        tickers_avail = sorted(df['Ticker'].tolist())
        sel_ticker = st.selectbox("Selecciona Activo para Detalle:", tickers_avail)
        
        asset = next((item for item in st.session_state['accumulated_data'] if item["Ticker"] == sel_ticker), None)
        
        if asset:
            # MÉTRICAS
            c1, c2, c3, c4, c5 = st.columns(5)
            dist_pain = ((asset['Max_Pain'] - asset['Price']) / asset['Price']) * 100
            
            c1.metric("Precio", f"${asset['Price']:.2f}")
            c2.metric("Max Pain (Imán)", f"${asset['Max_Pain']:.2f}", f"{dist_pain:.2f}%", delta_color="off")
            c3.metric("Sentimiento", asset['Sentimiento'], f"Ratio: {asset['PC_Ratio']:.2f}")
            c4.metric("Techo (Resistencia)", f"${asset['Call_Wall']:.2f}")
            c5.metric("Piso (Soporte)", f"${asset['Put_Wall']:.2f}")
            
            # GRÁFICOS
            col_graph1, col_graph2 = st.columns([1, 2])
            
            with col_graph1:
                st.markdown("##### Sentimiento")
                fig_pie = go.Figure(data=[go.Pie(
                    labels=['Calls', 'Puts'], 
                    values=[asset['Call_OI'], asset['Put_OI']], 
                    hole=.4,
                    marker=dict(colors=['#00C853', '#FF5252'])
                )])
                fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, showlegend=False)
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with col_graph2:
                st.markdown("##### Muro de Liquidez")
                calls_df = asset['Calls_DF']
                puts_df = asset['Puts_DF']
                
                center = asset['Price']
                # Rango dinámico del gráfico (+- 20% del precio)
                mask_c = (calls_df['strike'] > center * 0.8) & (calls_df['strike'] < center * 1.2)
                mask_p = (puts_df['strike'] > center * 0.8) & (puts_df['strike'] < center * 1.2)
                
                fig_wall = go.Figure()
                fig_wall.add_trace(go.Bar(x=calls_df[mask_c]['strike'], y=calls_df[mask_c]['openInterest'], name='Calls (Techo)', marker_color='#00C853'))
                fig_wall.add_trace(go.Bar(x=puts_df[mask_p]['strike'], y=puts_df[mask_p]['openInterest'], name='Puts (Piso)', marker_color='#FF5252'))
                
                fig_wall.add_vline(x=asset['Price'], line_dash="dash", line_color="gray", annotation_text="Precio")
                fig_wall.add_vline(x=asset['Call_Wall'], line_dash="dot", line_color="#00C853")
                fig_wall.add_vline(x=asset['Put_Wall'], line_dash="dot", line_color="#FF5252")
                fig_wall.add_vline(x=asset['Max_Pain'], line_dash="dash", line_color="orange", annotation_text="Max Pain")
                
                fig_wall.update_layout(barmode='overlay', height=350, margin=dict(t=20, b=0), xaxis_title="Strike", yaxis_title="Interés Abierto", legend=dict(orientation="h", y=1.1))
                st.plotly_chart(fig_wall, use_container_width=True)
                
            st.info(f"""
            🧠 **Interpretación Táctica:**
            1. **Imán (Max Pain ${asset['Max_Pain']:.2f}):** Precio teórico de vencimiento ({asset['Expiration']}).
            2. **Sentimiento:** {asset['Sentimiento']} (Ratio P/C: {asset['PC_Ratio']:.2f}).
            """)

else:
    st.info("👈 Selecciona un **Lote** o usa la **Lista Personalizada** en el menú para comenzar.")
