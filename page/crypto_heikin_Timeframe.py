import streamlit as st
import ccxt
import pandas as pd
import time

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Crypto HA Scanner")

# --- MAPEO DE TEMPORALIDADES ---
TIMEFRAMES = {
    '1H': '1h',
    '4H': '4h',
    'Diario': '1d',
    'Semanal': '1w'
}

# --- FUNCIONES DE CÁLCULO ---
def calculate_heikin_ashi(df):
    """Calcula HA con precisión matemática"""
    if df.empty: return df
    
    df_ha = df.copy()
    
    # HA Close
    df_ha['HA_Close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    
    # HA Open (Requiere iteración para precisión)
    df_ha['HA_Open'] = 0.0
    # Inicialización del primer valor
    df_ha.iat[0, df_ha.columns.get_loc('HA_Open')] = (df.iloc[0]['open'] + df.iloc[0]['close']) / 2
    
    # Optimizamos el bucle usando numpy values para velocidad
    vals = df_ha.values
    idx_open = df_ha.columns.get_loc('HA_Open')
    idx_close = df_ha.columns.get_loc('HA_Close')
    
    for i in range(1, len(vals)):
        # HA_Open = (Prev_Open + Prev_Close) / 2
        vals[i, idx_open] = (vals[i-1, idx_open] + vals[i-1, idx_close]) / 2
        
    df_ha['HA_Open'] = vals[:, idx_open]
    return df_ha

@st.cache_data(ttl=3600)
def get_all_perp_pairs():
    """
    Obtiene contratos PERPETUOS de Binance Futures USDT-M.
    Incluye manejo de error por Geo-Bloqueo.
    """
    try:
        # INICIALIZACIÓN: MODO FUTUROS
        exchange = ccxt.binance({
            'options': {'defaultType': 'future'},
            'timeout': 10000,
            'enableRateLimit': True
        })
        
        markets = exchange.load_markets()
        
        # Lista negra de stablecoins y pares raros
        blacklist = ['USDC/USDT', 'BUSD/USDT', 'TUSD/USDT', 'USDP/USDT']
        
        valid_pairs = []
        
        for symbol in markets:
            market = markets[symbol]
            # FILTRO: USDT + SWAP (Perpetuo) + ACTIVO
            if market['quote'] == 'USDT' and market['type'] == 'swap' and market['active']:
                if symbol not in blacklist:
                    valid_pairs.append(symbol)
        
        # Intentamos ordenar por volumen (Top Liquidez)
        try:
            # Pedimos tickers de todos para ordenar (puede ser pesado, si falla, devolvemos sin orden)
            # Para optimizar en nube, limitamos la carga si son muchos
            return valid_pairs
        except:
            return valid_pairs

    except Exception as e:
        st.error(f"Error de conexión con Exchange: {e}")
        return []

def get_market_scan(symbols_list, max_limit):
    # Instancia
    exchange = ccxt.binance({'options': {'defaultType': 'future'}, 'enableRateLimit': True})
    
    results = []
    # Barra de progreso
    prog_bar = st.progress(0, text="Iniciando escaneo fractal...")
    
    # Limitamos la lista a la cantidad elegida
    target_list = symbols_list[:max_limit]
    total = len(target_list)
    
    for idx, symbol in enumerate(target_list):
        prog_bar.progress((idx + 1) / total, text=f"Analizando {symbol}...")
        
        row_data = {'Activo': symbol}
        greens = 0
        valid_candle = True
        
        for tf_label, tf_code in TIMEFRAMES.items():
            try:
                # Bajamos velas suficientes para HA
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf_code, limit=50)
                
                if not ohlcv:
                    row_data[tf_label] = "N/A"
                    valid_candle = False
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
                df_ha = calculate_heikin_ashi(df)
                last = df_ha.iloc[-1]
                
                # Determinación de tendencia HA
                if last['HA_Close'] >= last['HA_Open']:
                    row_data[tf_label] = "🟢 ALCISTA"
                    greens += 1
                else:
                    row_data[tf_label] = "🔴 BAJISTA"
                    
            except Exception as e:
                # Si falla por bloqueo (451), detenemos todo
                if '451' in str(e) or 'Restricted' in str(e):
                    st.error("🚨 BLOQUEO DE IP DETECTADO: Binance no permite acceso desde este servidor (EEUU).")
                    st.info("Solución: Cambiar el código para usar BYBIT o GATE.IO.")
                    st.stop()
                
                row_data[tf_label] = "⚠️ Error"
                valid_candle = False
        
        if valid_candle:
            # Diagnóstico SystemaTrader
            if greens == 4: row_data['Diagnóstico'] = "🔥 FULL ALCISTA"
            elif greens == 0: row_data['Diagnóstico'] = "❄️ FULL BAJISTA"
            elif greens == 3: row_data['Diagnóstico'] = "✅ ALCISTA FUERTE"
            elif greens == 1: row_data['Diagnóstico'] = "🔻 BAJISTA FUERTE"
            else: row_data['Diagnóstico'] = "⚖️ MIXTO"
            
            results.append(row_data)
        
        # Pausa pequeña para no saturar rate limit
        time.sleep(0.1) 
        
    prog_bar.empty()
    return pd.DataFrame(results)

# --- INTERFAZ ---
st.title("⚡ SystemaTrader: Cripto Trend (Binance)")
st.markdown("Monitor de Tendencia Heikin Ashi para **Futuros Perpetuos**.")

# Sidebar
with st.sidebar:
    st.header("Configuración")
    
    if st.button("🔄 Cargar Lista de Pares"):
        st.cache_data.clear()
    
    # Carga de símbolos
    all_symbols = get_all_perp_pairs()
    
    if all_symbols:
        st.success(f"Disponibles: {len(all_symbols)}")
        # Selección de cantidad para no tardar años
        scan_limit = st.slider("Escanear Top X activos:", 5, 50, 15)
        
        # Filtro manual opcional
        manual_select = st.multiselect("O filtrar específicos:", all_symbols, default=[])
        
        start_btn = st.button("🚀 INICIAR ESCANEO", type="primary")
    else:
        st.warning("No se pudieron cargar pares. Posible bloqueo de IP.")
        start_btn = False

# --- RESULTADOS ---
if start_btn:
    # Definir lista objetivo
    target_list = manual_select if manual_select else all_symbols
    
    with st.spinner("Analizando Estructura de Mercado..."):
        df_results = get_market_scan(target_list, scan_limit)
        
        if not df_results.empty:
            # Ordenar por diagnóstico
            sort_order = {"🔥 FULL ALCISTA": 0, "❄️ FULL BAJISTA": 1, "✅ ALCISTA FUERTE": 2, "🔻 BAJISTA FUERTE": 3, "⚖️ MIXTO": 4}
            # Manejo seguro de mapeo
            df_results['sort_val'] = df_results['Diagnóstico'].map(sort_order).fillna(5)
            df_results = df_results.sort_values('sort_val').drop('sort_val', axis=1)
            
            # KPI Cards
            bulls = len(df_results[df_results['Diagnóstico'] == "🔥 FULL ALCISTA"])
            bears = len(df_results[df_results['Diagnóstico'] == "❄️ FULL BAJISTA"])
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Analizados", len(df_results))
            k2.metric("Oportunidades Long", bulls)
            k3.metric("Oportunidades Short", bears)

            # Filtros Visuales
            f_ver = st.radio("Filtro:", ["Ver Todo", "🔥 Solo Full Bull", "❄️ Solo Full Bear"], horizontal=True)
            
            if f_ver == "🔥 Solo Full Bull":
                df_show = df_results[df_results['Diagnóstico'] == "🔥 FULL ALCISTA"]
            elif f_ver == "❄️ Solo Full Bear":
                df_show = df_results[df_results['Diagnóstico'] == "❄️ FULL BAJISTA"]
            else:
                df_show = df_results
            
            st.dataframe(
                df_show,
                column_config={
                    "Activo": st.column_config.TextColumn("Contrato", width="medium"),
                    "1H": st.column_config.TextColumn("1H", width="small"),
                    "4H": st.column_config.TextColumn("4H", width="small"),
                    "Diario": st.column_config.TextColumn("1D", width="small"),
                    "Semanal": st.column_config.TextColumn("1W", width="small"),
                    "Diagnóstico": st.column_config.TextColumn("Tendencia", width="medium"),
                },
                use_container_width=True,
                hide_index=True,
                height=600
            )
            
            st.caption("Nota: Datos extraídos de Binance Futures en tiempo real.")
        else:
            st.error("El escaneo no arrojó resultados válidos.")
else:
    if all_symbols:
        st.info("Configura los parámetros y presiona INICIAR.")
