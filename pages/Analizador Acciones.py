import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import time

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="Scanner Masivo: HA + ADX")

# --- ESTILOS VISUALES ---
st.markdown("""
<style>
    div[data-testid="stMetric"], .metric-card {
        background-color: #0e1117; border: 1px solid #303030;
        padding: 10px; border-radius: 8px; text-align: center;
    }
    .buy-signal { color: #00FF00; font-weight: bold; }
    .sell-signal { color: #FF0000; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS MAESTRA (CEDEARS / USA / GLOBAL) ---
# Tickers en origen (USA/China/Brasil en USD)
TICKERS_DB = sorted([
    # ARGENTINA (ADRs)
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX',
    # BIG TECH
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NFLX', 'CRM', 'ORCL', 'ADBE', 'IBM', 'CSCO', 'PLTR',
    # SEMIS & AI
    'AMD', 'INTC', 'QCOM', 'AVGO', 'TXN', 'MU', 'ADI', 'AMAT', 'ARM', 'SMCI', 'TSM', 'ASML',
    # FINANCIERO
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B', 'PYPL', 'SQ', 'COIN',
    # CONSUMO
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'TGT', 'HD', 'PG',
    # INDUSTRIA & ENERGIA
    'XOM', 'CVX', 'SLB', 'BA', 'CAT', 'DE', 'GE', 'MMM', 'LMT', 'F', 'GM',
    # GLOBAL
    'PBR', 'VALE', 'ITUB', 'BBD', 'ERJ', 'BABA', 'JD', 'BIDU', 'NIO', 'GOLD', 'NEM', 'FCX',
    # ETFS
    'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EWZ', 'XLE', 'XLF', 'XLK', 'XLV', 'ARKK', 'GLD', 'SLV', 'GDX'
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
    # 1 Verde, -1 Rojo
    df_ha['Color'] = np.where(df_ha['HA_Close'] > df_ha['HA_Open'], 1, -1)
    return df_ha

def get_last_signal(ticker, interval_main, interval_filter, adx_len, th_micro, th_macro):
    """
    Analiza un ticker y devuelve la ÚLTIMA señal generada.
    """
    try:
        # Mapeo de periodos para descargar suficiente historia
        period_map = {"1mo": "max", "1wk": "10y", "1d": "5y", "1h": "730d"}
        
        # 1. Descargar Datos
        df_main = yf.download(ticker, interval=interval_main, period=period_map[interval_main], progress=False, auto_adjust=True)
        df_filter = yf.download(ticker, interval=interval_filter, period="max", progress=False, auto_adjust=True)
        
        if df_main.empty or df_filter.empty: return None
        
        # Limpieza MultiIndex
        if isinstance(df_main.columns, pd.MultiIndex): df_main.columns = df_main.columns.get_level_values(0)
        if isinstance(df_filter.columns, pd.MultiIndex): df_filter.columns = df_filter.columns.get_level_values(0)

        # 2. Calcular Indicadores
        # Main (Gatillo)
        df_main.ta.adx(length=adx_len, append=True)
        df_main = calculate_heikin_ashi(df_main)
        col_adx_main = f"ADX_{adx_len}"
        
        # Filtro (Macro)
        df_filter.ta.adx(length=adx_len, append=True)
        col_adx_filter = f"ADX_{adx_len}"
        
        # 3. Sincronizar (Reindex)
        # Traemos el ADX del filtro a la tabla principal
        adx_filter_aligned = df_filter[col_adx_filter].reindex(df_main.index, method='ffill')
        df_main['ADX_Filter_Val'] = adx_filter_aligned

        # 4. Encontrar la ÚLTIMA señal válida
        # Recorremos de atrás para adelante para ser más eficientes en la búsqueda del último estado
        # Pero para simular el estado de "entrada", necesitamos saber si estamos "dentro"
        # Así que simulamos rápido hacia adelante.
        
        last_signal = None
        in_position = False
        
        # Vectorizamos condiciones para velocidad (aproximación rápida)
        # Condición Compra
        buy_cond = (df_main['Color'] == 1) & (df_main[col_adx_main] > th_micro) & (df_main['ADX_Filter_Val'] > th_macro)
        # Condición Venta
        sell_cond = (df_main['Color'] == -1)
        
        # Iteración lineal necesaria para el estado de posición (stateful)
        for i in range(1, len(df_main)):
            date = df_main.index[i]
            price = df_main['Close'].iloc[i]
            
            # Si NO estamos en posición y hay compra
            if not in_position and buy_cond.iloc[i]:
                in_position = True
                last_signal = {
                    "Ticker": ticker,
                    "Fecha": date,
                    "Tipo": "🟢 COMPRA",
                    "Precio": price,
                    "ADX Gatillo": df_main[col_adx_main].iloc[i],
                    "ADX Filtro": df_main['ADX_Filter_Val'].iloc[i],
                    "Estado Actual": "ABIERTA"
                }
            
            # Si ESTAMOS en posición y hay venta
            elif in_position and sell_cond.iloc[i]:
                in_position = False
                last_signal = {
                    "Ticker": ticker,
                    "Fecha": date,
                    "Tipo": "🔴 VENTA",
                    "Precio": price,
                    "ADX Gatillo": df_main[col_adx_main].iloc[i],
                    "ADX Filtro": df_main['ADX_Filter_Val'].iloc[i],
                    "Estado Actual": "CERRADA"
                }
                
        return last_signal

    except Exception as e:
        return None

# --- UI LATERAL ---
with st.sidebar:
    st.header("⚙️ Configuración Estrategia")
    
    st.info(f"Base de Datos: {len(TICKERS_DB)} Activos (Acciones + CEDEARs)")
    
    st.subheader("Tiempo")
    # Configuración por defecto igual a tu captura (Mensual / Diario)
    int_main = st.selectbox("Temporalidad Gráfico", ["1mo", "1wk", "1d"], index=0)
    int_filter = st.selectbox("Temporalidad Filtro", ["1mo", "1wk", "1d"], index=2) 
    
    st.subheader("ADX Parametros")
    p_len = st.number_input("Longitud", value=14)
    p_micro = st.number_input("Umbral Gatillo (Gráfico)", value=25)
    p_macro = st.number_input("Umbral Filtro (Diario/Macro)", value=20)
    
    st.divider()
    
    # Batch Size
    batch_size = st.slider("Tamaño del Lote", 5, 50, 10)
    batches = [TICKERS_DB[i:i + batch_size] for i in range(0, len(TICKERS_DB), batch_size)]
    batch_labels = [f"Lote {i+1}: {b[0]} ... {b[-1]}" for i, b in enumerate(batches)]
    sel_batch = st.selectbox("Seleccionar Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    run_btn = st.button("🚀 ESCANEAR LOTE", type="primary")

# --- APP PRINCIPAL ---
st.title("🛰️ Escáner de Señales: HA + ADX Strategy")

if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []

if run_btn:
    targets = batches[sel_batch]
    
    # Barra de progreso
    prog_bar = st.progress(0)
    status = st.empty()
    
    new_data = []
    
    for i, t in enumerate(targets):
        status.text(f"Analizando {t}...")
        
        # Ejecutar análisis
        signal_data = get_last_signal(t, int_main, int_filter, p_len, p_micro, p_macro)
        
        if signal_data:
            new_data.append(signal_data)
            
        prog_bar.progress((i + 1) / len(targets))
    
    # Agregar a la lista acumulada (Evitar duplicados)
    current_tickers = [x['Ticker'] for x in st.session_state['scan_results']]
    for item in new_data:
        if item['Ticker'] not in current_tickers:
            st.session_state['scan_results'].append(item)
    
    status.success("Escaneo finalizado.")
    time.sleep(1)
    status.empty()
    prog_bar.empty()
    st.rerun()

# --- MOSTRAR RESULTADOS ---
if st.session_state['scan_results']:
    df = pd.DataFrame(st.session_state['scan_results'])
    
    # Filtros de visualización
    c1, c2, c3 = st.columns([1, 1, 3])
    with c1:
        f_type = st.multiselect("Filtrar por Tipo:", ["🟢 COMPRA", "🔴 VENTA"], default=["🟢 COMPRA", "🔴 VENTA"])
    with c2:
        if st.button("🗑️ Limpiar Resultados"):
            st.session_state['scan_results'] = []
            st.rerun()
            
    # Aplicar filtro
    if f_type:
        df_show = df[df['Tipo'].isin(f_type)]
    else:
        df_show = df
        
    # Ordenar por fecha (más reciente primero)
    df_show = df_show.sort_values("Fecha", ascending=False)
    
    # Formatear Fecha para mostrar solo día
    df_show['Fecha'] = df_show['Fecha'].dt.strftime('%Y-%m-%d')

    # Estilos de color para la tabla
    def highlight_signal(val):
        color = '#d4edda' if 'COMPRA' in val else '#f8d7da' if 'VENTA' in val else ''
        return f'background-color: {color}; color: black; font-weight: bold'

    st.subheader(f"Bitácora de Alertas ({len(df_show)})")
    
    st.dataframe(
        df_show.style.applymap(highlight_signal, subset=['Tipo']),
        column_config={
            "Ticker": st.column_config.TextColumn("Activo", width="small"),
            "Fecha": st.column_config.TextColumn("Fecha Señal", width="medium"),
            "Precio": st.column_config.NumberColumn("Precio Señal", format="$%.2f"),
            "ADX Gatillo": st.column_config.NumberColumn(format="%.2f"),
            "ADX Filtro": st.column_config.NumberColumn(format="%.2f"),
            "Estado Actual": st.column_config.TextColumn("Estado", help="ABIERTA: La señal sigue vigente. CERRADA: Ya cambió de color.")
        },
        use_container_width=True,
        hide_index=True,
        height=600
    )
    
else:
    st.info("👈 Selecciona un lote en el menú lateral y presiona 'ESCANEAR' para buscar la última señal.")
