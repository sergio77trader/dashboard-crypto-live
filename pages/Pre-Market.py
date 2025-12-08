import streamlit as st
import yfinance as yf
import pandas as pd

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Watchlist Pro")

st.markdown("""
<style>
    /* Estilo tipo CNBC */
    .metric-card {
        background-color: #1e1e1e;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 10px;
        border-left: 5px solid #333;
    }
    .positive { border-left-color: #00CC96 !important; }
    .negative { border-left-color: #EF553B !important; }
</style>
""", unsafe_allow_html=True)

# --- TUS LISTAS (EXTRAÍDAS DE LA IMAGEN) ---
WATCHLISTS = {
    "🇦🇷 Argentina (ADRs)": [
        "BMA", "IRS", "GGAL", "PAM", "VIST", "CEPU", "LOMA", "YPF", "MELI"
    ],
    "🇺🇸 EEUU (Tech & Blue Chips)": [
        "MA", "JD", "ADBE", "COST", "DE", "XOM", "NFLX", "MSTR"
    ]
}

# --- MOTOR DE DATOS ---
def get_market_data(tickers):
    if not tickers: return pd.DataFrame()
    
    # Descarga masiva para velocidad
    try:
        df = yf.download(tickers, period="5d", progress=False)['Close']
        
        data = []
        for t in tickers:
            try:
                # Obtener precio actual y anterior
                # Manejo robusto si yfinance devuelve MultiIndex o Series
                if isinstance(df, pd.DataFrame) and t in df.columns:
                    series = df[t].dropna()
                else:
                    # Fallback por si la descarga masiva falla para un ticker
                    single = yf.Ticker(t).history(period="5d")['Close']
                    series = single
                
                if len(series) >= 2:
                    last_price = series.iloc[-1]
                    prev_price = series.iloc[-2]
                    change = last_price - prev_price
                    pct_change = (change / prev_price) * 100
                    
                    data.append({
                        "Symbol": t,
                        "Last": last_price,
                        "Change": change,
                        "% Chg": pct_change / 100 # Para formato %
                    })
            except:
                continue
                
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
st.title("📊 SystemaTrader: Watchlist Manager")
st.markdown("### Monitor de Activos Estratégicos")

if st.button("🔄 ACTUALIZAR PRECIOS", type="primary"):
    st.cache_data.clear()
    st.rerun()

# Layout de 2 Columnas (Como tu imagen)
col1, col2 = st.columns(2)

# --- COLUMNA 1: ARGENTINA ---
with col1:
    st.subheader("Argentina")
    group_name = "🇦🇷 Argentina (ADRs)"
    tickers = WATCHLISTS[group_name]
    
    with st.spinner("Cargando Argentina..."):
        df_arg = get_market_data(tickers)
    
    if not df_arg.empty:
        st.dataframe(
            df_arg,
            column_config={
                "Symbol": st.column_config.TextColumn("Activo", width="small"),
                "Last": st.column_config.NumberColumn("Último", format="$%.2f"),
                "Change": st.column_config.NumberColumn("Cambio $", format="%.2f"),
                "% Chg": st.column_config.NumberColumn("% Var", format="%.2f%%")
            },
            use_container_width=True,
            hide_index=True
        )

# --- COLUMNA 2: EEUU ---
with col2:
    st.subheader("EEUU")
    group_name = "🇺🇸 EEUU (Tech & Blue Chips)"
    tickers = WATCHLISTS[group_name]
    
    with st.spinner("Cargando Wall Street..."):
        df_usa = get_market_data(tickers)
        
    if not df_usa.empty:
        st.dataframe(
            df_usa,
            column_config={
                "Symbol": st.column_config.TextColumn("Activo", width="small"),
                "Last": st.column_config.NumberColumn("Último", format="$%.2f"),
                "Change": st.column_config.NumberColumn("Cambio $", format="%.2f"),
                "% Chg": st.column_config.NumberColumn("% Var", format="%.2f%%")
            },
            use_container_width=True,
            hide_index=True
        )

# --- EDITOR RÁPIDO (Opcional) ---
with st.expander("✏️ Editar Listas (Temporal)"):
    new_ticker = st.text_input("Agregar Ticker a EEUU (Ej: TSLA):")
    if st.button("Agregar"):
        st.info("Para guardar cambios permanentes, edita la lista WATCHLISTS en el código de GitHub.")
