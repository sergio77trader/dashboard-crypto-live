import streamlit as st
import ccxt
import pandas as pd
import time
import numpy as np

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - OI Deep Dive")

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 16px; }
</style>
""", unsafe_allow_html=True)

# --- MOTOR DE DATOS (GATE.IO EXCLUSIVO) ---
# Usamos Gate.io porque es de los pocos que permite bajar HISTORIAL de OI gratis y sin bloqueo
@st.cache_resource
def get_exchange():
    return ccxt.gate({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}, # Futuros Perpetuos
        'timeout': 30000
    })

@st.cache_data(ttl=600)
def get_top_vol_pairs(limit=15):
    """Obtiene el Top de monedas por volumen en Gate"""
    try:
        exchange = get_exchange()
        tickers = exchange.fetch_tickers()
        valid = []
        
        for s in tickers:
            # Filtro: USDT y Swap (Perpetuo)
            if '_USDT' in s: # Gate usa guión bajo BTC_USDT
                valid.append({
                    'symbol': s,
                    'vol': tickers[s]['quoteVolume']
                })
        
        df = pd.DataFrame(valid).sort_values('vol', ascending=False).head(limit)
        return df['symbol'].tolist()
    except Exception as e:
        # Fallback de emergencia
        return ['BTC_USDT', 'ETH_USDT', 'SOL_USDT', 'ORDI_USDT', 'DOGE_USDT']

def fetch_oi_history(symbols):
    exchange = get_exchange()
    data_rows = []
    
    prog = st.progress(0, text="Extrayendo Historial de Open Interest...")
    total = len(symbols)
    
    for idx, symbol in enumerate(symbols):
        clean_name = symbol.replace('_', '/')
        prog.progress(idx/total, text=f"Analizando Flujo: {clean_name}...")
        
        row = {'Activo': clean_name}
        
        try:
            # 1. Obtenemos Historial de OI (Intervalo 1 Hora)
            # Pedimos 30 datos para cubrir las últimas 24h
            # Gate.io endpoint: fetch_open_interest_history
            oi_hist = exchange.fetch_open_interest_history(symbol, timeframe='1h', limit=30)
            
            if not oi_hist or len(oi_hist) < 24:
                # Si falla el historial, intentamos llenar con 0
                row.update({'OI 1H %': 0, 'OI 4H %': 0, 'OI 1D %': 0, 'OI Actual ($)': 0})
            else:
                # El formato suele ser: [{'timestamp':..., 'openInterestValue':...}, ...]
                # Convertimos a DataFrame para fácil manejo
                df = pd.DataFrame(oi_hist)
                
                # Aseguramos que la columna sea float
                # Gate suele devolver 'openInterestValue' (en USD) o 'openInterest' (en monedas)
                col_oi = 'openInterestValue' if 'openInterestValue' in df.columns else 'openInterestAmount'
                if col_oi not in df.columns: col_oi = 'openInterest' # Fallback
                
                # Limpieza de datos
                current_oi = float(df[col_oi].iloc[-1])
                
                # --- CÁLCULOS DELTAS ---
                # OI Actual
                row['OI Actual ($)'] = current_oi
                
                # OI Hace 1 Hora (Penúltimo dato)
                oi_1h = float(df[col_oi].iloc[-2])
                row['OI 1H %'] = ((current_oi - oi_1h) / oi_1h) * 100 if oi_1h else 0
                
                # OI Hace 4 Horas (Indice -5)
                if len(df) >= 5:
                    oi_4h = float(df[col_oi].iloc[-5])
                    row['OI 4H %'] = ((current_oi - oi_4h) / oi_4h) * 100 if oi_4h else 0
                else: row['OI 4H %'] = 0
                
                # OI Hace 24 Horas (Indice -25)
                if len(df) >= 25:
                    oi_24h = float(df[col_oi].iloc[-25])
                    row['OI 1D %'] = ((current_oi - oi_24h) / oi_24h) * 100 if oi_24h else 0
                else: row['OI 1D %'] = 0

            data_rows.append(row)
            
        except Exception:
            # Si falla un activo, ponemos ceros para no romper la tabla
            row.update({'OI 1H %': 0, 'OI 4H %': 0, 'OI 1D %': 0, 'OI Actual ($)': 0})
            data_rows.append(row)
        
        # Pausa para evitar Rate Limit de Gate
        time.sleep(0.2)
        
    prog.empty()
    return pd.DataFrame(data_rows)

# --- INTERFAZ ---
st.title("🧩 SystemaTrader: Open Interest Matrix")
st.markdown("### Flujo de Dinero Institucional (Gate.io Source)")

with st.sidebar:
    st.header("Configuración")
    LIMIT = st.slider("Cantidad de Activos:", 5, 20, 10)
    
    if st.button("🔄 ANALIZAR FLUJO", type="primary"):
        st.cache_data.clear()
        st.rerun()
    
    st.info("Nota: Usamos Gate.io porque permite descargar el historial de OI sin bloqueo de región.")

# --- EJECUCIÓN ---
try:
    with st.spinner("Conectando con Gate.io Futures..."):
        targets = get_top_vol_pairs(LIMIT)
        
    if not targets:
        st.error("Error de conexión.")
    else:
        df = fetch_oi_history(targets)
        
        if not df.empty:
            # SANITIZACIÓN FINAL
            df = df.fillna(0)
            
            # Formato Condicional (Colores)
            # Pandas Styler para colorear los % de cambio
            def color_change(val):
                if val > 5: return 'color: #00FF00; font-weight: bold' # Verde fuerte si sube mucho
                elif val > 0: return 'color: #90EE90' # Verde suave
                elif val < -5: return 'color: #FF4500; font-weight: bold' # Rojo fuerte si baja mucho
                elif val < 0: return 'color: #FA8072' # Rojo suave
                return 'color: white'

            # TABLA
            st.dataframe(
                df.style.applymap(color_change, subset=['OI 1H %', 'OI 4H %', 'OI 1D %']),
                column_config={
                    "Activo": st.column_config.TextColumn("Ticker", width="small"),
                    "OI Actual ($)": st.column_config.ProgressColumn(
                        "Open Interest Total", 
                        format="$%.0f", 
                        min_value=0, 
                        max_value=float(df['OI Actual ($)'].max())
                    ),
                    "OI 1H %": st.column_config.NumberColumn("Cambio 1H", format="%.2f%%"),
                    "OI 4H %": st.column_config.NumberColumn("Cambio 4H", format="%.2f%%"),
                    "OI 1D %": st.column_config.NumberColumn("Cambio 24H", format="%.2f%%"),
                },
                use_container_width=True,
                height=600
            )
            
            st.caption("""
            **Interpretación SystemaTrader:**
            *   **OI sube + Precio sube:** Tendencia Saludable (Entra dinero).
            *   **OI sube + Precio baja:** Short Build-up (Acumulación de ventas).
            *   **OI baja drásticamente:** Liquidaciones (Short/Long Squeeze).
            """)
            
        else:
            st.warning("No se obtuvieron datos.")

except Exception as e:
    st.error(f"Error crítico: {e}")
