import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Backtester de Señales HA + ADX", layout="wide")

# --- FUNCIONES DE CÁLCULO ---
def calculate_heikin_ashi(df):
    """
    Calcula Heikin Ashi de forma iterativa para coincidir con TradingView.
    """
    df_ha = df.copy()
    
    # 1. HA Close
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    # 2. HA Open (Iterativo es necesario para precisión)
    ha_open = [df['Open'].iloc[0]]
    for i in range(1, len(df)):
        # HA Open actual = (HA Open prev + HA Close prev) / 2
        prev_open = ha_open[-1]
        prev_close = df_ha['HA_Close'].iloc[i-1]
        ha_open.append((prev_open + prev_close) / 2)
        
    df_ha['HA_Open'] = ha_open
    
    # 3. HA High y Low
    df_ha['HA_High'] = df_ha[['High', 'HA_Open', 'HA_Close']].max(axis=1)
    df_ha['HA_Low'] = df_ha[['Low', 'HA_Open', 'HA_Close']].min(axis=1)
    
    # 4. Color (1 Verde, -1 Rojo)
    df_ha['Color'] = np.where(df_ha['HA_Close'] > df_ha['HA_Open'], 1, -1)
    
    return df_ha

def get_data(ticker, interval, period):
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False, auto_adjust=True)
        if df.empty: return None
        # Limpieza de columnas MultiIndex si existen
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except: return None

def run_strategy(df, adx_len, adx_th):
    # 1. Calcular ADX
    # Pandas TA requiere columnas específicas
    df.ta.adx(length=adx_len, append=True)
    # Renombrar columna ADX (suele ser ADX_14)
    adx_col = f"ADX_{adx_len}"
    
    # 2. Calcular Heikin Ashi
    df_ha = calculate_heikin_ashi(df)
    
    # 3. Simulación de Señales
    signals = []
    in_position = False
    entry_price = 0.0
    entry_date = None
    
    # Iteramos sobre el dataframe
    for i in range(1, len(df_ha)):
        date = df_ha.index[i]
        ha_color = df_ha['Color'].iloc[i]      # 1 Verde, -1 Rojo
        adx_val = df_ha[adx_col].iloc[i]
        price = df_ha['Close'].iloc[i]
        
        # CONDICIÓN DE ENTRADA (LONG)
        # Vela Verde + ADX > Umbral + No estamos comprados
        if not in_position and ha_color == 1 and adx_val > adx_th:
            in_position = True
            entry_price = price
            entry_date = date
            signals.append({
                'Fecha': date,
                'Tipo': '🟢 COMPRA',
                'Precio': price,
                'ADX': adx_val,
                'Resultado': '-'
            })
            
        # CONDICIÓN DE SALIDA (EXIT)
        # Vela se vuelve Roja + Estamos comprados
        elif in_position and ha_color == -1:
            in_position = False
            pnl = ((price - entry_price) / entry_price) * 100
            signals.append({
                'Fecha': date,
                'Tipo': '🔴 VENTA',
                'Precio': price,
                'ADX': adx_val,
                'Resultado': f"{pnl:.2f}%"
            })
            
    return pd.DataFrame(signals), df_ha

# --- UI STREAMLIT ---
st.title("🔎 Detector de Señales Históricas (Clon TradingView)")

with st.sidebar:
    st.header("Parámetros")
    ticker = st.text_input("Ticker", "AAPL").upper()
    
    # Configuración para replicar tu caso: Mensual
    interval = st.selectbox("Temporalidad", ["1mo", "1wk", "1d", "1h"], index=0)
    
    # Para mensual necesitamos mucha historia
    period_map = {"1mo": "max", "1wk": "10y", "1d": "5y", "1h": "730d"}
    
    st.divider()
    st.subheader("Estrategia")
    adx_len = st.number_input("Longitud ADX", value=14)
    adx_th = st.number_input("Umbral ADX (Filtro)", value=20) # En tu script era 20 el filtro macro

    if st.button("CALCULAR SEÑALES"):
        with st.spinner("Descargando y procesando..."):
            df = get_data(ticker, interval, period_map[interval])
            
            if df is not None:
                res_df, df_ha = run_strategy(df, adx_len, adx_th)
                
                # --- MOSTRAR RESULTADOS ---
                if not res_df.empty:
                    last_signal = res_df.iloc[-1]
                    
                    # MÉTRICAS DESTACADAS
                    c1, c2, c3 = st.columns(3)
                    
                    # Buscamos la última COMPRA específicamente
                    last_buy = res_df[res_df['Tipo'] == '🟢 COMPRA'].iloc[-1]
                    
                    c1.metric("Última Señal de COMPRA", last_buy['Fecha'].strftime('%d-%m-%Y'))
                    c2.metric("Precio de Entrada", f"${last_buy['Precio']:.2f}")
                    c3.metric("ADX en ese momento", f"{last_buy['ADX']:.2f}")
                    
                    st.divider()
                    
                    # TABLA COMPLETA
                    st.subheader("📜 Historial de Alertas")
                    # Formatear fecha
                    res_df['Fecha'] = res_df['Fecha'].dt.strftime('%Y-%m-%d')
                    st.dataframe(res_df.style.map(lambda x: 'color: green' if 'COMPRA' in x else 'color: red', subset=['Tipo']), use_container_width=True)
                    
                    # GRÁFICO
                    st.subheader("Gráfico Heikin Ashi")
                    
                    # Filtramos data reciente para el gráfico (últimos 50 periodos para que se vea bien)
                    chart_data = df_ha.tail(60) 
                    
                    fig = go.Figure(data=[go.Candlestick(
                        x=chart_data.index,
                        open=chart_data['HA_Open'],
                        high=chart_data['HA_High'],
                        low=chart_data['HA_Low'],
                        close=chart_data['HA_Close'],
                        name='Heikin Ashi'
                    )])
                    
                    # Agregar marcas de compra
                    buys = res_df[res_df['Tipo'] == '🟢 COMPRA']
                    # Filtramos las compras que estén dentro del rango del gráfico
                    buys_visible = buys[buys['Fecha'].isin(chart_data.index.strftime('%Y-%m-%d'))]
                    
                    if not buys_visible.empty:
                        # Necesitamos volver a convertir la fecha string a datetime para plotear
                        buy_dates = pd.to_datetime(buys_visible['Fecha'])
                        fig.add_trace(go.Scatter(
                            x=buy_dates,
                            y=buys_visible['Precio'] * 0.95, # Un poco abajo de la vela
                            mode='markers',
                            marker=dict(symbol='triangle-up', size=15, color='blue'),
                            name='Señal Compra'
                        ))

                    fig.update_layout(xaxis_rangeslider_visible=False, height=500)
                    st.plotly_chart(fig, use_container_width=True)
                    
                else:
                    st.warning("No se encontraron señales con estos parámetros.")
            else:
                st.error("No se encontraron datos para el ticker.")
