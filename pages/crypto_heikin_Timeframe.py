import streamlit as st
import ccxt
import pandas as pd
import time

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Multi-Exchange Matrix")

# --- GESTIÓN DE MEMORIA ---
if 'crypto_results' not in st.session_state:
    st.session_state['crypto_results'] = []

# --- MAPEO TEMPORAL ---
TIMEFRAMES = {
    '1H': '1h',
    '4H': '4h',
    'Diario': '1d',
    'Semanal': '1w',
    'Mensual': '1M'
}

# --- MOTOR HEIKIN ASHI ---
def calculate_heikin_ashi(df):
    if df is None or df.empty or len(df) < 2: 
        return pd.DataFrame() 
    
    df_ha = df.copy()
    # HA Close
    df_ha['HA_Close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    # HA Open
    df_ha['HA_Open'] = 0.0
    df_ha.iat[0, df_ha.columns.get_loc('HA_Open')] = (df.iloc[0]['open'] + df.iloc[0]['close']) / 2
    
    vals = df_ha.values
    idx_open = df_ha.columns.get_loc('HA_Open')
    idx_close = df_ha.columns.get_loc('HA_Close')
    
    for i in range(1, len(vals)):
        vals[i, idx_open] = (vals[i-1, idx_open] + vals[i-1, idx_close]) / 2
        
    df_ha['HA_Open'] = vals[:, idx_open]
    return df_ha

# --- CONECTORES DE EXCHANGES ---
def get_exchange_instance(name):
    """Fábrica de conexiones"""
    options = {'enableRateLimit': True, 'timeout': 30000}
    
    if name == 'KuCoin Futures':
        return ccxt.kucoinfutures(options)
    elif name == 'Gate.io Futures':
        return ccxt.gate(dict(options, **{'options': {'defaultType': 'swap'}}))
    elif name == 'MEXC Futures':
        return ccxt.mexc(dict(options, **{'options': {'defaultType': 'swap'}}))
    return None

@st.cache_data(ttl=3600)
def get_market_pairs(exchange_name):
    """Obtiene pares USDT según el exchange elegido"""
    try:
        exchange = get_exchange_instance(exchange_name)
        markets = exchange.load_markets()
        valid = []
        
        for s in markets:
            market = markets[s]
            # Lógica universal para detectar Perpetuos USDT
            is_usdt = market['quote'] == 'USDT'
            is_active = market['active']
            is_swap = market.get('swap', False) or market.get('linear', False) or market['type'] == 'swap'
            
            if is_usdt and is_active and is_swap:
                valid.append(s)
        
        # Orden prioritario (Majors)
        majors = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'BTC/USDT:USDT', 'ETH/USDT:USDT']
        # Ajuste de formato para Gate/MEXC que a veces usan _ o :
        
        return sorted(valid)
    except Exception as e:
        st.error(f"Error conectando a {exchange_name}: {e}")
        return []

def scan_batch(targets, exchange_name):
    exchange = get_exchange_instance(exchange_name)
    results = []
    
    prog = st.progress(0, text=f"Escaneando en {exchange_name}...")
    total = len(targets)
    
    for idx, symbol in enumerate(targets):
        prog.progress((idx)/total, text=f"Analizando: {symbol}")
        
        # Limpieza visual del nombre
        clean_name = symbol.split(':')[0].replace('_', '/')
        row = {'Activo': clean_name, 'Symbol_Raw': symbol}
        
        greens = 0
        valid_timeframes = 0
        error_msg = ""
        
        for tf_label, tf_code in TIMEFRAMES.items():
            try:
                # 12 velas para mensual, 30 para el resto
                limit = 12 if tf_code == '1M' else 30
                
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf_code, limit=limit)
                
                # Tolerancia mínima: 2 velas
                if not ohlcv or len(ohlcv) < 2:
                    row[tf_label] = "⚪"
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
                df_ha = calculate_heikin_ashi(df)
                
                last = df_ha.iloc[-1]
                
                if last['HA_Close'] >= last['HA_Open']:
                    row[tf_label] = "🟢"
                    greens += 1
                else:
                    row[tf_label] = "🔴"
                
                valid_timeframes += 1
                
            except Exception as e:
                row[tf_label] = "⚠️"
                error_msg = str(e)
        
        # Puntuación
        if valid_timeframes > 0:
            ratio = greens / valid_timeframes
            if ratio == 1.0: row['Diagnóstico'] = "🔥 FULL ALCISTA"
            elif ratio == 0.0: row['Diagnóstico'] = "❄️ FULL BAJISTA"
            elif ratio >= 0.75: row['Diagnóstico'] = "✅ ALCISTA FUERTE"
            elif ratio <= 0.25: row['Diagnóstico'] = "🔻 BAJISTA FUERTE"
            else: row['Diagnóstico'] = "⚖️ MIXTO"
            
            results.append(row)
        else:
            # Si falló todo, guardamos el error para debug (opcional)
            pass
            
        time.sleep(0.2) # Pausa táctica
        
    prog.empty()
    return pd.DataFrame(results)

# --- UI ---
st.title("⚡ SystemaTrader: Multi-Exchange Matrix")

with st.sidebar:
    st.header("1. Fuente de Datos")
    # SELECTOR DE MOTOR
    SOURCE = st.selectbox("Exchange:", ["Gate.io Futures", "MEXC Futures", "KuCoin Futures"])
    
    if st.button("🔄 Cargar Mercados"):
        st.cache_data.clear()
        
    # Carga dinámica según selección
    with st.spinner(f"Conectando a {SOURCE}..."):
        all_symbols = get_market_pairs(SOURCE)
        
    if all_symbols:
        st.success(f"Online: {len(all_symbols)} activos")
        st.divider()
        
        st.header("2. Escaneo por Lotes")
        BATCH_SIZE = st.selectbox("Tamaño Lote:", [10, 20, 50], index=1)
        batches = [all_symbols[i:i + BATCH_SIZE] for i in range(0, len(all_symbols), BATCH_SIZE)]
        
        batch_labels = [f"Lote {i+1} ({b[0]})" for i, b in enumerate(batches)]
        sel_batch = st.selectbox("Elegir:", range(len(batches)), format_func=lambda x: batch_labels[x])
        
        accumulate = st.checkbox("Acumular", value=True)
        
        if st.button("🚀 ESCANEAR", type="primary"):
            target = batches[sel_batch]
            with st.spinner("Procesando..."):
                new_df = scan_batch(target, SOURCE)
                
                if not new_df.empty:
                    new_data = new_df.to_dict('records')
                    if accumulate:
                        existing = {x['Activo'] for x in st.session_state['crypto_results']}
                        for item in new_data:
                            if item['Activo'] not in existing:
                                st.session_state['crypto_results'].append(item)
                    else:
                        st.session_state['crypto_results'] = new_data
                    st.success(f"Hecho. {len(new_df)} procesados.")
                else:
                    st.error("Error: No llegaron datos. Intenta cambiar de Exchange.")
                    
        if st.button("Limpiar"):
            st.session_state['crypto_results'] = []
            st.rerun()
    else:
        st.error(f"No se pudo conectar a {SOURCE}. Probablemente bloqueo de IP.")

# --- TABLA ---
if st.session_state['crypto_results']:
    df = pd.DataFrame(st.session_state['crypto_results'])
    
    sort_map = {"🔥 FULL ALCISTA": 0, "❄️ FULL BAJISTA": 1, "✅ ALCISTA FUERTE": 2, "🔻 BAJISTA FUERTE": 3, "⚖️ MIXTO": 4}
    df['sort'] = df['Diagnóstico'].map(sort_map).fillna(5)
    df = df.sort_values('sort').drop('sort', axis=1)
    
    f_mode = st.radio("Ver:", ["Todos", "🔥 Oportunidades"], horizontal=True)
    if f_mode == "🔥 Oportunidades":
        df = df[df['Diagnóstico'].isin(["🔥 FULL ALCISTA", "❄️ FULL BAJISTA"])]

    st.dataframe(
        df,
        column_config={
            "Activo": st.column_config.TextColumn("Ticker", width="small"),
            "1H": st.column_config.TextColumn("1H", width="small"),
            "4H": st.column_config.TextColumn("4H", width="small"),
            "Diario": st.column_config.TextColumn("1D", width="small"),
            "Semanal": st.column_config.TextColumn("1W", width="small"),
            "Mensual": st.column_config.TextColumn("1M", width="small"),
            "Diagnóstico": st.column_config.TextColumn("Estructura", width="medium"),
            "Symbol_Raw": None
        },
        use_container_width=True,
        hide_index=True,
        height=600
    )
    st.caption(f"Fuente de datos: {SOURCE} | Servidor: Cloud")
else:
    st.info("Selecciona un Exchange y comienza a escanear lotes.")
