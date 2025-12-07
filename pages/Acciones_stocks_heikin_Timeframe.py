import streamlit as st
import yfinance as yf
import pandas as pd

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Stocks HA Matrix Pro")

# --- BASE DE DATOS MAESTRA (ADRs + CEDEARs en USD) ---
TICKERS_DB = sorted([
    # --- ARGENTINA (ADRs) ---
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX',
    # --- BIG TECH / AI / SEMIS ---
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NFLX', 
    'AMD', 'INTC', 'QCOM', 'AVGO', 'TSM', 'MU', 'ARM', 'SMCI', 'TXN', 'ADI',
    # --- SOFTWARE / CLOUD / CYBER ---
    'ADBE', 'CRM', 'ORCL', 'IBM', 'PLTR', 'SPOT', 'SHOP', 'SNOW', 'PANW', 'CRWD', 'SQ', 'PYPL', 'UBER', 'ABNB',
    # --- CONSUMO / RETAIL ---
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'TGT', 'HD', 'LOW', 'AMGN',
    # --- FINANCIEROS ---
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B',
    # --- INDUSTRIAL / ENERGIA / SALUD ---
    'XOM', 'CVX', 'SLB', 'BA', 'CAT', 'MMM', 'GE', 'DE', 'F', 'GM', 'TM', 'JNJ', 'PFE', 'MRK', 'LLY',
    # --- ETFS (Índices y Sectores) ---
    'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'XLE', 'XLF', 'ARKK', 'EWZ', 'GLD', 'SLV',
    # --- GLOBAL / CRYPTO / OTROS ---
    'PBR', 'VALE', 'ITUB', 'BBD', 'BABA', 'JD', 'BIDU', 'COIN', 'MSTR', 'HUT', 'BITF', 'NGG'
])

# --- MOTOR DE CÁLCULO ---

def calculate_heikin_ashi(df):
    """Convierte velas OHLC normales a Heikin Ashi"""
    if df is None or df.empty: return pd.DataFrame()
    
    # Asegurar nombres de columnas
    df.columns = [c.capitalize() for c in df.columns]
    
    if 'Open' not in df.columns or 'Close' not in df.columns:
        return pd.DataFrame()

    df_ha = df.copy()
    
    # HA Close
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    # HA Open (Iterativo)
    df_ha['HA_Open'] = 0.0
    # Inicializamos
    df_ha.iat[0, df_ha.columns.get_loc('HA_Open')] = (df.iloc[0]['Open'] + df.iloc[0]['Close']) / 2
    
    # Bucle vectorizado optimizado
    ha_open_idx = df_ha.columns.get_loc('HA_Open')
    ha_close_idx = df_ha.columns.get_loc('HA_Close')
    
    vals = df_ha.values
    for i in range(1, len(vals)):
        vals[i, ha_open_idx] = (vals[i-1, ha_open_idx] + vals[i-1, ha_close_idx]) / 2
    
    df_ha['HA_Open'] = vals[:, ha_open_idx]
        
    return df_ha

def get_candle_status(df_ha):
    """Determina si la última vela es Verde o Roja"""
    if df_ha.empty: return "N/A"
    try:
        last = df_ha.iloc[-1]
        return "🟢 ALCISTA" if last['HA_Close'] > last['HA_Open'] else "🔴 BAJISTA"
    except:
        return "N/A"

@st.cache_data(ttl=900) # Cache de 15 minutos
def fetch_bulk_data(tickers):
    """Descarga masiva optimizada"""
    try:
        # Descarga 1: Datos Horarios (Último mes para 1H y 4H)
        data_1h = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False, auto_adjust=True, threads=True)
        
        # Descarga 2: Datos Diarios (Últimos 2 años para asegurar Mensual correcto)
        data_1d = yf.download(tickers, period="2y", interval="1d", group_by='ticker', progress=False, auto_adjust=True, threads=True)
        
        return data_1h, data_1d
    except Exception as e:
        return None, None

def process_market_matrix(tickers):
    # 1. Descarga Masiva
    with st.spinner("📡 Conectando con Wall Street (Descarga Masiva)..."):
        bulk_1h, bulk_1d = fetch_bulk_data(tickers)
    
    if bulk_1h is None or bulk_1d is None or bulk_1h.empty:
        st.error("Error: Yahoo Finance no respondió. Intenta de nuevo en 1 minuto.")
        return pd.DataFrame()

    results = []
    prog = st.progress(0, text="Procesando Algoritmo Heikin Ashi...")
    total = len(tickers)
    
    # 2. Procesamiento Individual
    for i, t in enumerate(tickers):
        row = {'Activo': t}
        
        try:
            # Extraer data de los dataframes masivos
            try:
                # Manejo robusto de MultiIndex de Pandas
                df_intra = bulk_1h[t].copy().dropna() if t in bulk_1h.columns.levels[0] else pd.DataFrame()
                df_daily = bulk_1d[t].copy().dropna() if t in bulk_1d.columns.levels[0] else pd.DataFrame()
                
                # Fallback si la estructura es plana (un solo ticker)
                if df_intra.empty and len(tickers) == 1: df_intra = bulk_1h.copy().dropna()
                if df_daily.empty and len(tickers) == 1: df_daily = bulk_1d.copy().dropna()
                
            except Exception:
                continue

            # --- PROCESAMIENTO INTRADÍA (1H, 4H) ---
            if not df_intra.empty:
                # 1 Hora
                ha_1h = calculate_heikin_ashi(df_intra)
                row['1H'] = get_candle_status(ha_1h)
                
                # 4 Horas (Resampling)
                logic = {'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}
                df_intra.columns = [c.capitalize() for c in df_intra.columns]
                df_4h = df_intra.resample('4h').agg(logic).dropna()
                ha_4h = calculate_heikin_ashi(df_4h)
                row['4H'] = get_candle_status(ha_4h)
            else:
                row['1H'] = "N/A"
                row['4H'] = "N/A"

            # --- PROCESAMIENTO MACRO (Diario, Semanal, Mensual) ---
            if not df_daily.empty:
                # Diario
                ha_1d = calculate_heikin_ashi(df_daily)
                row['Diario'] = get_candle_status(ha_1d)
                
                # Asegurar nombres
                df_daily.columns = [c.capitalize() for c in df_daily.columns]
                logic = {'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}
                
                # Semanal
                df_1w = df_daily.resample('W').agg(logic).dropna()
                ha_1w = calculate_heikin_ashi(df_1w)
                row['Semanal'] = get_candle_status(ha_1w)
                
                # Mensual
                try:
                    df_1m = df_daily.resample('ME').agg(logic).dropna()
                except:
                    df_1m = df_daily.resample('M').agg(logic).dropna()
                    
                ha_1m = calculate_heikin_ashi(df_1m)
                row['Mensual'] = get_candle_status(ha_1m)
            else:
                row['Diario'] = "N/A"
                row['Semanal'] = "N/A"
                row['Mensual'] = "N/A"
        
        except Exception:
            row['1H'] = "Error"
        
        results.append(row)
        prog.progress((i + 1) / total)
        
    prog.empty()
    return pd.DataFrame(results)

# --- INTERFAZ ---
st.title("🏙️ SystemaTrader: Wall Street Heikin Ashi Matrix (Pro)")
st.markdown(f"Monitor de Tendencia Multi-Timeframe (1H a Mensual). Universo: **{len(TICKERS_DB)} Activos**.")

if st.button("🚀 ESCANEAR TENDENCIAS (BULK)", type="primary"):
    df_results = process_market_matrix(TICKERS_DB)
    
    if not df_results.empty:
        # --- LÓGICA DE DIAGNÓSTICO (SCORE 0-5) ---
        def check_alignment(row):
            cols_to_check = ['1H', '4H', 'Diario', 'Semanal', 'Mensual']
            greens = sum([1 for col in cols_to_check if "🟢" in str(row.get(col, ''))])
            
            if greens == 5: return "🔥 FULL ALCISTA"
            if greens == 0: return "❄️ FULL BAJISTA"
            if greens >= 4: return "✅ ALCISTA FUERTE"
            if greens <= 1: return "🔻 BAJISTA FUERTE"
            return "⚖️ MIXTO"

        df_results['Diagnóstico'] = df_results.apply(check_alignment, axis=1)
        
        # Ordenar: Oportunidades primero
        sort_map = {"🔥 FULL ALCISTA": 0, "❄️ FULL BAJISTA": 1, "✅ ALCISTA FUERTE": 2, "🔻 BAJISTA FUERTE": 3, "⚖️ MIXTO": 4}
        df_results['sort'] = df_results['Diagnóstico'].map(sort_map)
        df_results = df_results.sort_values('sort').drop('sort', axis=1)
        
        # --- KPIS ---
        bulls = len(df_results[df_results['Diagnóstico'] == "🔥 FULL ALCISTA"])
        bears = len(df_results[df_results['Diagnóstico'] == "❄️ FULL BAJISTA"])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Activos Procesados", len(df_results))
        c2.metric("Full Alcistas (5/5)", bulls)
        c3.metric("Full Bajistas (0/5)", bears)
        
        # --- TABLA ---
        st.divider()
        f_mode = st.radio("Filtro Rápido:", ["Ver Todo", "Solo Oportunidades (Full Bull/Bear)"], horizontal=True)
        
        if f_mode == "Solo Oportunidades (Full Bull/Bear)":
            df_show = df_results[df_results['Diagnóstico'].isin(["🔥 FULL ALCISTA", "❄️ FULL BAJISTA"])]
        else:
            df_show = df_results

        st.dataframe(
            df_show,
            column_config={
                "Activo": st.column_config.TextColumn("Ticker", width="small"),
                "Diagnóstico": st.column_config.TextColumn("Estado", width="medium"),
            },
            use_container_width=True,
            hide_index=True,
            height=800
        )
else:
    st.info("Presiona el botón para descargar los datos de todo el mercado.")
