import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import time
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader 360: Diamond")

# --- ESTILOS CSS ---
st.markdown("""
<style>
    div[data-testid="stMetric"], .metric-card {
        background-color: transparent !important;
        border: 1px solid #e0e0e0;
        padding: 15px; border-radius: 8px; text-align: center;
        min-height: 160px; display: flex; flex-direction: column; justify-content: center;
    }
    @media (prefers-color-scheme: dark) {
        div[data-testid="stMetric"], .metric-card { border: 1px solid #404040; }
    }
    .big-score { font-size: 2.2rem; font-weight: 800; margin: 5px 0; }
    .score-label { font-size: 0.8rem; font-weight: 600; text-transform: uppercase; opacity: 0.8; }
    .sub-info { font-size: 0.8rem; color: #666; }
    
    .context-box { padding: 10px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #ccc; font-size: 0.9rem;}
    
    .alert-tag {
        font-size: 0.75rem; font-weight: bold; padding: 2px 6px; border-radius: 4px; margin-top: 4px; display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS ---
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
    '📈 ETFs': ['SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EWZ', 'XLE', 'XLF', 'XLK', 'XLV', 'ARKK', 'GLD', 'SLV', 'GDX']
}
CEDEAR_DATABASE = sorted(list(set([item for sublist in DB_CATEGORIES.values() for item in sublist])))

# --- ESTADO (V10) ---
if 'st360_db_v10' not in st.session_state: st.session_state['st360_db_v10'] = []

# --- HELPERS ---
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

# --- ALERTAS INTELIGENTES ---
def get_rsi_alert(rsi):
    if rsi > 70: return "⚠️ SOBRECOMPRA (Riesgo Corrección)", "#FFEBEE", "#C62828" # Rojo claro fondo, Rojo oscuro texto
    if rsi < 30: return "♻️ SOBREVENTA (Posible Rebote)", "#E8F5E9", "#2E7D32" # Verde claro
    if 40 <= rsi <= 65: return "✅ TENDENCIA SANA", "#E3F2FD", "#1565C0" # Azul claro
    return "⚖️ NEUTRAL", "#F5F5F5", "#616161"

def get_atr_alert(atr, price):
    atr_pct = (atr / price) * 100
    if atr_pct > 3.5: return f"⚡ VOLATILIDAD ALTA ({atr_pct:.1f}%)", "#FFF3E0", "#EF6C00" # Naranja
    if atr_pct < 1.5: return f"🐢 VOLATILIDAD BAJA ({atr_pct:.1f}%)", "#F3E5F5", "#6A1B9A" # Violeta
    return f"✨ VOLATILIDAD NORMAL ({atr_pct:.1f}%)", "#E0F2F1", "#00695C" # Teal

# --- MOTOR DE CÁLCULO ---
def detect_region_benchmark(ticker):
    if ticker in DB_CATEGORIES['🇦🇷 Argentina']: return 'ARGT', "ETF Argentina"
    if ticker in DB_CATEGORIES['🇧🇷 Brasil']: return 'EWZ', "ETF Brasil"
    if ticker in DB_CATEGORIES['🇨🇳 China']: return 'FXI', "ETF China"
    if ticker in DB_CATEGORIES['🤖 Semis & AI']: return 'SOXX', "ETF Semis"
    if ticker in DB_CATEGORIES['⛏️ Minería']: return 'GDX', "ETF Oro"
    return 'SPY', "S&P 500"

def get_market_context_dynamic(ticker):
    try:
        bench_tk, bench_name = detect_region_benchmark(ticker)
        data = yf.Tickers(f"{bench_tk} ^VIX")
        bench = data.tickers[bench_tk].history(period="6mo")
        vix = data.tickers['^VIX'].history(period="5d")
        
        if bench.empty: return "NEUTRAL", f"Sin datos {bench_name}", 0, "N/A", bench_name
        
        price = bench['Close'].iloc[-1]
        ma50 = bench['Close'].rolling(50).mean().iloc[-1]
        vix_p = vix['Close'].iloc[-1] if not vix.empty else 0
        
        stt = "BULLISH" if price > ma50 else "BEARISH"
        msg = f"{'✅ Alcista' if price > ma50 else '🛑 Bajista'} en {bench_name}"
        vix_st = "🟢 Calma" if vix_p < 20 else "🔴 MIEDO" if vix_p > 25 else "🟡 Alerta"
        
        return stt, msg, vix_p, vix_st, bench_name
    except: return "NEUTRAL", "Error Macro", 0, "N/A", "SPY"

def analyze_complete(ticker):
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="2y")
        if df.empty: return None
        price = df['Close'].iloc[-1]
        
        # 1. Técnico
        rsi = calculate_rsi(df['Close']).iloc[-1]
        score_tec = 0
        details_tec = []
        
        # HA Logic
        ha_close = (df['Open']+df['High']+df['Low']+df['Close'])/4
        ha_open = (df['Open'].shift(1)+df['Close'].shift(1))/2
        daily_green = ha_close.iloc[-1] > ha_open.iloc[-1]
        if daily_green: score_tec += 1
        
        # Medias
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        if price > ma20: score_tec += 2; details_tec.append("> MA20")
        if ma20 > ma50: score_tec += 3; details_tec.append("Tendencia Sana")
        
        # RSI Score
        if 40 <= rsi <= 65: score_tec += 2
        elif rsi > 70: score_tec -= 2
        elif rsi < 30: score_tec += 1
        
        score_tec = max(0, min(10, score_tec))
        
        # 2. Opciones
        try:
            exps = tk.options
            opt = tk.option_chain(exps[0])
            calls, puts = opt.calls, opt.puts
            cw = calls.loc[calls['openInterest'].idxmax()]['strike']
            pw = puts.loc[puts['openInterest'].idxmax()]['strike']
            
            pcr = puts['openInterest'].sum() / calls['openInterest'].sum()
            sent = "🚀 Euforia" if pcr < 0.7 else "🐻 Miedo" if pcr > 1.3 else "⚖️ Neutral"
            
            strikes = sorted(list(set(calls['strike'].tolist()+puts['strike'].tolist())))
            rel = [s for s in strikes if price*0.7 < s < price*1.3] or strikes
            cash = []
            for s in rel:
                c_l = calls.apply(lambda r: max(0, s-r['strike'])*r['openInterest'], axis=1).sum()
                p_l = puts.apply(lambda r: max(0, r['strike']-s)*r['openInterest'], axis=1).sum()
                cash.append(c_l+p_l)
            mp = rel[np.argmin(cash)] if cash else price
            
            score_opt = 5
            if price > cw: score_opt = 10
            elif price < pw: score_opt = 1
            else:
                rng = cw - pw
                if rng > 0: score_opt = 10 - ((price-pw)/rng * 10)
        except:
            score_opt, cw, pw, mp, sent = 5, 0, 0, 0, "N/A"

        # 3. Estacionalidad & Niveles
        curr_m = datetime.now().month
        m_ret = df['Close'].resample('ME').last().pct_change()
        hist = m_ret[m_ret.index.month == curr_m]
        
        win = (hist>0).mean() if len(hist)>1 else 0
        score_sea = win * 6
        avg_ret = hist.mean() if len(hist)>1 else 0
        if avg_ret > 0.01: score_sea += 4
        
        # ATR Logic
        atr = calculate_atr(df).iloc[-1]
        sl = price - (2 * atr)
        tp = price + (3 * atr)
        
        # Contexto
        macro_st, macro_msg, vix, vix_st, bench = get_market_context_dynamic(ticker)
        
        final = (score_tec * 4) + (score_opt * 3) + (score_sea * 3)
        if macro_st == "BEARISH": final -= 10
        if vix > 25: final -= 5
        
        verdict = "NEUTRAL"
        if final >= 75: verdict = "🔥 COMPRA FUERTE"
        elif final >= 60: verdict = "✅ COMPRA"
        elif final <= 25: verdict = "💀 VENTA FUERTE"
        elif final <= 40: verdict = "🔻 VENTA"
        
        return {
            "Ticker": ticker, "Price": price, "Score": final, "Verdict": verdict,
            "S_Tec": score_tec, "RSI": rsi,
            "S_Opt": score_opt, "Sentiment": sent, "CW": cw, "PW": pw, "Max_Pain": mp,
            "S_Sea": score_sea, "Avg_Ret": avg_ret,
            "ATR": atr, "SL": sl, "TP": tp,
            "Macro_Msg": macro_msg, "Bench": bench, "VIX": vix, "VIX_St": vix_st,
            "History": df
        }
    except: return None

# --- UI ---
with st.sidebar:
    st.header("⚙️ Panel de Control")
    st.info(f"Base de Datos: {len(CEDEAR_DATABASE)} Activos")
    
    batch_size = st.slider("Tamaño del Lote", 1, 15, 5)
    batches = [CEDEAR_DATABASE[i:i + batch_size] for i in range(0, len(CEDEAR_DATABASE), batch_size)]
    batch_labels = [f"Lote {i+1}: {b[0]} ... {b[-1]}" for i, b in enumerate(batches)]
    sel_batch = st.selectbox("Seleccionar Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    c1, c2 = st.columns(2)
    if c1.button("▶️ ESCANEAR", type="primary"):
        targets = batches[sel_batch]
        prog = st.progress(0)
        mem = [x['Ticker'] for x in st.session_state['st360_db_v10']]
        run = [t for t in targets if t not in mem]
        for i, t in enumerate(run):
            r = analyze_complete(t)
            if r: st.session_state['st360_db_v10'].append(r)
            prog.progress((i+1)/len(run))
            time.sleep(0.3)
        prog.empty(); st.rerun()
        
    if c2.button("🗑️ Limpiar"): st.session_state['st360_db_v10'] = []; st.rerun()
    st.divider()
    mt = st.text_input("Ticker Manual:").upper().strip()
    if st.button("Analizar"):
        if mt:
            with st.spinner("Procesando..."):
                r = analyze_complete(mt)
                if r:
                    st.session_state['st360_db_v10'] = [x for x in st.session_state['st360_db_v10'] if x['Ticker']!=mt]
                    st.session_state['st360_db_v10'].append(r)
                    st.rerun()

st.title("SystemaTrader 360: Diamond Edition")

if st.session_state['st360_db_v10']:
    dfv = pd.DataFrame(st.session_state['st360_db_v10'])
    if 'Score' in dfv.columns: dfv = dfv.sort_values("Score", ascending=False)
    
    st.dataframe(
        dfv[['Ticker', 'Price', 'Score', 'Verdict', 'S_Tec', 'S_Opt', 'S_Sea']],
        column_config={
            "Ticker": "Activo", "Price": st.column_config.NumberColumn(format="$%.2f"),
            "Score": st.column_config.ProgressColumn("Puntaje", min_value=0, max_value=100, format="%.0f"),
            "S_Tec": st.column_config.NumberColumn("Técnico", format="%.1f"),
            "S_Opt": st.column_config.NumberColumn("Opciones", format="%.1f"),
            "S_Sea": st.column_config.NumberColumn("Estac.", format="%.1f")
        }, use_container_width=True, hide_index=True
    )
    
    st.divider()
    sel = st.selectbox("Inspección Profunda:", dfv['Ticker'].tolist())
    it = next((x for x in st.session_state['st360_db_v10'] if x['Ticker'] == sel), None)
    
    if it:
        # Generar Textos de Alerta
        rsi_msg, rsi_bg, rsi_txt = get_rsi_alert(it['RSI'])
        atr_msg, atr_bg, atr_txt = get_atr_alert(it['ATR'], it['Price'])
        
        # BANNER CONTEXTO
        clr_mc = "#d4edda" if "✅" in it['Macro_Msg'] else "#f8d7da"
        txt_mc = "#155724" if "✅" in it['Macro_Msg'] else "#721c24"
        
        st.markdown(f"""
        <div class="context-box" style="background-color: {clr_mc}; color: {txt_mc}; border-color: {txt_mc};">
            🌍 <b>CONTEXTO REGIONAL ({it['Bench']}):</b> {it['Macro_Msg']} | 📉 <b>VIX:</b> {it['VIX']:.2f} ({it['VIX_St']})
        </div>
        """, unsafe_allow_html=True)
        
        k1, k2, k3, k4 = st.columns(4)
        sc = it['Score']
        clr = "#00C853" if sc >= 70 else "#D32F2F" if sc <= 40 else "#FBC02D"
        
        with k1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="score-label">TÉCNICO</div>
                <div class="big-score" style="color:#555;">{it['S_Tec']:.1f}</div>
                <div class="alert-tag" style="background-color:{rsi_bg}; color:{rsi_txt};">{rsi_msg}</div>
            </div>""", unsafe_allow_html=True)
        with k2:
            st.markdown(f"""
            <div class="metric-card" style="border: 2px solid {clr};">
                <div class="score-label" style="color:{clr};">PUNTAJE</div>
                <div class="big-score" style="color:{clr};">{sc:.0f}</div>
                <div style="font-weight:bold; color:{clr};">{it['Verdict']}</div>
            </div>""", unsafe_allow_html=True)
        with k3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="score-label">ESTRUCTURA</div>
                <div class="big-score" style="color:#555;">{it['S_Opt']:.1f}</div>
                <div class="sub-info">{it['Sentiment']}</div>
            </div>""", unsafe_allow_html=True)
        with k4:
            st.markdown(f"""
            <div class="metric-card">
                <div class="score-label">RIESGO & VOLATILIDAD</div>
                <div class="alert-tag" style="background-color:{atr_bg}; color:{atr_txt}; margin-bottom:5px;">{atr_msg}</div>
                <div style="text-align:left; font-size:0.85rem;">
                🎯 <b>TP:</b> ${it['TP']:.2f}<br>
                🛡️ <b>SL:</b> ${it['SL']:.2f}<br>
                </div>
            </div>""", unsafe_allow_html=True)

        with st.expander("🔎 Auditoría y Niveles"):
            st.markdown(f"""
            **1. Análisis Técnico:** RSI: {it['RSI']:.1f}.
            **2. Estructura:** Put Wall ${it['PW']:.2f} | Call Wall ${it['CW']:.2f} | Max Pain ${it['Max_Pain']:.2f}.
            **3. Estacionalidad:** {it['Avg_Ret']:.1%} Retorno Promedio Histórico.
            **4. Gestión:** ATR ${it['ATR']:.2f}. Stop Loss (2 ATR) y Take Profit (3 ATR).
            """)
            
        h = it['History']
        fig = go.Figure(data=[go.Candlestick(x=h.index, open=h['Open'], high=h['High'], low=h['Low'], close=h['Close'], name='Precio')])
        if it['SL'] > 0:
            fig.add_hline(y=it['SL'], line_dash="solid", line_color="red", annotation_text="STOP")
            fig.add_hline(y=it['TP'], line_dash="solid", line_color="green", annotation_text="PROFIT")
        if it['CW'] > 0:
            fig.add_hline(y=it['CW'], line_dash="dot", line_color="orange", annotation_text="Call Wall")
            fig.add_hline(y=it['PW'], line_dash="dot", line_color="cyan", annotation_text="Put Wall")
            
        fig.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_white", margin=dict(t=30, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

else: st.info("👈 Comienza escaneando un lote.")
