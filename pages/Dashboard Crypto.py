import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import re

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="Crypto-Radar 360: Sniper V2.3")

# --- ESTILOS VISUALES ---
st.markdown("""
<style>
    .crypto-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 15px; 
        border-radius: 10px;
        text-align: center; 
        margin-bottom: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .signal-box {
        padding: 5px; border-radius: 5px; font-weight: bold; 
        text-align: center; margin-top: 10px; letter-spacing: 1px; font-size: 0.9rem;
    }
    .sig-long { background-color: rgba(35, 134, 54, 0.2); color: #3fb950; border: 1px solid #3fb950; }
    .sig-short { background-color: rgba(218, 54, 51, 0.2); color: #f85149; border: 1px solid #f85149; }
    .sig-wait { background-color: rgba(139, 148, 158, 0.2); color: #8b949e; border: 1px solid #30363d; }
    
    .alert-pill { 
        font-size: 0.75rem; font-weight: bold; padding: 2px 8px; 
        border-radius: 10px; margin: 3px; display: inline-block; 
    }
    .sqz-anim { 
        animation: pulse 1.5s infinite; 
        color: #ff9b00; border: 1px solid #ff9b00; 
        background-color: rgba(255, 155, 0, 0.1);
    }
    @keyframes pulse { 0% {opacity: 1;} 50% {opacity: 0.5;} 100% {opacity: 1;} }
    
    .audit-text { font-size: 0.9rem; color: #ccc; margin-bottom: 5px; }
    .audit-check { color: #3fb950; font-weight: bold; }
    .audit-cross { color: #f85149; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
CRYPTO_DB = {
    '👑 Majors (L1)': ['BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'ADA-USD', 'XRP-USD', 'AVAX-USD', 'TRX-USD', 'DOT-USD', 'LINK-USD', 'MATIC-USD'],
    '🐸 Memecoins': ['DOGE-USD', 'SHIB-USD', 'PEPE24478-USD', 'WIF-USD', 'FLOKI-USD', 'BONK-USD', 'DOGS-USD', 'POPCAT-USD'],
    '🤖 AI & DePIN': ['FET-USD', 'RNDR-USD', 'TAO22974-USD', 'WLD-USD', 'ARKM-USD', 'AGIX-USD', 'JASMY-USD', 'NEAR-USD', 'ICP-USD'],
    '🔗 DeFi & DEX': ['UNI7083-USD', 'AAVE-USD', 'LDO-USD', 'MKR-USD', 'JUP-USD', 'PYTH-USD', 'ENA-USD', 'RUNE-USD'],
    '⚡ Layer 2': ['ARB11841-USD', 'OP-USD', 'IMX-USD', 'STX4847-USD', 'MANTLE-USD', 'STRK-USD'],
    '🎮 Gaming': ['SAND-USD', 'MANA-USD', 'AXS-USD', 'GALA-USD', 'APE-USD', 'BEAM28298-USD'],
    '👵 Legacy': ['LTC-USD', 'BCH-USD', 'ETC-USD', 'XMR-USD', 'XLM-USD', 'EOS-USD']
}

if 'crypto_acc_v3' not in st.session_state: st.session_state['crypto_acc_v3'] = []

# --- INDICADORES ---
def calculate_indicators(df):
    try:
        df['EMA8'] = df['Close'].ewm(span=8, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        
        # ADX
        df['TR'] = np.maximum(df['High'] - df['Low'], np.maximum(abs(df['High'] - df['Close'].shift()), abs(df['Low'] - df['Close'].shift())))
        df['ATR'] = df['TR'].rolling(14).mean()
        df['DMplus'] = np.where((df['High']-df['High'].shift())>(df['Low'].shift()-df['Low']), np.maximum(df['High']-df['High'].shift(),0), 0)
        df['DMminus'] = np.where((df['Low'].shift()-df['Low'])>(df['High']-df['High'].shift()), np.maximum(df['Low'].shift()-df['Low'],0), 0)
        df['DIplus'] = 100*(df['DMplus'].rolling(14).mean()/df['ATR'])
        df['DIminus'] = 100*(df['DMminus'].rolling(14).mean()/df['ATR'])
        df['DX'] = 100*abs(df['DIplus']-df['DIminus'])/(df['DIplus']+df['DIminus'])
        df['ADX'] = df['DX'].rolling(14).mean()
        
        # Bollinger
        df['SMA20'] = df['Close'].rolling(20).mean()
        df['StdDev'] = df['Close'].rolling(20).std()
        df['Upper'] = df['SMA20']+(2*df['StdDev'])
        df['Lower'] = df['SMA20']-(2*df['StdDev'])
        df['BandWidth'] = (df['Upper']-df['Lower'])/df['SMA20']
        
        # RVOL
        df['VolAvg'] = df['Volume'].rolling(20).mean()
        df['RVOL'] = df['Volume']/df['VolAvg']
        
        return df
    except: return pd.DataFrame()

# --- CONTEXTO BTC ---
def get_btc_context():
    try:
        btc = yf.Ticker("BTC-USD").history(period="3mo")
        if btc.empty: return "NEUTRAL", 0
        
        btc['EMA50'] = btc['Close'].ewm(span=50).mean()
        last = btc.iloc[-1]
        
        trend = "ALCISTA" if last['Close'] > last['EMA50'] else "BAJISTA"
        return trend, last['Close']
    except: 
        return "NEUTRAL (Sin Datos)", 0

# --- ANALISIS ---
def analyze_coin(ticker, df_hist):
    try:
        if df_hist.empty or len(df_hist) < 50: return None
        
        df = calculate_indicators(df_hist.copy())
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # AUDITORÍA DETALLADA
        audit_log = []
        score = 5 # Base Neutral
        
        # 1. Tendencia (EMA Cross)
        if last['EMA8'] > last['EMA21']: 
            score += 2
            audit_log.append("✅ Tendencia Alcista (EMA8 > EMA21) [+2]")
            if last['Close'] > last['EMA8']: 
                score += 1
                audit_log.append("✅ Momentum Fuerte (Precio > EMA8) [+1]")
        else:
            score -= 2
            audit_log.append("❌ Tendencia Bajista (EMA8 < EMA21) [-2]")
            if last['Close'] < last['EMA8']: 
                score -= 1
                audit_log.append("❌ Momentum Débil (Precio < EMA8) [-1]")
            
        # 2. ADX (Fuerza)
        if last['ADX'] > 25:
            audit_log.append(f"💪 Tendencia con Fuerza (ADX {last['ADX']:.0f} > 25)")
            score += 1 if score > 5 else -1 # Potencia la dirección
        else:
            audit_log.append(f"💤 Mercado Lateral/Ruido (ADX {last['ADX']:.0f} < 25) -> Score tiende a 5")
            # Pull to neutral
            if score > 5: score -= 1
            if score < 5: score += 1
            
        # 3. Squeeze
        avg_bw = df['BandWidth'].rolling(50).mean().iloc[-1]
        is_squeeze = False
        if last['BandWidth'] < (avg_bw * 0.9): 
            is_squeeze = True
            audit_log.append("💣 BOLLINGER SQUEEZE DETECTADO (Alerta de Explosión)")
            
        # 4. Volumen
        rvol = last['RVOL']
        if rvol > 2.0:
            score += 2 if score > 5 else -2
            audit_log.append(f"🔥 Volumen Climático (x{rvol:.1f}) [Magnifica Señal]")
        elif rvol < 0.5:
            audit_log.append("🧊 Volumen muy bajo (Poco interés)")
            
        # Señal Final
        signal = "ESPERAR ✋"
        if score >= 8 and last['ADX'] > 20: signal = "LONG 🟢"
        elif score <= 2 and last['ADX'] > 20: signal = "SHORT 🔴"
        
        # Alertas simples para la tarjeta
        alerts = []
        if is_squeeze: alerts.append("💣 SQUEEZE")
        if rvol > 1.5: alerts.append(f"⚡ VOL x{rvol:.1f}")
        
        return {
            "Ticker": ticker.replace("-USD", ""),
            "Price": last['Close'],
            "Change": ((last['Close']-prev['Close'])/prev['Close'])*100,
            "Signal": signal,
            "Score": score,
            "RVOL": last['RVOL'],
            "ADX": last['ADX'],
            "Audit": audit_log, # Lista detallada para el explicador
            "Alerts": alerts
        }
    except: return None

# --- PROCESSOR ---
def run_scan(target_list):
    prog = st.progress(0)
    st_txt = st.empty()
    
    current_tickers = [x['Ticker'] for x in st.session_state['crypto_acc_v3']]
    
    clean_targets = []
    # FIX DE LA LISTA MANUAL
    for t in target_list:
        # Limpieza básica: Sacar espacios, poner mayúsculas
        clean_t = t.strip().upper()
        
        # Si dice USDT, cambiar a USD (Yahoo usa -USD)
        if clean_t.endswith("USDT"):
            clean_t = clean_t.replace("USDT", "")
        # Si dice USD al final sin guion (ej BTCUSD), arreglar
        elif clean_t.endswith("USD") and not clean_t.endswith("-USD"):
            clean_t = clean_t.replace("USD", "")
        
        # Quitar el -USD si el usuario lo puso, para estandarizar
        clean_t = clean_t.replace("-USD", "")
        
        # Verificar si ya está en memoria
        if clean_t not in current_tickers:
            # Reconstruir formato Yahoo
            clean_targets.append(f"{clean_t}-USD")
    
    if not clean_targets:
        st.toast("Monedas ya en lista o formato inválido.", icon="ℹ️")
        prog.empty()
        return

    st_txt.text(f"Conectando para {len(clean_targets)} activos...")
    try:
        data = yf.download(clean_targets, period="3mo", group_by='ticker', progress=False)
        new_results = []
        
        # Caso especial: Si solo es 1 activo, yfinance no devuelve MultiIndex a veces
        if len(clean_targets) == 1:
            t = clean_targets[0]
            st_txt.text(f"Procesando {t}...")
            # Si data es DataFrame simple, lo usamos directo
            df_coin = data
            if not df_coin.empty:
                res = analyze_coin(t, df_coin)
                if res: new_results.append(res)
            prog.progress(100)
        else:
            for i, t in enumerate(clean_targets):
                st_txt.text(f"Procesando {t}...")
                try:
                    df_coin = data[t].dropna()
                    res = analyze_coin(t, df_coin)
                    if res: new_results.append(res)
                except: pass
                prog.progress((i+1)/len(clean_targets))
        
        st.session_state['crypto_acc_v3'].extend(new_results)
        st.toast(f"Agregadas {len(new_results)} criptos.", icon="🚀")
        
    except Exception as e: st.error(f"Error: {e}")
    
    st_txt.empty(); prog.empty()

# --- UI ---
with st.sidebar:
    st.title("🎛️ Centro de Comando")
    
    trend, price = get_btc_context()
    btc_col = "green" if trend == "ALCISTA" else "red"
    price_display = f"${price:,.0f}" if price > 0 else "Cargando..."
    
    st.markdown(f"""
    <div style='padding:10px; border:1px solid #333; border-radius:5px; text-align:center; background-color:#0d1117;'>
        <div style='font-size:0.8rem; color:#888;'>Clima Bitcoin</div>
        <div style='font-size:1.2rem; font-weight:bold; color:{btc_col};'>{trend}</div>
        <div style='font-size:0.9rem;'>{price_display}</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    narrative = st.selectbox("Selecciona Lote:", list(CRYPTO_DB.keys()))
    if st.button("📡 Escanear Sector"): run_scan(CRYPTO_DB[narrative])
        
    st.divider()
    
    # INPUT MANUAL MEJORADO
    st.markdown("### 📝 Lista Manual")
    st.caption("Escribe tickers separados por coma o espacio (ej: BTC, ETH, PEPE). El sistema agrega '-USD' solo.")
    custom_txt = st.text_area("Ingresar Criptos:", height=70)
    
    if st.button("🔎 Analizar Mi Lista"):
        if custom_txt:
            # Regex para separar por comas, espacios o saltos de linea
            raw_list = re.split(r'[,\s\n]+', custom_txt)
            # Filtramos vacíos
            raw_list = [x for x in raw_list if x]
            if raw_list: run_scan(raw_list)
                
    st.divider()
    if st.button("🗑️ Borrar Todo"): st.session_state['crypto_acc_v3'] = []; st.rerun()

# --- MAIN ---
st.title("🛰️ Crypto-Radar 360: Sniper V2.3")

if st.session_state['crypto_acc_v3']:
    df = pd.DataFrame(st.session_state['crypto_acc_v3'])
    
    c_f1, c_f2 = st.columns([3, 1])
    with c_f1:
        f_mode = st.radio("Filtro:", ["Ver Todo", "Solo LONG 🟢", "Solo SHORT 🔴", "Solo SQUEEZE 💣"], horizontal=True)
    
    if f_mode == "Solo LONG 🟢": df = df[df['Signal'].str.contains("LONG")]
    elif f_mode == "Solo SHORT 🔴": df = df[df['Signal'].str.contains("SHORT")]
    elif f_mode == "Solo SQUEEZE 💣": df = df[df['Alerts'].apply(lambda x: any("SQUEEZE" in s for s in x))]
    
    if not df.empty:
        df['AbsScore'] = abs(df['Score'] - 5)
        df = df.sort_values('AbsScore', ascending=False)
    
        cols = st.columns(4)
        for i, row in df.iterrows():
            with cols[i % 4]:
                sig_class = "sig-long" if "LONG" in row['Signal'] else "sig-short" if "SHORT" in row['Signal'] else "sig-wait"
                price_col = "#3fb950" if row['Change'] > 0 else "#f85149"
                
                alert_html = ""
                for alert in row['Alerts']:
                    cls = "sqz-anim" if "SQUEEZE" in alert else "alert-pill"
                    bg = "rgba(255, 155, 0, 0.2)" if "SQUEEZE" in alert else "rgba(100, 100, 255, 0.2)"
                    alert_html += f"<span class='alert-pill {cls}' style='background:{bg}; color:#fff;'>{alert}</span> "
                
                # CARD HTML
                html_card = f"""
<div class="crypto-card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
        <span style="font-weight:bold; font-size:1.2rem;">{row['Ticker']}</span>
        <span style="color:{price_col}; font-weight:bold;">{row['Change']:+.2f}%</span>
    </div>
    <div style="font-size:0.9rem; color:#ccc;">${row['Price']:.4f}</div>
    <div class="signal-box {sig_class}">{row['Signal']}</div>
    <div style="margin: 10px 0;">{alert_html}</div>
    <div style="font-size:0.75rem; color:#8b949e; border-top:1px solid #30363d; padding-top:8px;">
        RVOL: {row['RVOL']:.1f}x | ADX: {row['ADX']:.0f}
    </div>
</div>
"""
                st.markdown(html_card, unsafe_allow_html=True)
                
    else:
        st.info("No hay activos para el filtro seleccionado.")
    
    # --- SECCIÓN DE AUDITORÍA ---
    st.divider()
    st.subheader("3. 🔬 Auditoría de Señal")
    st.caption("Selecciona una criptomoneda para entender por qué dio esa señal.")
    
    # Selector de monedas ya analizadas
    audit_ticker = st.selectbox("Seleccionar Activo para inspeccionar:", df['Ticker'].tolist())
    
    # Buscar datos
    audit_item = next((x for x in st.session_state['crypto_acc_v3'] if x['Ticker'] == audit_ticker), None)
    
    if audit_item:
        with st.expander(f"Desglose de cálculo para {audit_ticker} (Score: {audit_item['Score']}/10)", expanded=True):
            st.markdown(f"**Señal Final:** {audit_item['Signal']}")
            st.markdown("---")
            for log in audit_item['Audit']:
                st.markdown(f"- {log}")
            
            st.markdown("---")
            st.caption("""
            **Explicación:**
            *   **EMA Cross:** Buscamos que la media rápida (8) cruce la lenta (21).
            *   **ADX:** Si es menor a 20, el mercado está lateral (peligroso operar). Si es > 25, hay tendencia real.
            *   **RVOL:** Volumen relativo. Si es > 1.0 hay interés. Si es > 2.0 hay ballenas.
            """)

else:
    st.info("👈 Selecciona una narrativa o escribe tu lista manual para comenzar.")
