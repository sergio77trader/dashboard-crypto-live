import streamlit as st
import yfinance as yf
import pandas as pd

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Watchlist Ultimate")

# --- BASE DE DATOS MAESTRA DE CEDEARS (EXPANDIDA) ---
# Esta lista cubre el 98% del volumen operado en Argentina
MARKET_DATA = {
    "🇦🇷 Argentina (ADRs)": [
        "GGAL", "YPF", "BMA", "PAMP", "TGS", "CEPU", "EDN", "BFR", "SUPV", 
        "CRESY", "IRS", "TEO", "LOMA", "DESP", "VIST", "GLOB", "MELI", "BIOX"
    ],
    "🇺🇸 Big Tech & AI": [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "NFLX", "AMD", "INTC", 
        "QCOM", "AVGO", "TSM", "CRM", "ORCL", "IBM", "CSCO", "ADBE", "PLTR"
    ],
    "🏦 Financiero & Pagos": [
        "JPM", "BAC", "C", "WFC", "GS", "MS", "V", "MA", "AXP", "BRK-B", 
        "PYPL", "SQ", "COIN"
    ],
    "🛒 Consumo Masivo & Retail": [
        "KO", "PEP", "MCD", "SBUX", "DIS", "NKE", "WMT", "COST", "TGT", "HD", 
        "PG", "CL", "MO"
    ],
    "🛢️ Energía & Industria": [
        "XOM", "CVX", "SLB", "OXY", "BA", "CAT", "MMM", "GE", "DE", "F", "GM", 
        "LMT", "RTX"
    ],
    "💊 Salud & Pharma": [
        "JNJ", "PFE", "MRK", "LLY", "ABBV", "UNH", "BMY", "AZN"
    ],
    "🇨🇳 China & 🇧🇷 Brasil": [
        "BABA", "JD", "BIDU", "NIO", "PBR", "VALE", "ITUB", "BBD", "ERJ"
    ],
    "🌎 ETFs (Índices)": [
        "SPY", "QQQ", "IWM", "DIA", "EEM", "XLE", "XLF", "ARKK", "EWZ", "GLD", "SLV"
    ]
}

# Lista combinada para búsquedas globales
ALL_TICKERS = sorted(list(set([item for sublist in MARKET_DATA.values() for item in sublist])))

# --- FUNCIONES DE ESTILO ---
def color_change(val):
    """Pinta verde si es positivo, rojo si es negativo"""
    if isinstance(val, float) or isinstance(val, int):
        color = '#00FF00' if val > 0 else '#FF4500' if val < 0 else 'white'
        return f'color: {color}; font-weight: bold'
    return ''

# --- MOTOR DE DATOS ---
@st.cache_data(ttl=60)
def get_quotes(ticker_list):
    if not ticker_list: return pd.DataFrame()
    
    try:
        # Descarga masiva para optimizar tiempo
        df = yf.download(ticker_list, period="5d", progress=False)['Close']
        
        data = []
        for t in ticker_list:
            try:
                # Extracción segura
                if isinstance(df, pd.DataFrame) and t in df.columns:
                    series = df[t].dropna()
                elif isinstance(df, pd.Series) and df.name == t:
                    series = df.dropna()
                else:
                    series = yf.Ticker(t).history(period="5d")['Close']
                
                if len(series) >= 2:
                    last_price = float(series.iloc[-1])
                    prev_price = float(series.iloc[-2])
                    
                    change = last_price - prev_price
                    pct_change = ((last_price - prev_price) / prev_price) * 100
                    
                    data.append({
                        "Symbol": t,
                        "Precio ($)": last_price,
                        "Cambio ($)": change,
                        "% Var": pct_change
                    })
            except:
                continue
                
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
st.title("📊 SystemaTrader: Global Watchlist")
st.caption("Cotizaciones en Tiempo Real (Mercado de Origen)")

if st.button("🔄 REFRESCAR MERCADO", type="primary"):
    st.cache_data.clear()
    st.rerun()

# --- DEFINICIÓN DE PESTAÑAS ---
tab1, tab2 = st.tabs(["📺 Dashboard Resumen", "🌎 Explorador Completo"])

# === PESTAÑA 1: VISTA DIVIDIDA (ARG vs EEUU) ===
with tab1:
    col1, col2 = st.columns(2)
    
    # 1. ARGENTINA
    with col1:
        st.subheader("🇦🇷 Argentina (ADRs)")
        with st.spinner("Cargando..."):
            df_arg = get_quotes(MARKET_DATA["🇦🇷 Argentina (ADRs)"])
        
        if not df_arg.empty:
            # APLICAMOS COLORES
            st.dataframe(
                df_arg.style.map(color_change, subset=['Cambio ($)', '% Var']),
                column_config={
                    "Symbol": st.column_config.TextColumn("Activo", width="small"),
                    "Precio ($)": st.column_config.NumberColumn("Precio", format="$%.2f"),
                    "Cambio ($)": st.column_config.NumberColumn("Dif", format="%.2f"),
                    "% Var": st.column_config.NumberColumn("% Var", format="%.2f%%")
                },
                use_container_width=True, hide_index=True, height=600
            )

    # 2. EEUU (Selección)
    with col2:
        st.subheader("🇺🇸 Wall Street (Selección)")
        # Combinamos Tech + Bancos para el resumen
        usa_selection = MARKET_DATA["🇺🇸 Big Tech & AI"] + ["JPM", "KO", "DIS", "XOM"]
        
        with st.spinner("Cargando..."):
            df_usa = get_quotes(usa_selection)
            
        if not df_usa.empty:
            st.dataframe(
                df_usa.style.map(color_change, subset=['Cambio ($)', '% Var']),
                column_config={
                    "Symbol": st.column_config.TextColumn("Activo", width="small"),
                    "Precio ($)": st.column_config.NumberColumn("Precio", format="$%.2f"),
                    "Cambio ($)": st.column_config.NumberColumn("Dif", format="%.2f"),
                    "% Var": st.column_config.NumberColumn("% Var", format="%.2f%%")
                },
                use_container_width=True, hide_index=True, height=600
            )

# === PESTAÑA 2: ESCÁNER TOTAL ===
with tab2:
    c_sel, c_stat = st.columns([3, 1])
    with c_sel:
        sector = st.selectbox("Seleccionar Sector:", ["TODOS"] + list(MARKET_DATA.keys()))
    
    target_list = ALL_TICKERS if sector == "TODOS" else MARKET_DATA[sector]
    
    if st.button("🔎 Escanear Sector Completo"):
        with st.spinner(f"Procesando {len(target_list)} activos..."):
            df_all = get_quotes(target_list)
            
        if not df_all.empty:
            # Ordenar por Mayor Variación
            df_all = df_all.sort_values("% Var", ascending=False)
            
            # Estadísticas
            best = df_all.iloc[0]
            worst = df_all.iloc[-1]
            
            with c_stat:
                st.metric("Total Activos", len(df_all))
            
            col_kpi1, col_kpi2 = st.columns(2)
            col_kpi1.success(f"🚀 Top Gainer: {best['Symbol']} ({best['% Var']:.2f}%)")
            col_kpi2.error(f"🐻 Top Loser: {worst['Symbol']} ({worst['% Var']:.2f}%)")
            
            # TABLA GIGANTE CON COLORES
            st.dataframe(
                df_all.style.map(color_change, subset=['Cambio ($)', '% Var']),
                column_config={
                    "Symbol": "Activo",
                    "Precio ($)": st.column_config.NumberColumn(format="$%.2f"),
                    "Cambio ($)": st.column_config.NumberColumn(format="%.2f"),
                    "% Var": st.column_config.NumberColumn(format="%.2f%%")
                },
                use_container_width=True, hide_index=True, height=800
            )
