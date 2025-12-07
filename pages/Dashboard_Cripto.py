import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import time

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Pro Dashboard")

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 18px; }
    .stProgress > div > div > div > div { background-color: #00CC96; }
</style>
""", unsafe_allow_html=True)

# --- FUNCIONES TÉCNICAS ---
def get_rsi(df, length=14):
    """Calcula RSI seguro"""
    if df.empty or len(df) < length: return 50
    try:
        rsi_series = df.ta.rsi(length=length)
        if rsi_series is None or rsi_series.empty: return 50
        return rsi_series.iloc[-1]
    except: return 50

# --- FACTORY DE CONEXIÓN ---
def get_exchange(name):
    """Genera la conexión según el exchange elegido"""
    opts = {'enableRateLimit': True, 'timeout': 30000}
    if name == 'Gate.io':
        return ccxt.gate(dict(opts, **{'options': {'defaultType': 'swap'}}))
    elif name == 'MEXC':
        return ccxt.mexc(dict(opts, **{'options': {'defaultType': 'swap'}}))
    elif name == 'KuCoin':
        return ccxt.kucoinfutures(opts)
    return None

@st.cache_data(ttl=300)
def get_top_pairs(exchange_name):
    """Obtiene Top 15 pares por volumen del exchange seleccionado"""
    try:
        exchange = get_exchange(exchange_name)
        markets = exchange.load_markets()
        
        # Obtener tickers para ver volumen
        tickers = exchange.fetch_tickers()
        valid = []
        
        for s in tickers:
            # Filtro universal de perpetuos USDT
            is_usdt = '/USDT' in s
            # Gate/MEXC usan 'swap' o 'linear', Kucoin usa otra logica.
            # CCXT suele normalizar, buscamos pares USDT con volumen
            if is_usdt and tickers[s]['quoteVolume'] is not None:
                valid.append({
                    'symbol': s,
                    'volume': tickers[s]['quoteVolume']
                })
        
        # Ordenar y Top 15
        df = pd.DataFrame(valid)
        df = df.sort_values('volume', ascending=False).head(15)
        return df['symbol'].tolist()
    except Exception as e:
        # Fallback si falla la lista
        return ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'XRP/USDT:USDT']

def fetch_data(symbols, exchange_name):
    exchange = get_exchange(exchange_name)
    data_rows = []
    total = len(symbols)
    bar = st.progress(0, text=f"Leyendo datos de {exchange_name}...")
    
    for i, symbol in enumerate(symbols):
        # Nombre limpio para mostrar
        display = symbol.split(':')[0]
        bar.progress((i)/total, text=f"Analizando {display}...")
        
        try:
            # 1. Velas para RSI (15m, 1h, 4h)
            # Optimizacion: Pedimos pocas velas
            k_15m = exchange.fetch_ohlcv(symbol, '15m', limit=30)
            rsi_15m = get_rsi(pd.DataFrame(k_15m, columns=['t','o','h','l','c','v']))
            
            k_1h = exchange.fetch_ohlcv(symbol, '1h', limit=30)
            df_1h = pd.DataFrame(k_1h, columns=['t','o','h','l','c','v'])
            rsi_1h = get_rsi(df_1h)
            price_now = df_1h['c'].iloc[-1]
            
            k_4h = exchange.fetch_ohlcv(symbol, '4h', limit=30)
            rsi_4h = get_rsi(pd.DataFrame(k_4h, columns=['t','o','h','l','c','v']))
            
            # 2. Datos Financieros
            funding = 0.0
            try:
                f_data = exchange.fetch_funding_rate(symbol)
                funding = f_data['fundingRate'] * 100
            except: pass
            
            # 3. Open Interest
            oi_usd = 0
            try:
                oi = exchange.fetch_open_interest(symbol)
                # Intentar buscar valor en USD directo
                if 'openInterestValue' in oi:
                    oi_usd = float(oi['openInterestValue'])
                # Si no, convertir contratos a USD
                elif 'openInterestAmount' in oi:
                     oi_usd = float(oi['openInterestAmount']) * price_now
                else:
                     oi_usd = float(oi.get('openInterest', 0)) * price_now
            except: pass

            # 4. Variación 24h
            try:
                tick = exchange.fetch_ticker(symbol)
                chg = tick['percentage'] if tick['percentage'] else 0
                # Normalizar si viene en decimal o entero
                if abs(chg) < 1: chg = chg * 100 # Si viene 0.05 es 5%
            except: chg = 0

            row = {
                'Symbol': display,
                'Precio': price_now,
                'Chg 24h': chg / 100, # Streamlit lo multiplica por 100 si es formato %
                'Volumen': tick.get('quoteVolume', 0),
                'RSI 15m': rsi_15m,
                'RSI 1H': rsi_1h,
                'RSI 4H': rsi_4h,
                'Funding': funding / 100, # Formato %
                'OI ($)': oi_usd
            }
            data_rows.append(row)
            
        except Exception:
            continue
            
    bar.empty()
    return pd.DataFrame(data_rows)

# --- INTERFAZ ---
st.title("💠 SystemaTrader: Pro Dashboard")

# BARRA LATERAL: SELECTOR DE MOTOR
with st.sidebar:
    st.header("Fuente de Datos")
    # Gate.io suele ser el más robusto para IPs de Cloud
    SOURCE = st.selectbox("Seleccionar Exchange:", ["Gate.io", "MEXC", "KuCoin"])
    
    if st.button("🔄 RECARGAR AHORA", type="primary"):
        st.cache_data.clear()
        st.rerun()

    st.info(f"Conectado a: **{SOURCE} Futures**")
    st.caption("Si falla la carga, cambia de Exchange en este menú.")

# EJECUCIÓN PRINCIPAL
try:
    with st.spinner(f"Estableciendo enlace satelital con {SOURCE}..."):
        top_symbols = get_top_pairs(SOURCE)
        
    if not top_symbols:
        st.error(f"Error crítico conectando a {SOURCE}. Prueba otro Exchange.")
    else:
        df = fetch_data(top_symbols, SOURCE)

        if not df.empty:
            # TABLA PRINCIPAL
            st.dataframe(
                df,
                column_config={
                    "Symbol": st.column_config.TextColumn("Activo", width="small"),
                    "Precio": st.column_config.NumberColumn("Precio", format="$%.4f"),
                    "Chg 24h": st.column_config.NumberColumn("24h %", format="%.2f%%"),
                    "Volumen": st.column_config.ProgressColumn("Volumen 24h", format="$%.0f", min_value=0, max_value=df['Volumen'].max()),
                    "RSI 15m": st.column_config.NumberColumn("RSI 15m", format="%.0f"),
                    "RSI 1H": st.column_config.NumberColumn("RSI 1H", format="%.0f"),
                    "RSI 4H": st.column_config.NumberColumn("RSI 4H", format="%.0f"),
                    "Funding": st.column_config.NumberColumn("Funding", format="%.4f%%"),
                    "OI ($)": st.column_config.NumberColumn("Open Int. ($)", format="$%.0f", help="Dinero en contratos abiertos")
                },
                use_container_width=True,
                hide_index=True,
                height=750
            )
            
            # LEYENDA
            c1, c2, c3 = st.columns(3)
            c1.info("💡 **RSI:** >70 (Sobrecompra) | <30 (Sobreventa)")
            c2.warning("⚡ **Funding:** Negativo = Posible Short Squeeze")
            c3.success(f"📡 Datos en vivo de **{SOURCE}**")
            
        else:
            st.error("No llegaron datos. Intenta recargar o cambiar de Exchange.")

except Exception as e:
    st.error(f"Error del Sistema: {e}")
