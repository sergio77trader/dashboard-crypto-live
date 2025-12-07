import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import re # Importamos Regex para limpiar la lista de entrada

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Options Screener Pro")

# --- BASE DE DATOS ---
CEDEAR_SET = {
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'AMD', 'INTC', 'QCOM',
    'KO', 'PEP', 'WMT', 'PG', 'COST', 'MCD', 'SBUX', 'DIS', 'NKE',
    'XOM', 'CVX', 'SLB', 'PBR', 'VIST',
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'V', 'MA', 'BRK-B',
    'GGAL', 'BMA', 'YPF', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'GLOB', 'MELI', 'BIOX'
}

STOCK_GROUPS = {
    '🇦🇷 Argentina (ADRs en USA)': ['GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX'],
    '🇺🇸 Big Tech (Magnificent 7)': ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META'],
    '🇺🇸 High Volatility & AI': ['AMD', 'PLTR', 'COIN', 'MSTR', 'ARM', 'SMCI', 'TSM', 'AVGO'],
    '🇺🇸 Blue Chips (Dow Jones)': ['KO', 'MCD', 'JPM', 'DIS', 'BA', 'CAT', 'XOM', 'CVX', 'WMT']
}

# --- FUNCIONES ---
def get_sentiment_label(ratio):
    if ratio < 0.7: return "🚀 ALCISTA"
    elif ratio > 1.0: return "🐻 BAJISTA"
    else: return "⚖️ NEUTRAL"

def generate_links(ticker, has_cedear):
    yahoo_link = f"https://finance.yahoo.com/quote/{ticker}/options"
    symbol = f"BCBA%3A{ticker}" if has_cedear else ticker
    tv_link = f"https://es.tradingview.com/chart/?symbol={symbol}"
    return yahoo_link, tv_link

@st.cache_data(ttl=1800)
def analyze_options_chain(ticker):
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="1d")
        if hist.empty: return None
        current_price = hist['Close'].iloc[-1]
        
        exps = tk.options
        if not exps: return None
        target_date = exps[0]
        opts = tk.option_chain(target_date)
        calls = opts.calls
        puts = opts.puts
        
        total_call_oi = calls['openInterest'].sum()
        total_put_oi = puts['openInterest'].sum()
        if total_call_oi == 0: total_call_oi = 1
        
        pc_ratio = total_put_oi / total_call_oi
        
        # Max Pain
        strikes = sorted(list(set(calls['strike'].tolist() + puts['strike'].tolist())))
        strikes = [s for s in strikes if current_price * 0.7 < s < current_price * 1.3]
        
        cash_values = []
        for strike in strikes:
            intrinsic_calls = calls.apply(lambda row: max(0, strike - row['strike']) * row['openInterest'], axis=1).sum()
            intrinsic_puts = puts.apply(lambda row: max(0, row['strike'] - strike) * row['openInterest'], axis=1).sum()
            cash_values.append(intrinsic_calls + intrinsic_puts)
        
        max_pain = strikes[np.argmin(cash_values)] if cash_values else current_price
        
        return {
            'Ticker': ticker, 'Price': current_price, 'Max_Pain': max_pain,
            'PC_Ratio': pc_ratio, 'Call_OI': total_call_oi, 'Put_OI': total_put_oi,
            'Expiration': target_date, 'Has_Cedear': ticker in CEDEAR_SET,
            'Calls_DF': calls, 'Puts_DF': puts
        }
    except Exception: return None

def get_batch_analysis(ticker_list):
    results = []
    prog = st.progress(0)
    for i, t in enumerate(ticker_list):
        data = analyze_options_chain(t)
        if data: results.append(data)
        prog.progress((i + 1) / len(ticker_list))
    prog.empty()
    return results

# --- INTERFAZ ---
st.title("🔮 SystemaTrader: Radar de Sentimiento Pro")

if 'analysis_results' not in st.session_state:
    st.session_state['analysis_results'] = {}
    st.session_state['current_view'] = "Esperando..."

# --- SIDEBAR (MODIFICADO) ---
with st.sidebar:
    st.header("1. Modo Grupal")
    selected_group = st.selectbox("Seleccionar Grupo:", list(STOCK_GROUPS.keys()))
    
    if st.button("🔍 Escanear Grupo"):
        tickers = STOCK_GROUPS[selected_group]
        st.session_state['current_view'] = selected_group
        with st.spinner(f"Analizando {len(tickers)} activos..."):
            st.session_state['analysis_results'] = get_batch_analysis(tickers)

    st.divider()
    
    # --- NUEVA FUNCIONALIDAD: LISTA PERSONALIZADA ---
    st.header("2. Tu Lista Personal")
    st.info("Escribe los activos separados por coma o espacio.")
    
    # Área de texto para múltiples tickers
    custom_list_raw = st.text_area("Tickers:", placeholder="AAPL, MELI, GGAL, TSLA, SPY", height=100)
    
    if st.button("🚀 Analizar Mi Selección"):
        if custom_list_raw:
            # Limpieza de texto: Reemplaza comas por espacios, divide, limpia espacios y convierte a mayúsculas
            custom_tickers = [t.strip().upper() for t in re.split(r'[,\s]+', custom_list_raw) if t.strip()]
            
            if custom_tickers:
                st.session_state['current_view'] = "Lista Personalizada"
                with st.spinner(f"Analizando {len(custom_tickers)} activos de tu lista..."):
                    st.session_state['analysis_results'] = get_batch_analysis(custom_tickers)
            else:
                st.error("Por favor escribe al menos un ticker válido.")
        else:
            st.error("El campo está vacío.")

# --- FASE 1: TABLERO ---
st.subheader(f"1️⃣ Tablero: {st.session_state.get('current_view', 'Sin Datos')}")

if st.session_state['analysis_results']:
    results = st.session_state['analysis_results']
    df_table = pd.DataFrame(results)
    
    if not df_table.empty:
        df_display = df_table.copy()
        df_display['Sentimiento'] = df_display['PC_Ratio'].apply(get_sentiment_label)
        st.dataframe(
            df_display[['Ticker', 'Price', 'Max_Pain', 'PC_Ratio', 'Sentimiento', 'Has_Cedear']],
            column_config={
                "Ticker": "Activo", "Price": st.column_config.NumberColumn("Precio", format="$%.2f"),
                "Max_Pain": st.column_config.NumberColumn("Max Pain", format="$%.2f"),
                "PC_Ratio": st.column_config.NumberColumn("Ratio", format="%.2f"),
                "Has_Cedear": st.column_config.CheckboxColumn("CEDEAR?", default=False)
            },
            use_container_width=True, hide_index=True
        )
    else: st.warning("No se encontraron datos de opciones para los activos ingresados. Verifica los tickers.")

    # --- FASE 2: ANÁLISIS PROFUNDO ---
    st.divider()
    st.subheader("2️⃣ Análisis Profundo & Auditoría")
    
    # Selector dinámico basado en los resultados
    ticker_options = [r['Ticker'] for r in results]
    if ticker_options:
        selected_ticker = st.selectbox("Selecciona Activo:", ticker_options)
        asset_data = next((i for i in results if i["Ticker"] == selected_ticker), None)
        
        if asset_data:
            link_yahoo, link_tv = generate_links(selected_ticker, asset_data['Has_Cedear'])
            c_l1, c_l2 = st.columns(2)
            c_l1.markdown(f'<a href="{link_yahoo}" target="_blank"><div style="background-color:#4B0082;color:white;padding:10px;border-radius:5px;text-align:center;font-weight:bold;">🔍 Auditar Fuente (Yahoo)</div></a>', unsafe_allow_html=True)
            c_l2.markdown(f'<a href="{link_tv}" target="_blank"><div style="background-color:#0052CC;color:white;padding:10px;border-radius:5px;text-align:center;font-weight:bold;">📈 Abrir Gráfico ({ "BCBA" if asset_data["Has_Cedear"] else "USA" })</div></a>', unsafe_allow_html=True)
            st.write("")

            if asset_data['Has_Cedear']:
                st.success(f"✅ **{selected_ticker}** tiene CEDEAR o es Acción Argentina. Operable localmente.")
            else:
                st.warning(f"⚠️ **{selected_ticker}** NO figura como CEDEAR líquido. Solo operable en cuenta EEUU.")

            k1, k2, k3, k4 = st.columns(4)
            delta_pain = asset_data['Max_Pain'] - asset_data['Price']
            k1.metric("Precio", f"${asset_data['Price']:.2f}")
            k2.metric("Max Pain", f"${asset_data['Max_Pain']:.2f}", delta=f"{delta_pain:.2f}", delta_color="off")
            k3.metric("Sentimiento", get_sentiment_label(asset_data['PC_Ratio']), delta=f"Ratio: {asset_data['PC_Ratio']:.2f}")
            k4.metric("Vencimiento", str(asset_data['Expiration']))

            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown("**Sentimiento General**")
                labels = ['Calls (Toros)', 'Puts (Osos)']
                values = [asset_data['Call_OI'], asset_data['Put_OI']]
                fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.4, marker=dict(colors=['#00CC96', '#EF553B']))])
                fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, showlegend=False)
                st.plotly_chart(fig_pie, use_container_width=True)
                st.caption("🟢 **Verde:** Apuestas a SUBE | 🔴 **Rojo:** Apuestas a BAJA.")
                
            with c2:
                st.markdown("**Muro de Liquidez (Soportes/Resistencias)**")
                calls, puts = asset_data['Calls_DF'], asset_data['Puts_DF']
                price = asset_data['Price']
                min_s, max_s = price * 0.85, price * 1.15
                c_filt = calls[(calls['strike'] >= min_s) & (calls['strike'] <= max_s)]
                p_filt = puts[(puts['strike'] >= min_s) & (puts['strike'] <= max_s)]
                
                fig_wall = go.Figure()
                fig_wall.add_trace(go.Bar(x=c_filt['strike'], y=c_filt['openInterest'], name='Calls (Techo)', marker_color='#00CC96'))
                fig_wall.add_trace(go.Bar(x=p_filt['strike'], y=p_filt['openInterest'], name='Puts (Piso)', marker_color='#EF553B'))
                fig_wall.add_vline(x=price, line_dash="dash", line_color="white", annotation_text="Precio")
                fig_wall.add_vline(x=asset_data['Max_Pain'], line_dash="dash", line_color="yellow", annotation_text="Max Pain")
                fig_wall.update_layout(barmode='overlay', height=350, margin=dict(t=20))
                st.plotly_chart(fig_wall, use_container_width=True)

            ratio_desc = "🔥 **EXTREMO MIEDO / OPORTUNIDAD:** Mercado muy cubierto (Posible Rebote)." if asset_data['PC_Ratio'] > 1.2 else ("🚀 **EUFORIA:** Cuidado, demasiada confianza alcista." if asset_data['PC_Ratio'] < 0.6 else "⚖️ **NEUTRAL:** Mercado balanceado.")
            st.info(f"""
            ### 🧠 Interpretación Táctica para {selected_ticker}:
            1.  **El Imán (Max Pain ${asset_data['Max_Pain']:.2f}):** Precio objetivo teórico de los Market Makers.
            2.  **Las Murallas:** Barras altas = Niveles difíciles de romper.
            3.  **El Sentimiento:** {ratio_desc}
            """)

else:
    st.info("Selecciona un grupo o ingresa tu lista personal para comenzar.")
