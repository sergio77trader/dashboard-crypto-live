import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import time

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="Crypto-Radar 360: Sniper")

# --- ESTILOS VISUALES (Ciberpunk / Dark Mode Friendly) ---
st.markdown("""
<style>
    .crypto-card {
        background-color: #111111;
        border: 1px solid #333;
        padding: 15px; border-radius: 10px;
        text-align: center; margin-bottom: 10px;
    }
    .score-green { color: #00FF00; font-weight: bold; font-size: 1.5rem; }
    .score-red { color: #FF0000; font-weight: bold; font-size: 1.5rem; }
    .score-neutral { color: #FFFF00; font-weight: bold; font-size: 1.5rem; }
    
    .signal-box {
        padding: 5px 10px; border-radius: 5px; font-weight: bold; text-align: center; margin-top: 5px;
    }
    .sig-long { background-color: rgba(0, 255, 0, 0.1); color: #00FF00; border: 1px solid #00FF00; }
    .sig-short { background-color: rgba(255, 0, 0, 0.1); color: #FF0000; border: 1px solid #FF0000; }
    .sig-wait { background-color: rgba(128, 128, 128, 0.1); color: #AAA; border: 1px solid #555; }
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS BINANCE FUTURES (Proxy Yahoo) ---
CRYPTO_DB = {
    '👑 Layer 1 (Majors)': ['BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'ADA-USD', 'AVAX-USD', 'TRX-USD', 'TON11419-USD'],
    '🐸 Memecoins (Alta Volatilidad)': ['DOGE-USD', 'SHIB-USD', 'PEPE24478-USD', 'WIF-USD', 'FLOKI-USD', 'BONK-USD', 'DOGS-USD'],
    '🤖 AI & Big Data': ['FET-USD', 'RNDR-USD', 'NEAR-USD', 'ICP-USD', 'TAO22974-USD', 'WLD-USD', 'ARKM-USD'],
    '🔗 DeFi & Infra': ['LINK-USD', 'UNI7083-USD', 'AAVE-USD', 'LDO-USD', 'MKR-USD', 'JUP-USD', 'PYTH-USD'],
    '⚡ Layer 2': ['MATIC-USD', 'ARB11841-USD', 'OP-USD', 'IMX-USD', 'STX4847-USD'],
    '🎮 Gaming & Metaverse': ['SAND-USD', 'MANA-USD', 'AXS-USD', 'GALA-USD', 'APE-USD', 'BEAM28298-USD'],
    '👵 Legacy / PoW': ['LTC-USD', 'BCH-USD', 'ETC-USD', 'XMR-USD', 'XLM-USD', 'XRP-USD']
}

# Lista plana para descarga masiva
ALL_COINS = sorted(list(set([item for sublist in CRYPTO_DB.values() for item in sublist])))

# --- INICIALIZAR ESTADO ---
if 'crypto_data' not in st.session_state: st.session_state['crypto_data'] = []

# --- INDICADORES TÉCNICOS ---
def calculate_indicators(df):
    try:
        # 1. EMAs (Tendencia)
        df['EMA8'] = df['Close'].ewm(span=8, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        # 2. RSI (Momento)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 3. ADX (Fuerza - El Filtro de Ruido)
        # Calculo simplificado de ADX para velocidad
        df['TR'] = np.maximum(df['High'] - df['Low'], np.maximum(abs(df['High'] - df['Close'].shift()), abs(df['Low'] - df['Close'].shift())))
        df['ATR'] = df['TR'].rolling(14).mean()
        df['DMplus'] = np.where((df['High']-df['High'].shift()) > (df['Low'].shift()-df['Low']), np.maximum(df['High']-df['High'].shift(), 0), 0)
        df['DMminus'] = np.where((df['Low'].shift()-df['Low']) > (df['High']-df['High'].shift()), np.maximum(df['Low'].shift()-df['Low'], 0), 0)
        df['DIplus'] = 100 * (df['DMplus'].rolling(14).mean() / df['ATR'])
        df['DIminus'] = 100 * (df['DMminus'].rolling(14).mean() / df['ATR'])
        df['DX'] = 100 * abs(df['DIplus'] - df['DIminus']) / (df['DIplus'] + df['DIminus'])
        df['ADX'] = df['DX'].rolling(14).mean()
        
        # 4. Bollinger Squeeze (Explosión)
        df['SMA20'] = df['Close'].rolling(20).mean()
        df['StdDev'] = df['Close'].rolling(20).std()
        df['Upper'] = df['SMA20'] + (2 * df['StdDev'])
        df['Lower'] = df['SMA20'] - (2 * df['StdDev'])
        df['BandWidth'] = (df['Upper'] - df['Lower']) / df['SMA20']
        
        # 5. Volumen Relativo
        df['VolAvg'] = df['Volume'].rolling(20).mean()
        df['RVOL'] = df['Volume'] / df['VolAvg']
        
        return df
    except: return pd.DataFrame()

# --- LÓGICA DE BTC (SEMÁFORO MACRO) ---
def get_btc_context():
    try:
        btc = yf.download("BTC-USD", period="3mo", progress=False)
        btc = calculate_indicators(btc)
        last = btc.iloc[-1]
        
        trend = "ALCISTA" if last['Close'] > last['EMA50'] else "BAJISTA"
        strength = "Fuerte" if last['ADX'] > 25 else "Débil/Rango"
        
        return trend, strength, last['Close']
    except: return "NEUTRAL", "Error", 0

# --- ANÁLISIS INDIVIDUAL ---
def analyze_coin(ticker, df_hist):
    try:
        if df_hist.empty or len(df_hist) < 50: return None
        
        df = calculate_indicators(df_hist.copy())
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- SISTEMA DE PUNTUACIÓN (0 a 10) ---
        score = 5
        reasons = []
        
        # 1. Tendencia (EMA 8/21 Cross)
        if last['EMA8'] > last['EMA21']: 
            score += 2
            if last['Close'] > last['EMA8']: score += 1 # Momentum fuerte
        else:
            score -= 2
            if last['Close'] < last['EMA8']: score -= 1
            
        # 2. Fuerza (ADX) - El filtro anti-ruido
        if last['ADX'] > 25:
            reasons.append(f"💪 Tendencia Fuerte (ADX {last['ADX']:.0f})")
            score += 1 if score > 5 else -1 # Potencia la dirección actual
        else:
            reasons.append("💤 Zona de Ruido/Rango")
            # Si hay ruido, el score tiende a 5 (Neutral)
            if score > 5: score -= 1
            if score < 5: score += 1
            
        # 3. Squeeze (Volatilidad)
        avg_bw = df['BandWidth'].rolling(50).mean().iloc[-1]
        is_squeeze = last['BandWidth'] < (avg_bw * 0.9)
        if is_squeeze:
            reasons.append("💣 SQUEEZE (Posible Explosión)")
            # El squeeze no da dirección, solo alerta
            
        # 4. Volumen (Ballenas)
        if last['RVOL'] > 2.0:
            score += 2 if score > 5 else -2 # Confirma el movimiento
            reasons.append(f"🔥 Volumen Climático (x{last['RVOL']:.1f})")
        elif last['RVOL'] < 0.5:
            reasons.append("🧊 Sin Volumen")
            
        # --- SEÑAL FINAL ---
        signal = "ESPERAR ✋"
        if score >= 8 and last['ADX'] > 20: signal = "LONG 🟢"
        elif score <= 2 and last['ADX'] > 20: signal = "SHORT 🔴"
        
        return {
            "Ticker": ticker.replace("-USD", ""),
            "Price": last['Close'],
            "Change 24h": ((last['Close'] - prev['Close'])/prev['Close']) * 100,
            "Signal": signal,
            "Score": score,
            "RVOL": last['RVOL'],
            "ADX": last['ADX'],
            "Squeeze": is_squeeze,
            "Reasons": ", ".join(reasons)
        }
    except: return None

# --- UI ---
with st.sidebar:
    st.title("🎛️ Radar Cripto")
    
    # Selector de Lote por Narrativa
    narrative = st.selectbox("Seleccionar Narrativa:", list(CRYPTO_DB.keys()))
    
    c1, c2 = st.columns(2)
    if c1.button("🚀 ESCANEAR", type="primary"):
        targets = CRYPTO_DB[narrative]
        prog = st.progress(0)
        st_txt = st.empty()
        
        # Descarga Masiva (Optimización de velocidad)
        st_txt.text("Descargando datos de mercado...")
        try:
            # Descargamos todo junto para no hacer 50 llamadas
            data = yf.download(targets, period="3mo", group_by='ticker', progress=False)
            
            results = []
            for i, t in enumerate(targets):
                st_txt.text(f"Analizando {t}...")
                
                # Manejo de MultiIndex de Pandas
                try:
                    if len(targets) > 1: df_coin = data[t]
                    else: df_coin = data
                except: continue
                
                # Limpiar NAs
                df_coin = df_coin.dropna()
                
                res = analyze_coin(t, df_coin)
                if res: results.append(res)
                prog.progress((i+1)/len(targets))
            
            st.session_state['crypto_data'] = results
            st_txt.empty()
            prog.empty()
            
        except Exception as e:
            st.error(f"Error de conexión: {e}")

    if c2.button("🗑️ Limpiar"): st.session_state['crypto_data'] = []; st.rerun()

# --- VISTA PRINCIPAL ---
st.title("🛰️ Crypto-Radar 360: Futuros & Perpetuos")

# 1. CONTEXTO BITCOIN (El Rey)
btc_trend, btc_str, btc_price = get_btc_context()
btc_color = "green" if btc_trend == "ALCISTA" else "red"
st.markdown(f"""
<div style="padding:15px; border:1px solid #333; border-radius:10px; background:#0e1117; margin-bottom:20px;">
    <h3 style="margin:0;">BITCOIN (El Clima): <span style="color:{btc_color}">{btc_trend}</span> (${btc_price:,.0f})</h3>
    <p style="margin:0; color:#888;">Fuerza de tendencia: {btc_str} | Si BTC está bajista, cuidado con los LONGS en Altcoins.</p>
</div>
""", unsafe_allow_html=True)

# 2. RESULTADOS
if st.session_state['crypto_data']:
    df = pd.DataFrame(st.session_state['crypto_data'])
    
    # Filtros Rápidos
    f_mode = st.radio("Filtro:", ["Ver Todo", "Solo Oportunidades (Long/Short)", "Solo Squeeze (A punto de explotar)"], horizontal=True)
    
    if f_mode == "Solo Oportunidades (Long/Short)":
        df = df[df['Signal'] != "ESPERAR ✋"]
    elif f_mode == "Solo Squeeze (A punto de explotar)":
        df = df[df['Squeeze'] == True]
    
    # Ordenar por Score (Los extremos primero)
    df['AbsScore'] = abs(df['Score'] - 5) # Para mostrar los 10 y los 0 primero
    df = df.sort_values('AbsScore', ascending=False)
    
    # MOSTRAR TARJETAS
    cols = st.columns(4)
    for i, row in df.iterrows():
        with cols[i % 4]:
            # Colores dinámicos
            sig_class = "sig-long" if "LONG" in row['Signal'] else "sig-short" if "SHORT" in row['Signal'] else "sig-wait"
            price_col = "green" if row['Change 24h'] > 0 else "red"
            
            st.markdown(f"""
            <div class="crypto-card">
                <div style="font-size:1.2rem; font-weight:bold;">{row['Ticker']}</div>
                <div style="font-size:1rem; color:{price_col};">${row['Price']:.4f} ({row['Change 24h']:.2f}%)</div>
                <div class="signal-box {sig_class}">{row['Signal']}</div>
                <div style="font-size:0.8rem; margin-top:8px; color:#aaa;">{row['Reasons'] if row['Reasons'] else "Sin señales claras"}</div>
                <div style="font-size:0.7rem; margin-top:5px; color:#666;">RVOL: {row['RVOL']:.1f}x | ADX: {row['ADX']:.0f}</div>
            </div>
            """, unsafe_allow_html=True)

else:
    st.info("👈 Selecciona una Narrativa (ej: AI, Memes) y dale a ESCANEAR.")
