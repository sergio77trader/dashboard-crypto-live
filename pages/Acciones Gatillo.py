import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import time
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader 360: Master Database")

# --- ESTILOS CSS ---
st.markdown("""
<style>
    div[data-testid="stMetric"], .metric-card {
        background-color: transparent !important;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        min-height: 160px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    @media (prefers-color-scheme: dark) {
        div[data-testid="stMetric"], .metric-card {
            border: 1px solid #404040;
        }
    }
    .big-score { font-size: 2.2rem; font-weight: 800; margin: 5px 0; }
    .score-label { font-size: 0.85rem; font-weight: 600; text-transform: uppercase; opacity: 0.8; letter-spacing: 1px;}
    .sub-info { font-size: 0.85rem; color: #666; margin-top: 5px; }
    
    .sentiment-tag {
        font-weight: bold; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; display: inline-block; margin-top: 5px;
    }
</style>
""", unsafe_allow_html=True)

# --- BASE DE DATOS MAESTRA ---
DB_CATEGORIES = {
    '🇦🇷 Argentina (ADRs & Unicornios)': [
        'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 
        'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX'
    ],
    '🇺🇸 Mag 7 & Big Tech': [
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NFLX', 
        'CRM', 'ORCL', 'ADBE', 'IBM', 'CSCO', 'PLTR', 'SNOW', 'SHOP', 'SPOT'
    ],
    '🤖 Semiconductores & AI': [
        'AMD', 'INTC', 'QCOM', 'AVGO', 'TXN', 'MU', 'ADI', 'AMAT', 'LRCX', 
        'ARM', 'SMCI', 'TSM', 'ASML'
    ],
    '🏦 Financiero (USA)': [
        'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B', 
        'BLK', 'PYPL', 'SQ', 'COIN', 'HOOD'
    ],
    '💊 Salud & Pharma': [
        'LLY', 'NVO', 'JNJ', 'PFE', 'MRK', 'ABBV', 'UNH', 'BMY', 'AMGN', 
        'GILD', 'AZN', 'NVS', 'SNY'
    ],
    '🛒 Consumo & Retail': [
        'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'TGT', 'HD', 
        'LOW', 'PG', 'CL', 'MO', 'PM'
    ],
    '🏭 Industria & Energía': [
        'XOM', 'CVX', 'SLB', 'HAL', 'OXY', 'SHEL', 'BP', 'TTE',
        'BA', 'CAT', 'DE', 'GE', 'MMM', 'HON', 'LMT', 'RTX',
        'F', 'GM', 'TM', 'HMC', 'STLA'
    ],
    '🇧🇷 Brasil': [
        'PBR', 'VALE', 'ITUB', 'BBD', 'ERJ', 'ABEV', 'GGB', 'SID'
    ],
    '🇨🇳 China': [
        'BABA', 'JD', 'BIDU', 'PDD', 'NIO', 'TCOM', 'BEKE'
    ],
    '⛏️ Minería': [
        'GOLD', 'NEM', 'PAAS', 'FCX', 'SCCO', 'RIO', 'BHP'
    ],
    '🪙 Crypto': [
        'MSTR', 'MARA', 'RIOT', 'HUT', 'BITF', 'CLSK'
    ],
    '📈 ETFs': [
        'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EWZ', 'FXI',
        'XLE', 'XLF', 'XLK', 'XLV', 'ARKK', 'SMH',
        'GLD', 'SLV', 'GDX', 'XLY', 'XLP'
    ]
}
CEDEAR_DATABASE = sorted(list(set([item for sublist in DB_CATEGORIES.values() for item in sublist])))

# --- INICIALIZAR ESTADO (V7 - Tolerante a Fallos) ---
if 'st360_db_v7' not in st.session_state:
    st.session_state['st360_db_v7'] = []

# --- MOTOR DE CÁLCULO ---

def calculate_ha_candle(df):
    if df.empty: return False
    ha_close = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    ha_open = (df['Open'].shift(1) + df['Close'].shift(1)) / 2
    last = df.index[-1]
    return ha_close[last] > ha_open[last]

def get_technical_score(df):
    try:
        score = 0
        details = []
        
        # A) Matriz Heikin Ashi
        if calculate_ha_candle(df): score+=1; details.append("HA Diario Alcista (+1)")
        else: details.append("HA Diario Bajista (0)")
            
        df_w = df.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'})
        if calculate_ha_candle(df_w): score+=1; details.append("HA Semanal Alcista (+1)")
        else: details.append("HA Semanal Bajista (0)")
        
        df_m = df.resample('ME').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'})
        if calculate_ha_candle(df_m): score+=1; details.append("HA Mensual Alcista (+1)")
        else: details.append("HA Mensual Bajista (0)")

        # B) Medias Móviles
        price = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        ma200 = df['Close'].rolling(200).mean().iloc[-1]
        
        if price > ma20: score += 2; details.append("Precio > MA20 (+2)")
        else: details.append("Precio < MA20 (0)")

        if ma20 > ma50: score += 3; details.append("Tendencia Sana (MA20 > MA50) (+3)")
        else: details.append("Tendencia Débil (0)")

        if price > ma200: score += 2; details.append("Tendencia Largo Plazo (>MA200) (+2)")
        else: details.append("Debajo MA200 (0)")
        
        return min(score, 10), details
    except: return 0, ["Error Técnico"]

def get_options_data(ticker, price):
    # Valores por defecto de fallo
    def_res = (5, "Sin Opciones", 0, 0, 0, "N/A")
    try:
        tk = yf.Ticker(ticker)
        # Intentamos obtener opciones con timeout implícito de YF
        try:
            exps = tk.options
        except:
            return def_res
            
        if not exps: return def_res
        
        opt = tk.option_chain(exps[0])
        calls = opt.calls
        puts = opt.puts
        
        if calls.empty or puts.empty: return def_res
        
        # Sentimiento
        total_call_oi = calls['openInterest'].sum()
        total_put_oi = puts['openInterest'].sum()
        pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        
        if pcr < 0.7: sentiment = "🚀 Alcista (Euforia)"
        elif pcr > 1.3: sentiment = "🐻 Bajista (Miedo)"
        else: sentiment = "⚖️ Neutral"

        # Estructura
        cw = calls.loc[calls['openInterest'].idxmax()]['strike']
        pw = puts.loc[puts['openInterest'].idxmax()]['strike']
        
        strikes = sorted(list(set(calls['strike'].tolist() + puts['strike'].tolist())))
        relevant = [s for s in strikes if price * 0.7 < s < price * 1.3]
        if not relevant: relevant = strikes
        
        cash_values = []
        for s in relevant:
            c_loss = calls.apply(lambda r: max(0, s - r['strike']) * r['openInterest'], axis=1).sum()
            p_loss = puts.apply(lambda r: max(0, r['strike'] - s) * r['openInterest'], axis=1).sum()
            cash_values.append(c_loss + p_loss)
        mp = relevant[np.argmin(cash_values)] if cash_values else price

        # Score
        score = 5
        detail = "Rango Medio"
        
        if price > cw: score=10; detail="🚀 Breakout Gamma"
        elif price < pw: score=1; detail="💀 Breakdown Gamma"
        else:
            rng = cw - pw
            if rng > 0:
                pos = (price - pw) / rng
                score = 10 - (pos * 10)
                if score > 8: detail = "🟢 Soporte (Put Wall)"
                elif score < 2: detail = "🧱 Resistencia (Call Wall)"
                else: detail = f"Rango ${pw}-${cw}"
                
        return score, detail, cw, pw, mp, sentiment
    except: return def_res

def get_seasonality_score(df):
    try:
        curr_month = datetime.now().month
        m_ret = df['Close'].resample('ME').last().pct_change()
        hist = m_ret[m_ret.index.month == curr_month]
        
        if len(hist) < 2: return 5, "Sin Historia", 0
        
        win_rate = (hist > 0).mean()
        avg_ret = hist.mean()
        
        wins = hist[hist > 0]
        losses = hist[hist < 0]
        avg_win = wins.mean() if not wins.empty else 0
        avg_loss = abs(losses.mean()) if not losses.empty else 0
        
        score = win_rate * 6 
        if avg_ret > 0.01: score += 4 
        elif avg_ret > 0: score += 2 
        else: score -= 2 
        
        warning = ""
        if avg_loss > (avg_win * 2) and avg_loss > 0.03:
            score -= 3
            warning = "⚠️ RIESGO (Loss > 2x Win)"
        
        final = max(0, min(10, score))
        detail = f"WR: {win_rate:.0%} | Avg: {avg_ret:.1%}"
        if warning: detail += f" {warning}"
        
        return final, detail, avg_ret
    except: return 5, "Error Estacional", 0

# --- FUNCIÓN MAESTRA TOLERANTE A FALLOS ---
def analyze_complete(ticker):
    # Estructura por defecto en caso de fallo total
    default_res = {
        "Ticker": ticker, "Price": 0, "Score": 0, "Verdict": "⚠️ SIN DATOS",
        "S_Tec": 0, "D_Tec_List": [], "D_Tec_Str": "Error de Conexión",
        "S_Opt": 0, "D_Opt": "N/A", "Sentiment": "N/A",
        "S_Sea": 0, "D_Sea": "N/A", "Avg_Ret": 0,
        "CW": 0, "PW": 0, "Max_Pain": 0, "History": None
    }
    
    try:
        tk = yf.Ticker(ticker)
        # Intentamos descargar. Si falla, devolvemos default pero NO None (para que aparezca en tabla)
        try:
            df = tk.history(period="5y")
        except:
            return default_res
            
        if df.empty:
            return default_res
        
        price = df['Close'].iloc[-1]
        
        # 1. Técnico
        s_tec, d_tec_list = get_technical_score(df)
        d_tec_str = ", ".join([d for d in d_tec_list if "(+" in d])
        if not d_tec_str: d_tec_str = "Técnicamente Débil"
        
        # 2. Opciones
        s_opt, d_opt, cw, pw, mp, sentiment = get_options_data(ticker, price)
        
        # 3. Estacionalidad
        s_sea, d_sea, avg_ret = get_seasonality_score(df)
        
        # Ponderación
        final = (s_tec * 4) + (s_opt * 3) + (s_sea * 3)
        
        verdict = "NEUTRAL"
        if final >= 75: verdict = "🔥 COMPRA FUERTE"
        elif final >= 60: verdict = "✅ COMPRA"
        elif final <= 25: verdict = "💀 VENTA FUERTE"
        elif final <= 40: verdict = "🔻 VENTA"
        
        return {
            "Ticker": ticker, "Price": price, "Score": final, "Verdict": verdict,
            "S_Tec": s_tec, "D_Tec_List": d_tec_list, "D_Tec_Str": d_tec_str,
            "S_Opt": s_opt, "D_Opt": d_opt, "Sentiment": sentiment,
            "S_Sea": s_sea, "D_Sea": d_sea, "Avg_Ret": avg_ret,
            "CW": cw, "PW": pw, "Max_Pain": mp,
            "History": df
        }
    except Exception as e:
        # Si explota algo inesperado, devolvemos el error visible
        default_res["D_Tec_Str"] = str(e)
        return default_res

# --- UI ---
with st.sidebar:
    st.header("⚙️ Panel de Control")
    st.info(f"Base de Datos: {len(CEDEAR_DATABASE)} Activos")
    
    batch_size = st.slider("Tamaño del Lote", 1, 15, 5)
    batches = [CEDEAR_DATABASE[i:i + batch_size] for i in range(0, len(CEDEAR_DATABASE), batch_size)]
    batch_labels = [f"Lote {i+1}: {b[0]} ... {b[-1]}" for i, b in enumerate(batches)]
    
    sel_batch = st.selectbox("Seleccionar Lote:", range(len(batches)), format_func=lambda x: batch_labels[x])
    
    col_b1, col_b2 = st.columns(2)
    if col_b1.button("▶️ ESCANEAR", type="primary"):
        targets = batches[sel_batch]
        prog = st.progress(0)
        status = st.empty()
        
        mem_tickers = [x['Ticker'] for x in st.session_state['st360_db_v7']]
        to_run = [t for t in targets if t not in mem_tickers]
        
        for i, t in enumerate(to_run):
            status.markdown(f"🔍 Analizando **{t}**...")
            # Ahora analyze_complete SIEMPRE devuelve un dict, nunca None
            res = analyze_complete(t)
            st.session_state['st360_db_v7'].append(res)
            
            prog.progress((i+1)/len(to_run))
            time.sleep(0.5)
            
        status.success("✅ Listo")
        time.sleep(1)
        status.empty()
        prog.empty()
        st.rerun()
        
    if col_b2.button("🗑️ Limpiar"):
        st.session_state['st360_db_v7'] = []
        st.rerun()

    st.divider()
    manual_t = st.text_input("Ticker (Ej: XLY):").upper().strip()
    if st.button("Analizar Individual"):
        if manual_t:
            with st.spinner("Procesando..."):
                res = analyze_complete(manual_t)
                # Eliminamos versión anterior si existe y agregamos nueva
                st.session_state['st360_db_v7'] = [x for x in st.session_state['st360_db_v7'] if x['Ticker'] != manual_t]
                st.session_state['st360_db_v7'].append(res)
                st.rerun()

# --- VISTA ---
st.title("🧠 SystemaTrader 360: Master Database")
st.caption("Algoritmo de Fusión: Técnico (40%) + Estructura (30%) + Estacionalidad (30%)")

if st.session_state['st360_db_v7']:
    df_view = pd.DataFrame(st.session_state['st360_db_v7'])
    if 'Score' in df_view.columns: df_view = df_view.sort_values("Score", ascending=False)
    
    st.subheader("1. Tablero de Comando")
    st.dataframe(
        df_view[['Ticker', 'Price', 'Score', 'Verdict', 'S_Tec', 'S_Opt', 'S_Sea']],
        column_config={
            "Ticker": "Activo",
            "Price": st.column_config.NumberColumn(format="$%.2f"),
            "Score": st.column_config.ProgressColumn("Puntaje Crítico", min_value=0, max_value=100, format="%.0f"),
            "S_Tec": st.column_config.NumberColumn("Técnico", format="%.1f"),
            "S_Opt": st.column_config.NumberColumn("Opciones", format="%.1f"),
            "S_Sea": st.column_config.NumberColumn("Estacional", format="%.1f"),
        },
        use_container_width=True, hide_index=True, height=350
    )
    
    st.divider()
    st.subheader("2. Inspección de Activo")
    # Filtramos solo los que tienen datos válidos para el detalle
    valid_options = df_view[df_view['Verdict'] != "⚠️ SIN DATOS"]['Ticker'].tolist()
    
    if valid_options:
        selection = st.selectbox("Selecciona para ver detalle:", valid_options)
        item = next((x for x in st.session_state['st360_db_v7'] if x['Ticker'] == selection), None)
        
        if item:
            c1, c2, c3 = st.columns(3)
            sc = item['Score']
            clr = "#00C853" if sc >= 70 else "#D32F2F" if sc <= 40 else "#FBC02D"
            
            with c1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="score-label">TÉCNICO (40%)</div>
                    <div class="big-score" style="color: #555;">{item['S_Tec']:.1f}<span style="font-size:1rem">/10</span></div>
                    <div class="sub-info">{item['D_Tec_Str']}</div>
                </div>""", unsafe_allow_html=True)
                
            with c2:
                st.markdown(f"""
                <div class="metric-card" style="border: 2px solid {clr};">
                    <div class="score-label" style="color:{clr};">PUNTAJE CRÍTICO</div>
                    <div class="big-score" style="color: {clr};">{sc:.0f}<span style="font-size:1rem">/100</span></div>
                    <div style="font-weight:bold; color:{clr};">{item['Verdict']}</div>
                </div>""", unsafe_allow_html=True)
                
            with c3:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="score-label">ESTRUCTURA (30%)</div>
                    <div class="big-score" style="color: #555;">{item['S_Opt']:.1f}<span style="font-size:1rem">/10</span></div>
                    <div class="sub-info">{item['D_Opt']}</div>
                    <div class="sentiment-tag" style="background-color: #f0f2f6; border: 1px solid #ccc; color: #333;">
                        {item['Sentiment']}
                    </div>
                </div>""", unsafe_allow_html=True)
                
            st.caption(f"📅 Estacionalidad: **{item['S_Sea']:.1f}/10** - {item['D_Sea']}")
            
            with st.expander("🧮 Auditoría del Cálculo (Caja Blanca)"):
                st.markdown("**1. Técnico (Multi-Timeframe):**")
                for d in item['D_Tec_List']:
                    st.markdown(f"- {'✅' if '(+' in d else '❌'} {d}")
                    
                st.markdown(f"""
                **2. Estructura y Sentimiento:**
                - Ratio Put/Call: {item['Sentiment']}
                - Precio: ${item['Price']:.2f}
                - Muros: Put ${item['PW']:.2f} | Call ${item['CW']:.2f}
                - Max Pain: ${item['Max_Pain']:.2f}
                
                **3. Estacionalidad Financiera:**
                - {item['D_Sea']}
                """)
                
            if item['History'] is not None:
                hist = item['History']
                fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'])])
                if item['CW'] > 0:
                    fig.add_hline(y=item['CW'], line_dash="dash", line_color="red", annotation_text="Call Wall")
                    fig.add_hline(y=item['PW'], line_dash="dash", line_color="green", annotation_text="Put Wall")
                    fig.add_hline(y=item['Max_Pain'], line_dash="dot", line_color="blue", annotation_text="Max Pain")
                
                fig.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_white", margin=dict(t=20, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Los activos escaneados no tienen datos válidos para mostrar detalles (Error de descarga o sin historial).")

else: st.info("👈 Selecciona un lote para comenzar.")
