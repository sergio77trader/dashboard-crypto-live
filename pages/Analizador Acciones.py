import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import numpy as np
import time

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Escáner Masivo: HA + ADX", layout="wide")

# --- ESTILOS VISUALES ---
st.markdown("""
<style>
    .stDataFrame { font-size: 0.9rem; }
    div[data-testid="stMetric"], .metric-card {
        background-color: #0e1117; border: 1px solid #303030;
        padding: 10px; border-radius: 8px; text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS DE ACTIVOS (CEDEARs / ADRs / USA) ---
TICKERS_DB = sorted([
    # ARGENTINA (ADRs)
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI',
    # USA (BIG TECH & BLUE CHIPS)
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NFLX', 'CRM', 'ORCL', 'ADBE', 'IBM', 'CSCO',
    'AMD', 'INTC', 'QCOM', 'AVGO', 'TXN', 'MU',
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA',
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT',
    'XOM', 'CVX', 'SLB', 'BA', 'CAT', 'GE',
    # CHINA
    'BABA', 'JD', 'BIDU', 'NIO', 'PDD',
    # BRASIL
    'PBR', 'VALE', 'ITUB', 'BBD', 'ERJ',
    # ETFS
    'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EWZ', 'XLE', 'XLF', 'ARKK', 'GLD', 'SLV'
])

# --- FUNCIONES DE CÁLCULO ---

def calculate_heikin_ashi(df):
    """Calcula Heikin Ashi iterativo (Precisión TradingView)"""
    df_ha = df.copy()
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    ha_open = [df['Open'].iloc[0]]
    for i in range(1, len(df)):
        prev_open = ha_open[-1]
        prev_close = df_ha['HA_Close'].iloc[i-1]
        ha_open.append((prev_open + prev_close) / 2)
        
    df_ha['HA_Open'] = ha_open
    df_ha['HA_High'] = df_ha[['High', 'HA_Open', 'HA_Close']].max(axis=1)
    df_ha['HA_Low'] = df_ha[['Low', 'HA_Open', 'HA_Close']].min(axis=1)
    
    # 1 Verde, -1 Rojo
    df_ha['Color'] = np.where(df_ha['HA_Close'] > df_ha['HA_Open'], 1, -1)
    return df_ha

@st.cache_data(ttl=3600)
def get_data(ticker, interval, period):
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False, auto_adjust=True)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except: return None

def analyze_ticker(ticker, interval, period, adx_len, adx_th):
    """
    Analiza un ticker y devuelve la ÚLTIMA señal y el DF completo para graficar.
    """
    df = get_data(ticker, interval, period)
    if df is None: return None, None

    # 1. Calcular ADX
    df.ta.adx(length=adx_len, append=True)
    adx_col = f"ADX_{adx_len}"
    
    # 2. Calcular HA
    df_ha = calculate_heikin_ashi(df)
    
    # 3. Lógica de Señal
    signals = []
    in_position = False
    
    # Iteramos para encontrar las señales
    for i in range(1, len(df_ha)):
        date = df_ha.index[i]
        ha_color = df_ha['Color'].iloc[i]
        adx_val = df_ha[adx_col].iloc[i]
        price = df_ha['Close'].iloc[i]
        
        if not in_position and ha_color == 1 and adx_val > adx_th:
            in_position = True
            signals.append({'Fecha': date, 'Tipo': '🟢 COMPRA', 'Precio': price, 'ADX': adx_val})
            
        elif in_position and ha_color == -1:
            in_position = False
            signals.append({'Fecha': date, 'Tipo': '🔴 VENTA', 'Precio': price, 'ADX': adx_val})
    
    # Si hay señales, devolvemos la última
    last_signal = signals[-1] if signals else None
    
    # Devolvemos la última señal encontrada y el DF con indicadores para el gráfico
    return last_signal, df_ha

# --- UI LATERAL ---
with st.sidebar:
    st.header("⚙️ Configuración del Escáner")
    
    st.info(f"Base de Datos: {len(TICKERS_DB)} Activos")
    
    # Parámetros Globales
    interval = st.selectbox("Temporalidad", ["1mo", "1wk", "1d", "1h"], index=0)
    period_map = {"1mo": "max", "1wk": "10y", "1d": "5y", "1h": "730d"}
    
    st.divider()
    st.subheader("Estrategia")
    adx_len = st.number_input("Longitud ADX", value=14)
    adx_th = st.number_input("Umbral ADX", value=20)
    
    st.divider()
    
    # Control de Lotes para no saturar
    batch_size = st.slider("Tamaño del Lote de Escaneo", 5, 50, 10)
    # Crear lotes
    batches = [TICKERS_DB[i:i + batch_size] for i in range(0, len(TICKERS_DB), batch_size)]
    batch_labels = [f"Lote {i+1}: {b[0]} ... {b[-1]}" for i, b in enumerate(batches)]
    sel_batch_idx = st.selectbox("Seleccionar Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    scan_btn = st.button("🚀 ESCANEAR LOTE SELECCIONADO", type="primary")

# --- APP PRINCIPAL ---
st.title("🛰️ Escáner de Señales: Heikin Ashi + ADX")

# Inicializar estado para guardar resultados
if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []

if scan_btn:
    targets = batches[sel_batch_idx]
    
    # Barra de progreso
    prog_bar = st.progress(0)
    status_text = st.empty()
    
    current_results = []
    
    for i, t in enumerate(targets):
        status_text.text(f"Analizando {t}...")
        
        last_sig, _ = analyze_ticker(t, interval, period_map[interval], adx_len, adx_th)
        
        if last_sig:
            # Agregamos el ticker al diccionario de señal
            last_sig['Ticker'] = t
            current_results.append(last_sig)
            
        prog_bar.progress((i + 1) / len(targets))
    
    # Guardamos en session state (acumulativo o reemplazo según prefieras, aquí reemplazo el lote)
    # Para hacerlo acumulativo cambiar '=' por extend, pero cuidado con duplicados.
    # Aquí usaremos una lista acumulativa limpiando duplicados
    
    # 1. Traer viejos
    old_data = st.session_state['scan_results']
    # 2. Eliminar si ya existen los que acabamos de escanear (para actualizar)
    old_data = [x for x in old_data if x['Ticker'] not in targets]
    # 3. Sumar nuevos
    st.session_state['scan_results'] = old_data + current_results
    
    status_text.empty()
    prog_bar.empty()
    st.success("Escaneo Finalizado")

# --- MOSTRAR RESULTADOS ---
if st.session_state['scan_results']:
    
    df_results = pd.DataFrame(st.session_state['scan_results'])
    
    # Ordenar por fecha (las señales más recientes primero)
    df_results = df_results.sort_values(by="Fecha", ascending=False)
    
    # Formatear Fecha
    df_results['Fecha_Str'] = df_results['Fecha'].dt.strftime('%d-%m-%Y')
    
    # --- TABLA RESUMEN ---
    st.subheader("📋 Bitácora de Últimas Alertas")
    
    # Filtros visuales
    c1, c2 = st.columns([1, 4])
    with c1:
        filter_type = st.multiselect("Filtrar por Tipo:", ["🟢 COMPRA", "🔴 VENTA"], default=["🟢 COMPRA", "🔴 VENTA"])
    
    if filter_type:
        df_show = df_results[df_results['Tipo'].isin(filter_type)]
    else:
        df_show = df_results

    # Estilos de tabla
    def color_signal(val):
        color = 'green' if 'COMPRA' in val else 'red'
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        df_show[['Ticker', 'Fecha_Str', 'Tipo', 'Precio', 'ADX']],
        column_config={
            "Precio": st.column_config.NumberColumn(format="$%.2f"),
            "ADX": st.column_config.NumberColumn(format="%.2f"),
            "Fecha_Str": "Fecha Alerta"
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.divider()
    
    # --- VISUALIZADOR DE GRÁFICO INDIVIDUAL ---
    st.subheader("📉 Visualizador de Gráfico")
    
    # Selector de activos (Solo los que están en la tabla)
    available_tickers = df_show['Ticker'].tolist()
    
    if available_tickers:
        selected_ticker = st.selectbox("Selecciona un activo para ver el gráfico:", available_tickers)
        
        if selected_ticker:
            # Buscar datos de la señal seleccionada
            signal_info = df_show[df_show['Ticker'] == selected_ticker].iloc[0]
            
            # Recalcular DF para graficar (usamos caché así que es rápido)
            with st.spinner("Generando gráfico..."):
                _, df_chart = analyze_ticker(selected_ticker, interval, period_map[interval], adx_len, adx_th)
            
            if df_chart is not None:
                # Filtrar data reciente para que el gráfico no sea eterno
                # Si es mensual mostramos todo, si es diario últimos 200
                chart_limit = 200 if interval != "1mo" else 500
                chart_data = df_chart.tail(chart_limit)
                
                # Crear Figura
                fig = go.Figure()

                # Velas HA
                fig.add_trace(go.Candlestick(
                    x=chart_data.index,
                    open=chart_data['HA_Open'], high=chart_data['HA_High'],
                    low=chart_data['HA_Low'], close=chart_data['HA_Close'],
                    name='Heikin Ashi'
                ))
                
                # Marcar la señal en el gráfico
                signal_date = signal_info['Fecha']
                
                # Solo graficar la señal si entra en el rango visible
                if signal_date >= chart_data.index[0]:
                    # Definir color y posición
                    is_buy = "COMPRA" in signal_info['Tipo']
                    marker_color = "blue" if is_buy else "orange"
                    marker_symbol = "triangle-up" if is_buy else "triangle-down"
                    y_pos = signal_info['Precio'] * (0.95 if is_buy else 1.05)
                    
                    fig.add_trace(go.Scatter(
                        x=[signal_date], y=[y_pos],
                        mode='markers+text',
                        marker=dict(symbol=marker_symbol, size=15, color=marker_color),
                        text=[signal_info['Tipo']],
                        textposition="bottom center" if is_buy else "top center",
                        name='Última Señal'
                    ))

                fig.update_layout(
                    title=f"Gráfico {selected_ticker} ({interval}) - Última Señal: {signal_info['Fecha_Str']}",
                    xaxis_rangeslider_visible=False,
                    height=600,
                    template="plotly_dark"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Mostrar métricas del momento de la señal
                k1, k2, k3 = st.columns(3)
                k1.metric("Fecha Señal", signal_info['Fecha_Str'])
                k2.metric("Precio Señal", f"${signal_info['Precio']:.2f}")
                k3.metric("Fuerza ADX", f"{signal_info['ADX']:.2f}")

    else:
        st.info("No hay activos para mostrar en el gráfico.")

else:
    st.info("👈 Selecciona un lote en el menú lateral y presiona 'ESCANEAR' para comenzar.")
