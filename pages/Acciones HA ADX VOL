import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - HA Matrix & ADX Strategy")

# --- BASE DE DATOS (Mismos Tickers) ---
TICKERS_DB = sorted([
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI',
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NFLX',
    'AMD', 'INTC', 'QCOM', 'AVGO', 'TSM', 'MU', 'ARM', 'SMCI',
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA',
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT',
    'XOM', 'CVX', 'SLB', 'OXY', 'BA', 'CAT', 'GE',
    'BABA', 'JD', 'BIDU', 'PBR', 'VALE', 'ITUB',
    'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'XLE', 'XLF', 'ARKK', 'GLD', 'SLV', 'GDX'
])

# --- FUNCIONES TÉCNICAS ---

def calculate_heikin_ashi(df):
    """Calcula velas Heikin Ashi"""
    if df.empty: return df
    df_ha = df.copy()
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    # HA Open Vectorizado (Aproximación rápida para escaneo masivo)
    # Para backtesting preciso se usa iteración, para escaneo esto es suficiente
    df_ha['HA_Open'] = (df['Open'].shift(1) + df['Close'].shift(1)) / 2
    df_ha.iloc[0, df_ha.columns.get_loc('HA_Open')] = (df.iloc[0]['Open'] + df.iloc[0]['Close']) / 2
    
    # Determinar color
    df_ha['HA_Color'] = np.where(df_ha['HA_Close'] > df_ha['HA_Open'], 1, -1) # 1 Verde, -1 Rojo
    return df_ha

def calculate_adx(df, period=14):
    """Calcula el indicador ADX"""
    if len(df) < period + 1: return pd.Series(0, index=df.index)
    
    plus_dm = df['High'].diff()
    minus_dm = df['Low'].diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    
    tr1 = pd.DataFrame(df['High'] - df['Low'])
    tr2 = pd.DataFrame(abs(df['High'] - df['Close'].shift(1)))
    tr3 = pd.DataFrame(abs(df['Low'] - df['Close'].shift(1)))
    frames = [tr1, tr2, tr3]
    tr = pd.concat(frames, axis=1, join='inner').max(axis=1)
    atr = tr.rolling(period).mean()
    
    plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
    minus_di = 100 * (abs(minus_dm).ewm(alpha=1/period).mean() / atr)
    dx = (abs(plus_di - minus_di) / abs(plus_di + minus_di)) * 100
    adx = dx.rolling(period).mean()
    return adx

@st.cache_data(ttl=600)
def fetch_data(tickers):
    # Descargamos datos horarios para construir todo (Max 730 días)
    try:
        data = yf.download(tickers, period="6mo", interval="1h", group_by='ticker', progress=False, auto_adjust=True)
        return data
    except: return None

def analyze_market_structure(tickers):
    data = fetch_data(tickers)
    if data is None: 
        st.error("Error de conexión.")
        return pd.DataFrame()
        
    results = []
    prog = st.progress(0)
    
    for i, t in enumerate(tickers):
        try:
            # Obtener DF del ticker (Manejo MultiIndex)
            df_1h = data[t].dropna() if len(tickers) > 1 else data.dropna()
            if df_1h.empty: continue
            
            # --- 1. CONSTRUCCIÓN DE TEMPORALIDADES (Matrioskas) ---
            
            # A. SEMANAL (Macro)
            df_1w = df_1h.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
            ha_1w = calculate_heikin_ashi(df_1w)
            trend_1w = ha_1w['HA_Color'].iloc[-1] # 1 o -1
            
            # B. DIARIO (Estructural + Filtro ADX)
            df_1d = df_1h.resample('D').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
            ha_1d = calculate_heikin_ashi(df_1d)
            adx_1d = calculate_adx(df_1d).iloc[-1]
            trend_1d = ha_1d['HA_Color'].iloc[-1]
            
            # C. 4 HORAS (Intermedio)
            df_4h = df_1h.resample('4h').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
            ha_4h = calculate_heikin_ashi(df_4h)
            trend_4h = ha_4h['HA_Color'].iloc[-1]
            
            # D. 1 HORA (Gatillo + Filtro ADX)
            ha_1h = calculate_heikin_ashi(df_1h)
            adx_1h = calculate_adx(df_1h).iloc[-1]
            trend_1h = ha_1h['HA_Color'].iloc[-1]
            
            # --- 2. LÓGICA DE ESTRATEGIA (Checklist) ---
            
            signal = "ESPERAR" # Default
            reason = "Sin Alineación"
            
            # CONDICIONES LONG
            if trend_1w == 1: # 1. Macro OK
                if trend_1d == 1: # 2. Diario OK
                    if adx_1d > 20: # 3. Filtro Diario OK
                        if trend_4h == 1: # 4. Intermedio OK
                            if trend_1h == 1: # 5. Gatillo OK
                                if adx_1h > 25: # 6. Filtro Gatillo OK
                                    signal = "🔥 LONG (COMPRA)"
                                    reason = "Alineación Total + Fuerza"
                                else:
                                    signal = "⚠️ ALERTA LONG"
                                    reason = "Falta Fuerza 1H (ADX<25)"
                            else:
                                reason = "Esperando Gatillo 1H"
                        else:
                            reason = "4H Contra-Tendencia"
                    else:
                        reason = "Diario sin Fuerza (Rango)"
                else:
                    reason = "Diario Bajista"
            
            # CONDICIONES SHORT (Espejo)
            elif trend_1w == -1:
                if trend_1d == -1 and adx_1d > 20:
                    if trend_4h == -1 and trend_1h == -1 and adx_1h > 25:
                        signal = "❄️ SHORT (VENTA)"
                        reason = "Alineación Bajista Total"
            
            # Formateo Visual
            res = {
                "Ticker": t,
                "Señal": signal,
                "Razón": reason,
                "Precio": df_1h['Close'].iloc[-1],
                "1W": "🟢" if trend_1w==1 else "🔴",
                "1D": "🟢" if trend_1d==1 else "🔴",
                "ADX_D": f"{adx_1d:.0f}",
                "4H": "🟢" if trend_4h==1 else "🔴",
                "1H": "🟢" if trend_1h==1 else "🔴",
                "ADX_1H": f"{adx_1h:.0f}"
            }
            results.append(res)
            
        except Exception as e:
            continue
            
        prog.progress((i+1)/len(tickers))
        
    return pd.DataFrame(results)

# --- INTERFAZ ---
st.title("🛡️ SystemaTrader: Matrix Strategy (Golden Alignment)")
st.markdown("""
Esta herramienta aplica la estrategia de **"Las Matrioskas"**: busca alineación perfecta entre Semana, Día, 4H y 1H, filtrando mercados laterales con ADX.
*   **LONG:** Todo Verde + ADX Diario > 20 + ADX 1H > 25.
*   **SHORT:** Todo Rojo + ADX Diario > 20 + ADX 1H > 25.
""")

if st.button("🔎 ESCANEAR ESTRATEGIA"):
    df = analyze_market_structure(TICKERS_DB)
    
    if not df.empty:
        # Ordenar: Primero las señales activas
        df['sort_key'] = df['Señal'].apply(lambda x: 0 if "LONG" in x or "SHORT" in x else (1 if "ALERTA" in x else 2))
        df = df.sort_values('sort_key').drop('sort_key', axis=1)
        
        # Métricas
        longs = len(df[df['Señal'].str.contains("LONG")])
        shorts = len(df[df['Señal'].str.contains("SHORT")])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Oportunidades Long", longs)
        c2.metric("Oportunidades Short", shorts)
        
        # Tabla Principal
        st.dataframe(
            df,
            column_config={
                "Ticker": st.column_config.TextColumn("Activo", width="small"),
                "Señal": st.column_config.TextColumn("Estrategia", width="medium"),
                "Precio": st.column_config.NumberColumn(format="$%.2f"),
                "ADX_D": st.column_config.TextColumn("ADX D (Filtro >20)", width="small"),
                "ADX_1H": st.column_config.TextColumn("ADX 1H (Gatillo >25)", width="small"),
            },
            use_container_width=True,
            hide_index=True,
            height=800
        )
    else:
        st.warning("No se encontraron datos o hubo un error de conexión.")
