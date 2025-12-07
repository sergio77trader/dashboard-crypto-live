import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import time

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Binance Pro Dash")

st.markdown("""
<style>
    [data-testid="stMetricValue"] {
        font-size: 18px;
    }
</style>
""", unsafe_allow_html=True)

# --- FUNCIONES DE CÁLCULO ---
def get_rsi(df, length=14):
    """Calcula RSI usando pandas_ta"""
    if df.empty: return 50
    try:
        rsi_series = df.ta.rsi(length=length)
        return rsi_series.iloc[-1]
    except: return 50

def get_change(current, prev):
    """Calcula % de cambio"""
    if prev == 0: return 0
    return ((current - prev) / prev) * 100

@st.cache_data(ttl=600) # Cache de 10 min para la lista de monedas
def get_top_liquid_pairs():
    """Obtiene el Top 20 pares por volumen en Binance Futures"""
    try:
        exchange = ccxt.binance({'options': {'defaultType': 'future'}})
        markets = exchange.load_markets()
        tickers = exchange.fetch_tickers()
        
        # Filtramos USDT perp
        valid = []
        for s in tickers:
            if '/USDT' in s and ':' in s: # Formato futuro BTC/USDT:USDT
                valid.append({
                    'symbol': s,
                    'volume': tickers[s]['quoteVolume']
                })
        
        # Ordenar y tomar Top 20
        df = pd.DataFrame(valid)
        df = df.sort_values('volume', ascending=False).head(20)
        return df['symbol'].tolist()
    except:
        return ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'XRP/USDT:USDT']

def fetch_market_data(symbols):
    exchange = ccxt.binance({
        'options': {'defaultType': 'future'},
        'enableRateLimit': True
    })
    
    data_rows = []
    total = len(symbols)
    bar = st.progress(0, text="Descargando Datos Institucionales...")
    
    for i, symbol in enumerate(symbols):
        bar.progress((i)/total, text=f"Procesando {symbol}...")
        
        try:
            # 1. Velas para RSI y Cambios (15m, 1h, 4h)
            # Optimizacion: Bajamos velas de 15m (96 velas = 24h) y de ahí sacamos todo
            # Para 4h y 1d necesitamos más historia, así que haremos llamadas especificas
            
            # RSI 15m
            ohlcv_15m = exchange.fetch_ohlcv(symbol, '15m', limit=30)
            df_15m = pd.DataFrame(ohlcv_15m, columns=['time','open','high','low','close','vol'])
            rsi_15m = get_rsi(df_15m)
            
            # RSI 1h y Cambios 1H
            ohlcv_1h = exchange.fetch_ohlcv(symbol, '1h', limit=30)
            df_1h = pd.DataFrame(ohlcv_1h, columns=['time','open','high','low','close','vol'])
            rsi_1h = get_rsi(df_1h)
            price_now = df_1h['close'].iloc[-1]
            price_1h_ago = df_1h['open'].iloc[-1] # Open de la vela actual aprox
            
            # RSI 4h y Cambios 4H
            ohlcv_4h = exchange.fetch_ohlcv(symbol, '4h', limit=30)
            df_4h = pd.DataFrame(ohlcv_4h, columns=['time','open','high','low','close','vol'])
            rsi_4h = get_rsi(df_4h)
            
            # Datos Generales (Funding, OI, 24h change)
            ticker = exchange.fetch_ticker(symbol)
            funding = exchange.fetch_funding_rate(symbol)
            
            # Open Interest (A veces falla, try/except interno)
            oi_val = 0
            try:
                oi_data = exchange.fetch_open_interest(symbol)
                oi_val = float(oi_data['openInterestAmount']) # En monedas
                oi_usd = oi_val * price_now
            except:
                oi_usd = 0

            # Cálculos de Variación de Precio
            chg_1h = ticker['percentage'] # Binance a veces da esto raro, calculamos manual mejor
            chg_24h = ticker['percentage']
            
            # Construcción de la Fila
            row = {
                'Symbol': symbol.split(':')[0], # Limpiar nombre
                'Precio': price_now,
                'Chg 24h': chg_24h / 100 if abs(chg_24h) > 1 else chg_24h, # Ajuste formato
                'Volumen 24h': ticker['quoteVolume'],
                'RSI 15m': rsi_15m,
                'RSI 1H': rsi_1h,
                'RSI 4H': rsi_4h,
                'Funding Rate': funding['fundingRate'] * 100, # En porcentaje
                'Open Interest ($)': oi_usd
            }
            data_rows.append(row)
            
        except Exception:
            continue
            
    bar.empty()
    return pd.DataFrame(data_rows)

# --- INTERFAZ ---
st.title("💠 SystemaTrader: Binance Pro Dashboard")
st.markdown("### Datos en tiempo real | Futuros USDT-M")

# Botón de recarga
if st.button("🔄 ACTUALIZAR DATOS AHORA", type="primary"):
    st.cache_data.clear()

# Lógica Principal
top_symbols = get_top_liquid_pairs()
df = fetch_market_data(top_symbols)

if not df.empty:
    # --- ESTILIZADO DEL DATAFRAME ---
    # Esto es lo que hace que se vea "Pro" como en las capturas
    
    st.dataframe(
        df,
        column_config={
            "Symbol": st.column_config.TextColumn("Activo", width="small"),
            "Precio": st.column_config.NumberColumn("Precio", format="$%.4f"),
            "Chg 24h": st.column_config.NumberColumn(
                "Cambio 24h", 
                format="%.2f%%", 
                help="Variación en las últimas 24 horas"
            ),
            "Volumen 24h": st.column_config.ProgressColumn(
                "Volumen (24h)",
                format="$%.0f",
                min_value=0,
                max_value=df['Volumen 24h'].max()
            ),
            "RSI 15m": st.column_config.NumberColumn("RSI 15m", format="%.1f"),
            "RSI 1H": st.column_config.NumberColumn("RSI 1H", format="%.1f"),
            "RSI 4H": st.column_config.NumberColumn("RSI 4H", format="%.1f"),
            "Funding Rate": st.column_config.NumberColumn(
                "Funding Rate", 
                format="%.4f%%",
                help="Positivo: Longs pagan a Shorts. Negativo: Shorts pagan a Longs."
            ),
            "Open Interest ($)": st.column_config.NumberColumn(
                "Open Interest ($)", 
                format="$%.0f",
                help="Dinero total en contratos abiertos"
            )
        },
        use_container_width=True,
        hide_index=True,
        height=800
    )
    
    # --- LEYENDA TÁCTICA ---
    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("**RSI Táctico:**\n- >70: Sobrecompra (Posible Short)\n- <30: Sobreventa (Posible Long)\n- 50: Neutral")
    with c2:
        st.warning("**Funding Rate:**\n- Muy Positivo (>0.01%): Peligro Long Squeeze\n- Negativo: Posible Short Squeeze")
    with c3:
        st.success("**Open Interest:**\n- Subiendo + Precio Subiendo: Tendencia Fuerte\n- Bajando + Precio Bajando: Liquidaciones")

else:
    st.error("No se pudieron cargar los datos. Verifica la conexión con Binance.")
