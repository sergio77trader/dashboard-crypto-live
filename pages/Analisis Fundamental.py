import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import time
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader 360: Platinum V3 Fixed")

# --- ESTILOS CSS ---
st.markdown("""
<style>
    div[data-testid="stMetric"], .metric-card {
        background-color: transparent !important;
        border: 1px solid #e0e0e0;
        padding: 10px; border-radius: 8px; text-align: center;
        min-height: 120px; display: flex; flex-direction: column; justify-content: center;
    }
    @media (prefers-color-scheme: dark) {
        div[data-testid="stMetric"], .metric-card { border: 1px solid #404040; }
    }
    .big-score { font-size: 2rem; font-weight: 800; margin: 5px 0; }
    .score-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; opacity: 0.8; }
    .sub-info { font-size: 0.75rem; color: #666; }
    
    .context-box { padding: 10px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #ccc; font-size: 0.9rem;}
    .alert-tag { font-size: 0.7rem; font-weight: bold; padding: 2px 6px; border-radius: 4px; display: inline-block; margin-top:4px;}
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS MAESTRA ---
DB_CATEGORIES = {
    '🇦🇷 Argentina': ['GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX'],
    '🇺🇸 Mag 7 & Tech': ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NFLX', 'CRM', 'ORCL', 'ADBE', 'IBM', 'CSCO', 'PLTR'],
    '🤖 Semis & AI': ['AMD', 'INTC', 'QCOM', 'AVGO', 'TXN', 'MU', 'ADI', 'AMAT', 'ARM', 'SMCI', 'TSM', 'ASML'],
    '🏦 Financiero': ['JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B', 'PYPL', 'SQ', 'COIN'],
    '💊 Salud': ['LLY', 'NVO', 'JNJ', 'PFE', 'MRK', 'ABBV', 'UNH', 'BMY', 'AMGN'],
    '🛒 Consumo': ['KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'TGT', 'HD', 'PG'],
    '🏭 Industria': ['XOM', 'CVX', 'SLB', 'BA', 'CAT', 'DE', 'GE', 'MMM', 'LMT', 'F', 'GM'],
    '🇧🇷 Brasil': ['PBR', 'VALE', 'ITUB', 'BBD', 'ERJ', 'ABEV'],
    '🇨🇳 China': ['BABA', 'JD', 'BIDU', 'PDD', 'NIO'],
    '⛏️ Minería': ['GOLD', 'NEM', 'FCX', 'SCCO'],
    '📈 ETFs': ['SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EWZ', 'XLE', 'XLF', 'XLK', 'XLV', 'ARKK', 'GLD', 'SLV', 'GDX', 'XLY', 'XLP']
}
CEDEAR_DATABASE = sorted(list(set([item for sublist in DB_CATEGORIES.values() for item in sublist])))

# --- ESTADO (V15 - FIX CRASH) ---
# Cambiamos el nombre de la variable para forzar limpieza de memoria
if 'st360_db_v15' not in st.session_state: st.session_state['st360_db_v15'] = []

# --- HELPERS MATEMÁTICOS ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()

# --- ALERTAS VISUALES ---
def get_rsi_alert(rsi):
    if rsi > 70: return "⚠️ SOBRECOMPRA", "#FFEBEE", "#C62828"
    if rsi < 30: return "♻️ SOBREVENTA", "#E8F5E9", "#2E7D32"
    if 40 <= rsi <= 65: return "✅ SANO", "#E3F2FD", "#1565C0"
    return "⚖️ NEUTRAL", "#F5F5F5", "#616161"

def get_atr_alert(atr, price):
    atr_pct = (atr / price) * 100
    if atr_pct > 3.5: return f"⚡ VOLATIL ({atr_pct:.1f}%)", "#FFF3E0", "#EF6C00"
    if atr_pct < 1.5: return f"🐢 LENTO ({atr_pct:.1f}%)", "#F3E5F5", "#6A1B9A"
    return f"✨ NORMAL ({atr_pct:.1f}%)", "#E0F2F1", "#00695C"

# --- MOTOR DE CÁLCULO ---

def get_technical_score(df):
    try:
        score = 0; details = []
        # HA Matrix
        ha_close = (df['Open']+df['High']+df['Low']+df['Close'])/4
        ha_open = (df['Open'].shift(1)+df['Close'].shift(1))/2
        if ha_close.iloc[-1] > ha_open.iloc[-1]: score+=1; details.append("HA Diario Alcista")
        
        df_w = df.resample('W').agg({'Open':'first','High':'max','Low':'min','Close':'last'})
        if not df_w.empty:
            ha_cw = (df_w['Open']+df_w['High']+df_w['Low']+df_w['Close'])/4
            ha_ow = (df_w['Open'].shift(1)+df_w['Close'].shift(1))/2
            if ha_cw.iloc[-1] > ha_ow.iloc[-1]: score+=1; details.append("HA Semanal Alcista")
        
        df_m = df.resample('ME').agg({'Open':'first','High':'max','Low':'min','Close':'last'})
        if not df_m.empty:
            ha_cm = (df_m['Open']+df_m['High']+df_m['Low']+df_m['Close'])/4
            ha_om = (df_m['Open'].shift(1)+df_m['Close'].shift(1))/2
            if ha_cm.iloc[-1] > ha_om.iloc[-1]: score+=1; details.append("HA Mensual Alcista")

        # Medias
        price = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        ma200 = df['Close'].rolling(200).mean().iloc[-1]
        if price > ma20: score+=1; details.append("> MA20")
        if ma20 > ma50: score+=2; details.append("MA20 > MA50")
        if price > ma200: score+=2; details.append("> MA200")

        rsi = calculate_rsi(df['Close']).iloc[-1]
        if 40 <= rsi <= 65: score += 2 
        elif rsi > 70: score -= 2
        elif rsi < 30: score += 1
            
        return max(0, min(10, score)), details, rsi
    except: return 0, ["Error Tec"], 50

def get_options_data(ticker, price, tk_obj):
    def_res = (5, "Sin Opciones", 0, 0, 0, "N/A", 0)
    try:
        try: exps = tk_obj.options
        except: return def_res
        if not exps: return def_res
        
        opt = tk_obj.option_chain(exps[0])
        calls, puts = opt.calls, opt.puts
        if calls.empty or puts.empty: return def_res
        
        t_call, t_put = calls['openInterest'].sum(), puts['openInterest'].sum()
        pcr = t_put / t_call if t_call > 0 else 0
        if pcr < 0.6: sentiment = "🚀 EUFORIA"
        elif pcr > 1.4: sentiment = "🐻 MIEDO"
        else: sentiment = "⚖️ NEUTRAL"

        cw = calls.loc[calls['openInterest'].idxmax()]['strike']
        pw = puts.loc[puts['openInterest'].idxmax()]['strike']
        
        strikes = sorted(list(set(calls['strike'].tolist() + puts['strike'].tolist())))
        rel = [s for s in strikes if price*0.7 < s < price*1.3] or strikes
        cash = []
        for s in rel:
            c_loss = calls.apply(lambda r: max(0, s-r['strike'])*r['openInterest'], axis=1).sum()
            p_loss = puts.apply(lambda r: max(0, r['strike']-s)*r['openInterest'], axis=1).sum()
            cash.append(c_loss+p_loss)
        mp = rel[np.argmin(cash)] if cash else price

        score = 5
        detail = "Rango Medio"
        if price > cw: score=10; detail="🚀 Breakout"
        elif price < pw: score=1; detail="💀 Breakdown"
        else:
            rng = cw - pw
            if rng > 0:
                score = 10 - ((price - pw)/rng * 10)
                if score > 8: detail="🟢 Soporte"
                elif score < 2: detail="🧱 Resistencia"
        
        return score, detail, cw, pw, mp, sentiment, pcr
    except: return def_res

def get_seasonality_score(df):
    try:
        curr_m = datetime.now().month
        m_ret = df['Close'].resample('ME').last().pct_change()
        hist = m_ret[m_ret.index.month == curr_m]
        
        if len(hist)<2: return 5, "N/A", 0
        
        win = (hist>0).mean()
        avg = hist.mean()
        score = win * 6
        if avg > 0.01: score += 4
        elif avg > 0: score += 2
        else: score -= 2
        
        wins = hist[hist>0]; losses = hist[hist<0]
        avg_w = wins.mean() if not wins.empty else 0
        avg_l = abs(losses.mean()) if not losses.empty else 0
        
        warning = ""
        if avg_l > (avg_w * 2) and avg_l > 0.03:
            score -= 3; warning = "⚠️ RIESGO"
            
        return max(0, min(10, score)), f"WR: {win:.0%}", avg
    except: return 5, "N/A", 0

def get_fundamental_score(tk_obj):
    score = 0; details = []; tags = []
    try:
        info = tk_obj.info
        if not info: return 5, ["Sin datos"], []
        
        # 1. Valuation
        peg = info.get('pegRatio', None)
        if peg:
            if peg < 1.0: score+=3; details.append(f"Subvaluada (PEG {peg})"); tags.append("💎 BARATA")
            elif peg < 2.0: score+=2; details.append(f"Precio Justo (PEG {peg})")
            else: details.append(f"Cara (PEG {peg})"); tags.append("💰 CARA")
        else:
            pe = info.get('forwardPE', 25)
            if pe < 15: score+=2; details.append("P/E Bajo"); tags.append("💎 BARATA")
            else: score+=1
            
        # 2. Rentabilidad
        marg = info.get('profitMargins', 0)
        if marg > 0.2: score+=3; details.append("Márgenes Top"); tags.append("👑 CALIDAD")
        elif marg > 0.1: score+=2; details.append("Rentable")
        elif marg > 0: score+=1
        else: details.append("⚠️ Pierde Dinero"); tags.append("🔥 QUEMA CAJA")
        
        # 3. Crecimiento
        rev_g = info.get('revenueGrowth', 0)
        if rev_g > 0.15: score+=2; details.append("Alto Crecimiento"); tags.append("🚀 GROWTH")
        elif rev_g > 0: score+=1
        
        # 4. Analistas
        curr = info.get('currentPrice', 0)
        tgt = info.get('targetMeanPrice', 0)
        if tgt > 0 and curr > 0:
            upside = (tgt - curr)/curr
            if upside > 0.2: score+=2; details.append(f"Analistas: +{upside:.0%}"); tags.append("📈 UPSIDE")
            elif upside > 0.05: score+=1
            
        return min(10, score), details, tags
    except: return 5, ["Error"], []

def analyze_complete(ticker):
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="10y") 
        if df.empty: return None
        price = df['Close'].iloc[-1]
        
        s_tec, d_tec, rsi = get_technical_score(df)
        s_opt, d_opt, cw, pw, mp, sent, pcr = get_options_data(ticker, price, tk)
        s_sea, d_sea, avg_ret = get_seasonality_score(df)
        s_fun, d_fun, fun_tags = get_fundamental_score(tk)
        
        atr = calculate_atr(df).iloc[-1]
        sl = price - (2 * atr)
        tp = price + (3 * atr)
        
        final = (s_tec * 3.0) + (s_opt * 2.5) + (s_sea * 2.0) + (s_fun * 2.5)
        
        verdict = "NEUTRAL"
        if final >= 75: verdict = "🔥 COMPRA FUERTE"
        elif final >= 60: verdict = "✅ COMPRA"
        elif final <= 30: verdict = "💀 VENTA FUERTE"
        elif final <= 45: verdict = "🔻 VENTA"
        
        # Parsing WR
        wr_val = 0
        if "WR:" in d_sea:
            try: wr_val = float(d_sea.split("%")[0].split(":")[-1].strip())
            except: pass
        
        return {
            "Ticker": ticker, "Price": price, "Score": final, "Verdict": verdict,
            "S_Tec": s_tec, "RSI": rsi, "D_Tec": d_tec,
            "S_Opt": s_opt, "Sentiment": sent, "CW": cw, "PW": pw, "Max_Pain": mp, "D_Opt": d_opt,
            "S_Sea": s_sea, "D_Sea": d_sea, "WR": wr_val,
            "S_Fun": s_fun, "D_Fun": d_fun, "Fun_Tags": fun_tags,
            "ATR": atr, "SL": sl, "TP": tp,
            "History": df
        }
    except: return None

# --- UI ---
with st.sidebar:
    st.header("⚙️ Panel de Control")
    st.info(f"Base de Datos: {len(CEDEAR_DATABASE)} Activos")
    
    batch_size = st.slider("Tamaño del Lote", 1, 10, 3)
    batches = [CEDEAR_DATABASE[i:i + batch_size] for i in range(0, len(CEDEAR_DATABASE), batch_size)]
    batch_labels = [f"Lote {i+1}: {b[0]} ... {b[-1]}" for i, b in enumerate(batches)]
    sel_batch = st.selectbox("Seleccionar Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    c1, c2 = st.columns(2)
    if c1.button("▶️ ESCANEAR", type="primary"):
        targets = batches[sel_batch]
        prog = st.progress(0)
        # USAMOS V15 PARA EVITAR ERROR
        mem = [x['Ticker'] for x in st.session_state['st360_db_v15']]
        run = [t for t in targets if t not in mem]
        for i, t in enumerate(run):
            r = analyze_complete(t)
            if r: st.session_state['st360_db_v15'].append(r)
            prog.progress((i+1)/len(run))
            time.sleep(0.5) 
        prog.empty(); st.rerun()
        
    if c2.button("🗑️ Limpiar"): st.session_state['st360_db_v15'] = []; st.rerun()
    st.divider()
    mt = st.text_input("Ticker Manual:").upper().strip()
    if st.button("Analizar"):
        if mt:
            with st.spinner("Descargando Fundamentales..."):
                r = analyze_complete(mt)
                if r:
                    st.session_state['st360_db_v15'] = [x for x in st.session_state['st360_db_v15'] if x['Ticker']!=mt]
                    st.session_state['st360_db_v15'].append(r)
                    st.rerun()

st.title("SystemaTrader 360: Fundamental Edition")

if st.session_state['st360_db_v15']:
    dfv = pd.DataFrame(st.session_state['st360_db_v15'])
    if 'Score' in dfv.columns: dfv = dfv.sort_values("Score", ascending=False)
    
    # Pre-cálculo filtros
    dfv['RSI_Cat'] = dfv['RSI'].apply(lambda x: "⚠️" if x>70 else ("♻️" if x<30 else "✅"))
    
    def get_tec_trend(tech_list):
        if "MA20 > MA50" in tech_list: return "📈 Alcista"
        if "Debajo MA200" in tech_list: return "📉 Bajista"
        return "⚖️ Lateral"
    
    # Check robusto por si la lista está vacía
    dfv['Trend_Cat'] = dfv['D_Tec'].apply(lambda x: get_tec_trend(x) if isinstance(x, list) else "N/A")
    
    # FILTROS AVANZADOS
    with st.expander("🔍 FILTROS AVANZADOS (Click para abrir)", expanded=True):
        t1, t2, t3, t4 = st.tabs(["📊 Técnico", "💎 Fundamental", "🧱 Estructura", "📅 Estacional"])
        
        with t1:
            c1, c2 = st.columns(2)
            with c1: f_rsi = st.multiselect("Estado RSI:", ["✅", "⚠️", "♻️"])
            with c2: f_trend = st.multiselect("Tendencia (Medias):", ["📈 Alcista", "📉 Bajista", "⚖️ Lateral"])
            
        with t2:
            st.caption("Filtra por etiquetas de calidad:")
            # Fix robusto para evitar KeyError si la columna no existe o está vacía
            if 'Fun_Tags' in dfv.columns:
                all_tags = sorted(list(set([t for sublist in dfv['Fun_Tags'] if isinstance(sublist, list) for t in sublist])))
                f_fund = st.multiselect("Calidad / Valor:", all_tags)
            else:
                f_fund = []
                st.warning("No hay datos fundamentales cargados aún.")
            
        with t3:
            c1, c2 = st.columns(2)
            with c1: f_sent = st.multiselect("Sentimiento Opciones:", ["🚀 EUFORIA", "🐻 MIEDO", "⚖️ NEUTRAL"])
            with c2: f_wall = st.checkbox("Solo en Zona de Soporte (Cerca de Put Wall)")
            
        with t4:
            f_win = st.slider("WinRate Mínimo Histórico (%)", 0, 100, 0)

    # --- APLICACIÓN DE FILTROS ---
    df_show = dfv.copy()
    min_sc = st.slider("Filtrar por Score Mínimo Global:", 0, 100, 0)
    df_show = df_show[df_show['Score'] >= min_sc]
    
    if f_rsi: df_show = df_show[df_show['RSI_Cat'].isin(f_rsi)]
    if f_trend: df_show = df_show[df_show['Trend_Cat'].isin(f_trend)]
    
    if f_fund: 
        df_show = df_show[df_show['Fun_Tags'].apply(lambda tags: any(x in tags for x in f_fund) if isinstance(tags, list) else False)]
        
    if f_sent:
        mask = df_show['Sentiment'].apply(lambda s: any(k in s for k in f_sent))
        df_show = df_show[mask]
        
    if f_wall:
        df_show = df_show[df_show['D_Opt'].str.contains("Soporte", na=False)]
        
    if f_win > 0:
        df_show = df_show[df_show['WR'] >= f_win]

    # --- VISUALIZACIÓN ---
    if df_show.empty:
        st.warning("⚠️ No hay activos que cumplan con todos los filtros seleccionados.")
    else:
        st.success(f"Encontrados: {len(df_show)} activos.")
        
        st.dataframe(
            df_show[['Ticker', 'Price', 'Score', 'Verdict', 'S_Tec', 'S_Opt', 'S_Sea', 'S_Fun']],
            column_config={
                "Ticker": "Activo", "Price": st.column_config.NumberColumn(format="$%.2f"),
                "Score": st.column_config.ProgressColumn("Puntaje Final", min_value=0, max_value=100, format="%.0f"),
                "S_Tec": st.column_config.NumberColumn("Técnico", format="%.1f"),
                "S_Opt": st.column_config.NumberColumn("Estructura", format="%.1f"),
                "S_Sea": st.column_config.NumberColumn("Estacional", format="%.1f"),
                "S_Fun": st.column_config.NumberColumn("Fundam.", format="%.1f"),
            }, use_container_width=True, hide_index=True
        )
        
        st.divider()
        valid_tickers = df_show['Ticker'].tolist()
        if valid_tickers:
            sel = st.selectbox("Inspección Profunda (Filtrados):", valid_tickers)
            it = next((x for x in st.session_state['st360_db_v15'] if x['Ticker'] == sel), None)
            
            if it:
                rsi_msg, rsi_bg, rsi_txt = get_rsi_alert(it['RSI'])
                atr_msg, atr_bg, atr_txt = get_atr_alert(it['ATR'], it['Price'])
                
                # --- TARJETAS ---
                k1, k2, k3, k4 = st.columns(4)
                sc = it['Score']
                clr = "#00C853" if sc >= 70 else "#D32F2F" if sc <= 40 else "#FBC02D"
                
                with k1:
                    st.markdown(f"""<div class="metric-card"><div class="score-label">TÉCNICO (30%)</div><div class="big-score" style="color:#555;">{it['S_Tec']:.1f}</div><div class="alert-tag" style="background-color:{rsi_bg}; color:{rsi_txt};">{rsi_msg}</div></div>""", unsafe_allow_html=True)
                with k2:
                    st.markdown(f"""<div class="metric-card"><div class="score-label">FUNDAMENTAL (25%)</div><div class="big-score" style="color:#1565C0;">{it['S_Fun']:.1f}</div><div class="sub-info" style="font-size:0.7rem;">{it['Fun_Tags'][0] if it['Fun_Tags'] else '-'}</div></div>""", unsafe_allow_html=True)
                with k3:
                    st.markdown(f"""<div class="metric-card"><div class="score-label">ESTRUCTURA (25%)</div><div class="big-score" style="color:#555;">{it['S_Opt']:.1f}</div><div class="sub-info">{it['Sentiment']}</div></div>""", unsafe_allow_html=True)
                with k4:
                    st.markdown(f"""<div class="metric-card" style="border:2px solid {clr};"><div class="score-label" style="color:{clr};">SCORE FINAL</div><div class="big-score" style="color:{clr};">{sc:.0f}</div><div style="font-weight:bold; color:{clr};">{it['Verdict']}</div></div>""", unsafe_allow_html=True)

                # --- AUDITORÍA ---
                with st.expander("📊 Auditoría de los 4 Pilares"):
                    c_tec, c_fun = st.columns(2)
                    with c_tec:
                        st.markdown("**1. Técnico:**")
                        for d in it['D_Tec']: st.markdown(f"- {d}")
                        st.markdown(f"**Riesgo:** {atr_msg}")
                        st.markdown(f"**Niveles:** SL ${it['SL']:.2f} | TP ${it['TP']:.2f}")
                    with c_fun:
                        st.markdown("**2. Fundamental (Calidad):**")
                        for d in it['D_Fun']: st.markdown(f"- 💎 {d}")
                    
                    st.markdown("---")
                    c_str, c_sea = st.columns(2)
                    with c_str:
                        st.markdown(f"**3. Estructura:** {it['D_Opt']}")
                        st.markdown(f"- Max Pain: ${it['Max_Pain']:.2f}")
                    with c_sea:
                        st.markdown(f"**4. Estacionalidad:** {it['D_Sea']}")

                h = it['History']
                fig = go.Figure(data=[go.Candlestick(x=h.index, open=h['Open'], high=h['High'], low=h['Low'], close=h['Close'], name='Precio')])
                if it['SL']>0:
                    fig.add_hline(y=it['SL'], line_dash="solid", line_color="red", annotation_text="STOP")
                    fig.add_hline(y=it['TP'], line_dash="solid", line_color="green", annotation_text="PROFIT")
                if it['CW']>0:
                    fig.add_hline(y=it['CW'], line_dash="dot", line_color="orange", annotation_text="Call Wall")
                    fig.add_hline(y=it['PW'], line_dash="dot", line_color="cyan", annotation_text="Put Wall")
                    
                fig.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_white", margin=dict(t=30, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)

else: st.info("👈 Escanea un lote (Paciencia: Fundamentales tardan más).")
