import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import re # Importamos Regex para procesar tu texto

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Options Screener Ultimate")

# --- BASE DE DATOS MAESTRA ---
CEDEAR_DATABASE = {
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX',
    'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'XLE', 'XLF', 'ARKK', 'EWZ', 'GLD', 'SLV',
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'AMD', 'NFLX', 'INTC', 'QCOM', 'AVGO', 'CRM', 'CSCO', 'ORCL', 'IBM', 'UBER', 'ABNB', 'PLTR', 'SPOT', 'TSM', 'MU', 'ARM', 'SMCI',
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B', 'PYPL', 'SQ',
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'PG', 'JNJ', 'PFE', 'MRK', 'LLY', 'XOM', 'CVX', 'SLB', 'BA', 'CAT', 'MMM', 'GE', 'DE', 'F', 'GM', 'TM',
    'COIN', 'MSTR', 'HUT', 'BITF',
    'PBR', 'VALE', 'ITUB', 'BBD', 'BABA', 'JD', 'BIDU'
}

STOCK_GROUPS = {
    '🇦🇷 Argentina (ADRs)': ['GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI'],
    '🇺🇸 ETFs (Índices)': ['SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'XLE', 'XLF', 'ARKK', 'EWZ'],
    '🇺🇸 Magnificent 7 + Tech': ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NFLX', 'CRM'],
    '🇺🇸 Semiconductores & AI': ['AMD', 'INTC', 'QCOM', 'AVGO', 'TSM', 'MU', 'ARM', 'SMCI', 'PLTR'],
    '🇺🇸 Financiero': ['JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'BRK-B', 'PYPL'],
    '🇺🇸 Consumo & Dividendos': ['KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'PG', 'JNJ', 'XOM', 'CVX'],
    '🇺🇸 Crypto & Volatilidad': ['COIN', 'MSTR', 'UBER', 'ABNB', 'SQ', 'TSLA'],
    '🌎 Brasil & China': ['PBR', 'VALE', 'ITUB', 'BABA', 'JD', 'BIDU']
}

# --- FUNCIONES ---
def get_sentiment_label(ratio):
    if ratio < 0.7: return "🚀 ALCISTA"
    elif ratio > 1.0: return "🐻 BAJISTA"
    else: return "⚖️ NEUTRAL"

def generate_links(ticker):
    yahoo_link = f"https://finance.yahoo.com/quote/{ticker}/options"
    tv_link = f"https://es.tradingview.com/chart/?symbol=BCBA%3A{ticker}"
    return yahoo_link, tv_link

def check_proximity(price, wall_price, threshold_pct):
    if wall_price == 0 or price == 0: return False
    distance = abs(price - wall_price) / price * 100
    return distance <= threshold_pct

@st.cache_data(ttl=1800)
def analyze_options_chain(ticker):
    try:
        tk = yf.Ticker(ticker)
        current_price = 0
        if hasattr(tk, 'fast_info') and tk.fast_info.last_price:
            current_price = tk.fast_info.last_price
        if current_price == 0:
            hist = tk.history(period="1d")
            if not hist.empty: current_price = hist['Close'].iloc[-1]
        
        if current_price == 0: return None

        exps = tk.options
        if not exps: return None
        target_date = exps[0]
        opts = tk.option_chain(target_date)
        calls = opts.calls
        puts = opts.puts
        
        if calls.empty or puts.empty: return None
        
        total_call_oi = calls['openInterest'].sum()
        total_put_oi = puts['openInterest'].sum()
        if total_call_oi == 0: total_call_oi = 1
        
        pc_ratio = total_put_oi / total_call_oi
        
        call_wall = calls.loc[calls['openInterest'].idxmax()]['strike'] if not calls.empty else 0
        put_wall = puts.loc[puts['openInterest'].idxmax()]['strike'] if not puts.empty else 0
        
        data_quality = "OK"
        market_consensus = (call_wall + put_wall) / 2
        calculation_price = current_price
        if market_consensus > 0:
            if abs(current_price - market_consensus) / market_consensus > 0.4:
                data_quality = "ERROR_PRECIO"
                calculation_price = market_consensus 

        strikes = sorted(list(set(calls['strike'].tolist() + puts['strike'].tolist())))
        strikes = [s for s in strikes if calculation_price * 0.5 < s < calculation_price * 1.5]
        
        cash_values = []
        for strike in strikes:
            intrinsic_calls = calls.apply(lambda row: max(0, strike - row['strike']) * row['openInterest'], axis=1).sum()
            intrinsic_puts = puts.apply(lambda row: max(0, row['strike'] - strike) * row['openInterest'], axis=1).sum()
            cash_values.append(intrinsic_calls + intrinsic_puts)
        
        max_pain = strikes[np.argmin(cash_values)] if cash_values else calculation_price
        
        return {
            'Ticker': ticker, 'Price': current_price, 'Max_Pain': max_pain,
            'PC_Ratio': pc_ratio, 'Call_OI': total_call_oi, 'Put_OI': total_put_oi,
            'Expiration': target_date,
            'Call_Wall': call_wall, 'Put_Wall': put_wall,
            'Data_Quality': data_quality, 'Calculated_Price_Ref': calculation_price,
            'Calls_DF': calls, 'Puts_DF': puts
        }
    except Exception: return None

def get_batch_analysis(ticker_list):
    results = []
    prog = st.progress(0)
    total = len(ticker_list)
    status_text = st.empty()
    
    for i, t in enumerate(ticker_list):
        status_text.text(f"Analizando {t} ({i+1}/{total})...")
        data = analyze_options_chain(t)
        if data: results.append(data)
        prog.progress((i + 1) / total)
        
    prog.empty()
    status_text.empty()
    return results

# --- INTERFAZ ---
st.title("🌎 SystemaTrader: Escáner Global de Oportunidades")

if 'analysis_results' not in st.session_state:
    st.session_state['analysis_results'] = {}
    st.session_state['current_view'] = "Esperando escaneo..."

# --- SIDEBAR (MODIFICADO PARA CUSTOM INPUT) ---
with st.sidebar:
    st.header("⚙️ Configuración")
    proximity_threshold = st.slider("Alerta Proximidad (%)", 1, 10, 3)
    
    st.divider()
    
    # SECCIÓN 1: MERCADO COMPLETO
    st.header("1. Escaneo Masivo")
    if st.button("ESCANEAR BASE DE DATOS ENTERA", type="primary"):
        st.session_state['current_view'] = "Mercado Completo (ADRs + CEDEARs)"
        sorted_tickers = sorted(list(CEDEAR_DATABASE))
        with st.spinner("Conectando con el mercado de opciones..."):
            st.session_state['analysis_results'] = get_batch_analysis(sorted_tickers)

    st.divider()

    # SECCIÓN 2: TU LISTA
    st.header("2. Lista Personalizada")
    st.info("Escribe los tickers separados por coma o espacio.")
    
    # Text Area para input libre
    custom_input = st.text_area("Ingresa Activos (Ej: AAPL, MELI, GGAL):", height=100)
    
    if st.button("🎯 ANALIZAR MI LISTA"):
        if custom_input:
            # Limpieza de input usando Regex (separa por comas, espacios o saltos de línea)
            custom_tickers = re.split(r'[,\s\n]+', custom_input)
            # Filtramos vacíos y ponemos mayúsculas
            custom_tickers = [t.strip().upper() for t in custom_tickers if t.strip()]
            
            if custom_tickers:
                st.session_state['current_view'] = "Lista Personalizada"
                with st.spinner(f"Analizando {len(custom_tickers)} activos seleccionados..."):
                    st.session_state['analysis_results'] = get_batch_analysis(custom_tickers)
            else:
                st.error("Por favor escribe al menos un ticker válido.")
        else:
            st.error("El campo está vacío.")

    st.markdown("---")
    st.caption("SystemaTrader v12.0")

# --- FASE 1: TABLERO GLOBAL ---
st.subheader(f"1️⃣ Resultados: {st.session_state.get('current_view', 'Sin Datos')}")

if st.session_state['analysis_results']:
    results = st.session_state['analysis_results']
    df_table = pd.DataFrame(results)
    
    if not df_table.empty:
        def get_alert_status(row):
            if row['Data_Quality'] == 'ERROR_PRECIO': return "❌ ERROR DATA"
            status = []
            if check_proximity(row['Price'], row['Call_Wall'], proximity_threshold): status.append("🧱 TECHO")
            if check_proximity(row['Price'], row['Put_Wall'], proximity_threshold): status.append("🟢 PISO")
            return " + ".join(status) if status else "OK"

        df_display = df_table.copy()
        df_display['Alerta'] = df_display.apply(get_alert_status, axis=1)
        df_display['Sentimiento'] = df_display['PC_Ratio'].apply(get_sentiment_label)
        
        # --- CÁLCULO DE PORCENTAJES DE DISTANCIA ---
        df_display['% Techo'] = ((df_display['Call_Wall'] - df_display['Price']) / df_display['Price']) * 100
        df_display['% Piso'] = ((df_display['Put_Wall'] - df_display['Price']) / df_display['Price']) * 100

        col_filter1, col_filter2 = st.columns([1, 4])
        with col_filter1:
            show_only_alerts = st.checkbox("🔥 Mostrar solo Alertas", value=False)
        
        if show_only_alerts:
            df_final = df_display[df_display['Alerta'] != "OK"]
        else:
            df_final = df_display.sort_values(by=['Alerta', 'Ticker'], ascending=[False, True])

        # --- TABLA DEFINITIVA ---
        st.dataframe(
            df_final[['Ticker', 'Price', 'Max_Pain', 'Alerta', 'Call_Wall', '% Techo', 'Put_Wall', '% Piso', 'Sentimiento']],
            column_config={
                "Ticker": "Activo", 
                "Price": st.column_config.NumberColumn("Precio", format="$%.2f"),
                "Max_Pain": st.column_config.NumberColumn("Max Pain", format="$%.2f"),
                "Alerta": st.column_config.TextColumn("Estado"),
                "Call_Wall": st.column_config.NumberColumn("Techo", format="$%.2f"),
                "% Techo": st.column_config.NumberColumn("Dist. Techo %", format="%.2f%%", help="Distancia hasta la resistencia Call"),
                "Put_Wall": st.column_config.NumberColumn("Piso", format="$%.2f"),
                "% Piso": st.column_config.NumberColumn("Dist. Piso %", format="%.2f%%", help="Distancia hasta el soporte Put"),
            },
            use_container_width=True, hide_index=True, height=600
        )
    else: st.warning("Sin datos. Verifica que los tickers sean correctos (ej: AAPL, TSLA).")

    # --- FASE 2: DETALLE ---
    st.divider()
    st.subheader("2️⃣ Análisis Profundo")
    ticker_options = sorted([r['Ticker'] for r in results])
    if ticker_options:
        selected_ticker = st.selectbox("Selecciona Activo:", ticker_options)
        asset_data = next((i for i in results if i["Ticker"] == selected_ticker), None)
        
        if asset_data:
            if asset_data['Data_Quality'] == 'ERROR_PRECIO':
                st.error(f"🚨 **ERROR DE PRECIO:** Yahoo reporta ${asset_data['Price']:.2f} pero el mercado de opciones apunta a ${asset_data['Max_Pain']:.2f}. Verifica en TradingView.")

            k1, k2, k3, k4, k5 = st.columns(5)
            
            dist_max_pain = ((asset_data['Max_Pain'] - asset_data['Price']) / asset_data['Price']) * 100
            dist_techo = ((asset_data['Call_Wall'] - asset_data['Price']) / asset_data['Price']) * 100
            dist_piso = ((asset_data['Put_Wall'] - asset_data['Price']) / asset_data['Price']) * 100

            k1.metric("Precio", f"${asset_data['Price']:.2f}")
            k2.metric("Max Pain (Imán)", f"${asset_data['Max_Pain']:.2f}", delta=f"{dist_max_pain:.1f}%", delta_color="off")
            k3.metric("Sentimiento", get_sentiment_label(asset_data['PC_Ratio']), delta=f"Ratio: {asset_data['PC_Ratio']:.2f}")
            k4.metric("Techo (Resistencia)", f"${asset_data['Call_Wall']:.2f}", delta=f"{dist_techo:.1f}%", delta_color="normal")
            k5.metric("Piso (Soporte)", f"${asset_data['Put_Wall']:.2f}", delta=f"{dist_piso:.1f}%", delta_color="normal")

            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown("##### Sentimiento")
                labels = ['Calls', 'Puts']
                values = [asset_data['Call_OI'], asset_data['Put_OI']]
                fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.4, marker=dict(colors=['#00CC96', '#EF553B']))])
                fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, showlegend=False)
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with c2:
                st.markdown("##### Muro de Liquidez")
                calls, puts = asset_data['Calls_DF'], asset_data['Puts_DF']
                center_price = asset_data['Calculated_Price_Ref']
                min_s, max_s = center_price * 0.85, center_price * 1.15
                c_filt = calls[(calls['strike'] >= min_s) & (calls['strike'] <= max_s)]
                p_filt = puts[(puts['strike'] >= min_s) & (puts['strike'] <= max_s)]
                
                fig_wall = go.Figure()
                fig_wall.add_trace(go.Bar(x=c_filt['strike'], y=c_filt['openInterest'], name='Calls (Techo)', marker_color='#00CC96'))
                fig_wall.add_trace(go.Bar(x=p_filt['strike'], y=p_filt['openInterest'], name='Puts (Piso)', marker_color='#EF553B'))
                
                if asset_data['Data_Quality'] == "OK":
                    fig_wall.add_vline(x=asset_data['Price'], line_dash="dash", line_color="white", annotation_text="Precio")
                
                fig_wall.add_vline(x=asset_data['Call_Wall'], line_dash="dot", line_color="#00FF00", annotation_text="TECHO")
                fig_wall.add_vline(x=asset_data['Put_Wall'], line_dash="dot", line_color="#FF0000", annotation_text="PISO")
                fig_wall.add_vline(x=asset_data['Max_Pain'], line_dash="dash", line_color="yellow", annotation_text="Max Pain")
                
                fig_wall.update_layout(barmode='overlay', height=350, margin=dict(t=20), xaxis_title="Strike ($)", yaxis_title="Contratos", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_wall, use_container_width=True)

            ratio_desc = "🔥 **EXTREMO MIEDO / OPORTUNIDAD:** Mercado muy cubierto (Posible Rebote)." if asset_data['PC_Ratio'] > 1.2 else ("🚀 **EUFORIA:** Cuidado, demasiada confianza alcista." if asset_data['PC_Ratio'] < 0.6 else "⚖️ **NEUTRAL:** Mercado balanceado.")
            st.info(f"### 🧠 Interpretación Táctica:\n1. **Imán (Max Pain ${asset_data['Max_Pain']:.2f}):** Precio objetivo de MM.\n2. **Sentimiento:** {ratio_desc}")
            
            link_yahoo, link_tv = generate_links(selected_ticker)
            st.markdown("---")
            col_foot1, col_foot2 = st.columns(2)
            col_foot1.markdown(f"🔍 [Auditar Fuente Oficial (Yahoo Finance)]({link_yahoo})")
            col_foot2.markdown(f"📈 [Abrir Gráfico (TradingView)]({link_tv})")

else:
    st.info("Dale al botón 'ESCANEAR' en la barra lateral para iniciar.")
