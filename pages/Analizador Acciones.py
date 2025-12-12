import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Backtester Pro: HA + Doble ADX", layout="wide")

# --- ESTILOS VISUALES ---
st.markdown("""
<style>
    .metric-card {
        background-color: #0e1117;
        border: 1px solid #303030;
        padding: 15px; border-radius: 10px;
        text-align: center;
    }
    .success-text { color: #00FF00; font-weight: bold; }
    .error-text { color: #FF0000; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

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

def run_strategy_mtf(df_main, df_filter, adx_len, th_micro, th_macro):
    """
    Ejecuta la estrategia cruzando datos del Timeframe Principal y el de Filtro
    """
    # 1. Calcular Indicadores en DF Principal (Micro / Gatillo)
    df_main.ta.adx(length=adx_len, append=True)
    df_main = calculate_heikin_ashi(df_main)
    col_adx_main = f"ADX_{adx_len}"
    
    # 2. Calcular Indicadores en DF Filtro (Macro / Diario)
    # Solo necesitamos el ADX del filtro
    df_filter.ta.adx(length=adx_len, append=True)
    col_adx_filter = f"ADX_{adx_len}"
    
    # 3. Sincronizar Datos (Mapping)
    # Agregamos el valor del ADX del Filtro al DF Principal basándonos en la fecha
    # Usamos 'reindex' con 'ffill' (forward fill) para evitar mirar al futuro.
    # El ADX Diario de ayer es el que se usa para la apertura de hoy.
    adx_filter_aligned = df_filter[col_adx_filter].reindex(df_main.index, method='ffill')
    df_main['ADX_Filter_Val'] = adx_filter_aligned

    # 4. Simulación
    signals = []
    in_position = False
    entry_price = 0.0
    
    for i in range(1, len(df_main)):
        date = df_main.index[i]
        price = df_main['Close'].iloc[i]
        
        # Datos Técnicos
        ha_color = df_main['Color'].iloc[i]      # 1 = Verde
        adx_micro_val = df_main[col_adx_main].iloc[i]
        adx_macro_val = df_main['ADX_Filter_Val'].iloc[i]
        
        # --- LÓGICA DE ENTRADA (DOBLE FILTRO) ---
        # 1. Vela Verde
        # 2. ADX del Gráfico Actual > Umbral Micro
        # 3. ADX del Gráfico Diario (Filtro) > Umbral Macro
        # 4. No NaN (Datos válidos)
        condition_buy = (
            ha_color == 1 and 
            adx_micro_val > th_micro and 
            adx_macro_val > th_macro and
            not np.isnan(adx_macro_val)
        )
        
        if not in_position and condition_buy:
            in_position = True
            entry_price = price
            signals.append({
                'Fecha': date, 'Tipo': '🟢 COMPRA', 'Precio': price,
                'ADX Gatillo': adx_micro_val, 'ADX Filtro': adx_macro_val, 'Resultado': '-'
            })
            
        # --- LÓGICA DE SALIDA ---
        # Vela se pone Roja
        elif in_position and ha_color == -1:
            in_position = False
            pnl = ((price - entry_price) / entry_price) * 100
            signals.append({
                'Fecha': date, 'Tipo': '🔴 VENTA', 'Precio': price,
                'ADX Gatillo': adx_micro_val, 'ADX Filtro': adx_macro_val, 'Resultado': f"{pnl:.2f}%"
            })
            
    return pd.DataFrame(signals), df_main

# --- UI STREAMLIT ---
st.title("🔎 Backtester: HA Matrix + Filtro ADX")

with st.sidebar:
    st.header("Datos del Gráfico")
    ticker = st.text_input("Ticker", "AAPL").upper()
    
    # Timeframe Principal (Gatillo)
    interval_main = st.selectbox("Temporalidad Gráfico", ["1mo", "1wk", "1d", "1h"], index=0)
    period_map = {"1mo": "max", "1wk": "10y", "1d": "5y", "1h": "730d"}
    
    st.divider()
    
    # --- CONFIGURACIÓN IDÉNTICA A TU FOTO ---
    st.subheader("CONFIGURACIÓN ADX")
    adx_len = st.number_input("Longitud ADX", value=14)
    adx_th_micro = st.number_input("Umbral ADX Micro (Gatillo)", value=25)
    
    # Selección del Timeframe del Filtro (Por defecto Diario, como en tu foto)
    st.markdown("---")
    st.caption("Configuración del Filtro Macro")
    interval_filter = st.selectbox("Temporalidad Filtro", ["1d", "1wk", "1mo"], index=0, help="Debe ser igual o menor a la del gráfico, o usar Diario para consistencia.")
    adx_th_macro = st.number_input("Umbral ADX Diario/Filtro", value=20)

    btn = st.button("CALCULAR ESTRATEGIA", type="primary")

if btn:
    with st.spinner("Procesando datos Multi-Timeframe..."):
        # 1. Bajar datos Principales
        df_main = get_data(ticker, interval_main, period_map[interval_main])
        
        # 2. Bajar datos de Filtro (Siempre bajamos 'max' para cubrir todo el historial del main)
        df_filter = get_data(ticker, interval_filter, "max")
        
        if df_main is not None and df_filter is not None:
            # 3. Correr Estrategia
            res_df, df_chart = run_strategy_mtf(df_main, df_filter, adx_len, adx_th_micro, adx_th_macro)
            
            if not res_df.empty:
                # Buscar última compra
                buys = res_df[res_df['Tipo'] == '🟢 COMPRA']
                
                if not buys.empty:
                    last_buy = buys.iloc[-1]
                    
                    # MÉTRICAS
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Última Señal", last_buy['Fecha'].strftime('%d/%m/%Y'))
                    c2.metric("Precio Entrada", f"${last_buy['Precio']:.2f}")
                    c3.metric(f"ADX {interval_main} (Gatillo)", f"{last_buy['ADX Gatillo']:.1f}")
                    c4.metric(f"ADX {interval_filter} (Filtro)", f"{last_buy['ADX Filtro']:.1f}")
                
                st.divider()
                
                # TABLA
                st.subheader("📜 Bitácora de Alertas")
                res_view = res_df.copy()
                res_view['Fecha'] = res_view['Fecha'].dt.strftime('%Y-%m-%d')
                
                def color_rows(val):
                    color = '#d4edda' if 'COMPRA' in str(val) else '#f8d7da' if 'VENTA' in str(val) else ''
                    return f'background-color: {color}; color: black'
                
                st.dataframe(res_view.style.applymap(color_rows, subset=['Tipo']), use_container_width=True)
                
                # GRÁFICO
                st.subheader(f"Gráfico Heikin Ashi ({interval_main})")
                
                # Plot últimos 100 periodos para ver detalle
                chart_data = df_chart.tail(100)
                
                fig = go.Figure(data=[go.Candlestick(
                    x=chart_data.index,
                    open=chart_data['HA_Open'], high=chart_data['HA_High'],
                    low=chart_data['HA_Low'], close=chart_data['HA_Close'],
                    name='Heikin Ashi'
                )])
                
                # Marcas de Compra en el gráfico
                buy_dates = buys[buys['Fecha'].isin(chart_data.index)]
                if not buy_dates.empty:
                    fig.add_trace(go.Scatter(
                        x=buy_dates['Fecha'], y=buy_dates['Precio']*0.98,
                        mode='markers', marker=dict(symbol='triangle-up', size=15, color='#00FF00'),
                        name='Entrada'
                    ))

                fig.update_layout(height=600, xaxis_rangeslider_visible=False, template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)
                
            else:
                st.warning("No se encontraron señales. El filtro ADX podría ser muy estricto.")
        else:
            st.error("Error al descargar datos. Verifica el ticker.")
