import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader 360: Decision Engine")

# --- ESTILOS ---
st.markdown("""
<style>
    .metric-card {
        background-color: #0E1117;
        border: 1px solid #303030;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
    }
    .big-score { font-size: 3rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS UNIFICADA ---
TICKERS_MASTER = sorted([
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'AMD', 'NFLX', 
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'MELI', 'GLOB', 'VIST',
    'SPY', 'QQQ', 'IWM', 'DIA', 'ARKK', 'GLD', 'SLV', 'BTC-USD',
    'KO', 'PEP', 'MCD', 'DIS', 'JPM', 'BAC', 'C', 'XOM', 'CVX'
])

# --- FUNCIONES CORE (FUSIÓN DE TUS SCRIPTS) ---

# 1. ANÁLISIS TÉCNICO (HEIKIN ASHI)
def get_technical_score(df):
    """Retorna un puntaje de 0 a 10 basado en alineación de tendencias"""
    score = 0
    if df.empty: return 0, "Sin Datos"
    
    # Heikin Ashi Logic simplificada para velocidad
    try:
        df_ha = df.copy()
        df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
        df_ha['HA_Open'] = (df['Open'].shift(1) + df['Close'].shift(1)) / 2
        
        # Última vela diaria
        last = df_ha.iloc[-1]
        bullish_day = last['HA_Close'] > last['HA_Open']
        
        # Media Móvil 20 y 50 (Tendencia macro)
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        price = df['Close'].iloc[-1]
        
        details = []
        if bullish_day: 
            score += 3
            details.append("Vela HA Diaria Alcista (+3)")
        else:
            details.append("Vela HA Diaria Bajista (0)")
            
        if price > ma20: 
            score += 3
            details.append("Precio sobre MA20 (+3)")
        
        if ma20 > ma50: 
            score += 4
            details.append("Cruce de Oro / Tendencia Sana (+4)")
            
        return score, ", ".join(details)
    except:
        return 0, "Error Cálculo"

# 2. ANÁLISIS ESTRUCTURAL (OPCIONES)
def get_options_score(ticker, current_price):
    """Retorna puntaje 0-10 basado en distancia a Muros"""
    try:
        tk = yf.Ticker(ticker)
        exps = tk.options
        if not exps: return 5, "Sin Opciones (Neutral)" # Neutral
        
        opt = tk.option_chain(exps[0])
        calls = opt.calls
        puts = opt.puts
        
        if calls.empty or puts.empty: return 5, "Data Incompleta"
        
        # Call Wall (Resistencia)
        call_wall = calls.loc[calls['openInterest'].idxmax()]['strike']
        # Put Wall (Soporte)
        put_wall = puts.loc[puts['openInterest'].idxmax()]['strike']
        
        # Lógica:
        # Si precio está cerca del Call Wall -> Bajista (Resistencia)
        # Si precio está cerca del Put Wall -> Alcista (Soporte)
        # Si rompió Call Wall -> Muy Alcista (Gamma Squeeze)
        
        dist_call = (call_wall - current_price) / current_price
        dist_put = (current_price - put_wall) / current_price
        
        score = 5 # Base neutral
        detail = ""
        
        if current_price > call_wall:
            score = 10
            detail = "🚀 ROMPIÓ TECHO (Posible Squeeze)"
        elif dist_call < 0.02: # Menos del 2% del techo
            score = 2
            detail = "🧱 Pegado a Resistencia (Peligro)"
        elif dist_put < 0.02: # Menos del 2% del piso
            score = 9
            detail = "🟢 En Soporte Fuerte (Compra)"
        else:
            # En el medio del rango
            relative_pos = (current_price - put_wall) / (call_wall - put_wall)
            # Si está más cerca del piso (0) es mejor compra que cerca del techo (1)
            score = 10 - (relative_pos * 10)
            detail = f"Rango Medio ({call_wall}/{put_wall})"
            
        return score, detail, call_wall, put_wall
        
    except:
        return 5, "Error Opciones", 0, 0

# 3. ANÁLISIS ESTACIONAL (HISTÓRICO)
def get_seasonality_score(df):
    """Retorna puntaje 0-10 basado en Win Rate del mes actual"""
    try:
        current_month = datetime.now().month
        
        monthly_ret = df['Close'].resample('ME').last().pct_change()
        monthly_ret = monthly_ret[monthly_ret.index.month == current_month]
        
        if len(monthly_ret) < 3: return 5, "Poca Data Histórica"
        
        win_rate = (monthly_ret > 0).mean() # 0.0 a 1.0
        avg_return = monthly_ret.mean()
        
        # Score directo: Win Rate * 10
        score = win_rate * 10
        detail = f"WinRate Histórico: {win_rate:.0%} (Avg: {avg_return:.1%})"
        
        return score, detail
    except:
        return 5, "Error Estacionalidad"

# --- INTERFAZ PRINCIPAL ---

st.title("🧠 SystemaTrader 360: Motor de Decisión")
st.markdown("Algoritmo de Fusión: **Técnico (40%) + Estructural (30%) + Estacional (30%)**")

# Selector
selected_ticker = st.selectbox("Selecciona Activo a Auditar:", TICKERS_MASTER)

if st.button("ANALIZAR ACTIVO", type="primary"):
    with st.spinner(f"Corriendo simulación para {selected_ticker}..."):
        
        # 1. Obtener Datos Históricos (1 Año para todo)
        tk = yf.Ticker(selected_ticker)
        df = tk.history(period="2y")
        
        if not df.empty:
            current_price = df['Close'].iloc[-1]
            
            # 2. Calcular Scores Individuales
            score_tech, desc_tech = get_technical_score(df)
            score_struct, desc_struct, cw, pw = get_options_score(selected_ticker, current_price)
            score_season, desc_season = get_seasonality_score(df)
            
            # 3. PONDERACIÓN FINAL (ALGORITMO)
            # Escala 0-100
            final_score = (score_tech * 4) + (score_struct * 3) + (score_season * 3)
            
            # --- PRESENTACIÓN DE RESULTADOS ---
            
            # Bloque Superior: Veredicto
            st.divider()
            c_score, c_verdict = st.columns([1, 3])
            
            with c_score:
                color = "green" if final_score > 70 else "red" if final_score < 40 else "orange"
                st.markdown(f"""
                <div class="metric-card">
                    <div style="font-size: 1rem; color: #888;">Puntaje Crítico</div>
                    <div class="big-score" style="color: {color};">{final_score:.0f}/100</div>
                </div>
                """, unsafe_allow_html=True)
                
            with c_verdict:
                if final_score >= 80:
                    st.success("🔥 COMPRA FUERTE: Todos los sistemas alineados. La tendencia es alcista, hay espacio en opciones y la estacionalidad acompaña.")
                elif final_score >= 60:
                    st.success("✅ COMPRA MODERADA: Buen aspecto técnico, pero verificar resistencias cercanas.")
                elif final_score >= 40:
                    st.warning("⚖️ HOLD / NEUTRAL: Señales mixtas. Esperar definición.")
                elif final_score >= 20:
                    st.error("🔻 VENTA / EVITAR: Estructura débil o resistencias fuertes.")
                else:
                    st.error("💀 VENTA FUERTE: Activo técnicamente roto y estacionalmente negativo.")

            st.divider()
            
            # Bloque Inferior: Desglose
            k1, k2, k3 = st.columns(3)
            
            k1.metric("🛠️ Análisis Técnico (40%)", f"{score_tech}/10", desc_tech)
            k1.progress(score_tech/10)
            
            k2.metric("🧱 Estructura/Opciones (30%)", f"{score_struct:.1f}/10", desc_struct)
            k2.progress(score_struct/10)
            if cw > 0:
                k2.caption(f"Rango Operativo: ${pw:.0f} - ${cw:.0f}")
            
            k3.metric("📅 Estacionalidad (30%)", f"{score_season:.1f}/10", desc_season)
            k3.progress(score_season/10)
            
            # Gráfico Rápido
            st.subheader("Gráfico de Referencia")
            fig = go.Figure(data=[go.Candlestick(x=df.index,
                open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            
            # Agregar Muros si existen
            if cw > 0:
                fig.add_hline(y=cw, line_dash="dash", line_color="red", annotation_text="Call Wall")
                fig.add_hline(y=pw, line_dash="dash", line_color="green", annotation_text="Put Wall")
                
            fig.update_layout(height=400, margin=dict(t=20, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

        else:
            st.error("No se pudieron obtener datos del activo.")
