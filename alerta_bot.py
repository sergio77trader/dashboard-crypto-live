import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime

# --- CREDENCIALES ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- CONFIGURACIÓN ---
# Analizamos Mensual, Semanal y Diario
TIMEFRAMES = [
    ("1mo", "MENSUAL", "max"),
    ("1wk", "SEMANAL", "10y"),
    ("1d", "DIARIO", "5y")
]

ADX_TH = 20
ADX_LEN = 14

# --- BASE DE DATOS EXACTA DE TU SCRIPT ---
TICKERS = sorted([
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX', 'TX',
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NFLX',
    'CRM', 'ORCL', 'ADBE', 'IBM', 'CSCO', 'PLTR', 'SNOW', 'SHOP', 'SPOT', 'UBER', 'ABNB', 'SAP', 'INTU', 'NOW',
    'AMD', 'INTC', 'QCOM', 'AVGO', 'TXN', 'MU', 'ADI', 'AMAT', 'ARM', 'SMCI', 'TSM', 'ASML', 'LRCX', 'HPQ', 'DELL',
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B', 'PYPL', 'SQ', 'COIN', 'BLK', 'USB', 'NU',
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'TGT', 'HD', 'LOW', 'PG', 'CL', 'MO', 'PM', 'KMB', 'EL',
    'JNJ', 'PFE', 'MRK', 'LLY', 'ABBV', 'UNH', 'BMY', 'AMGN', 'GILD', 'AZN', 'NVO', 'NVS', 'CVS',
    'BA', 'CAT', 'DE', 'GE', 'MMM', 'LMT', 'RTX', 'HON', 'UNP', 'UPS', 'FDX', 'LUV', 'DAL',
    'F', 'GM', 'TM', 'HMC', 'STLA', 'RACE',
    'XOM', 'CVX', 'SLB', 'OXY', 'HAL', 'BP', 'SHEL', 'TTE', 'PBR', 'VLO',
    'VZ', 'T', 'TMUS', 'VOD',
    'BABA', 'JD', 'BIDU', 'NIO', 'PDD', 'TCEHY', 'TCOM', 'BEKE', 'XPEV', 'LI', 'SONY',
    'VALE', 'ITUB', 'BBD', 'ERJ', 'ABEV', 'GGB', 'SID', 'NBR',
    'GOLD', 'NEM', 'PAAS', 'FCX', 'SCCO', 'RIO', 'BHP', 'ALB', 'SQM',
    'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EWZ', 'FXI', 'XLE', 'XLF', 'XLK', 'XLV', 'XLI', 'XLP', 'XLU', 'XLY', 'ARKK', 'SMH', 'TAN', 'GLD', 'SLV', 'GDX'
])

def send_message(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    # Manejo de límites de Telegram (4096 caracteres)
    if len(msg) > 4000:
        parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
        for part in parts:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": CHAT_ID, "text": part, "parse_mode": "Markdown"})
            time.sleep(1)
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

# --- CÁLCULOS MATEMÁTICOS (Nativos y Robustos) ---
def calculate_heikin_ashi(df):
    df_ha = df.copy()
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    # Cálculo iterativo para coincidir con TV
    ha_open = [df['Open'].iloc[0]]
    for i in range(1, len(df)):
        ha_open.append((ha_open[-1] + df_ha['HA_Close'].iloc[i-1]) / 2)
    df_ha['HA_Open'] = ha_open
    
    df_ha['Color'] = np.where(df_ha['HA_Close'] > df_ha['HA_Open'], 1, -1)
    return df_ha

def calculate_adx(df, period=14):
    df = df.copy()
    df['H-L'] = df['High'] - df['Low']
    df['H-C'] = abs(df['High'] - df['Close'].shift(1))
    df['L-C'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-C', 'L-C']].max(axis=1)
    
    df['UpMove'] = df['High'] - df['High'].shift(1)
    df['DownMove'] = df['Low'].shift(1) - df['Low']
    
    df['+DM'] = np.where((df['UpMove'] > df['DownMove']) & (df['UpMove'] > 0), df['UpMove'], 0)
    df['-DM'] = np.where((df['DownMove'] > df['UpMove']) & (df['DownMove'] > 0), df['DownMove'], 0)
    
    def wilder(x, period): return x.ewm(alpha=1/period, adjust=False).mean()

    tr_s = wilder(df['TR'], period).replace(0, 1)
    p_dm_s = wilder(df['+DM'], period)
    n_dm_s = wilder(df['-DM'], period)
    
    p_di = 100 * (p_dm_s / tr_s)
    n_di = 100 * (n_dm_s / tr_s)
    dx = 100 * abs(p_di - n_di) / (p_di + n_di)
    return wilder(dx, period)

# --- MOTOR DE BÚSQUEDA DE SEÑAL ---
def get_last_signal(df, adx_th):
    """Recorre la historia para encontrar la última señal válida"""
    df['ADX'] = calculate_adx(df)
    df_ha = calculate_heikin_ashi(df)
    
    last_signal = None
    in_position = False
    
    for i in range(1, len(df_ha)):
        color = df_ha['Color'].iloc[i]
        adx = df['ADX'].iloc[i]
        date = df_ha.index[i]
        price = df_ha['Close'].iloc[i]
        
        # COMPRA: Verde + ADX>20
        if not in_position and color == 1 and adx > adx_th:
            in_position = True
            last_signal = {"Tipo": "🟢 COMPRA", "Fecha": date, "Precio": price, "ADX": adx, "Color": 1}
        # VENTA: Rojo
        elif in_position and color == -1:
            in_position = False
            last_signal = {"Tipo": "🔴 VENTA", "Fecha": date, "Precio": price, "ADX": adx, "Color": -1}
            
    # Si no hubo cruce, devolvemos el estado de la última vela
    if not last_signal:
        curr = df_ha.iloc[-1]
        t = "🟢 COMPRA" if curr['Color'] == 1 else "🔴 VENTA"
        last_signal = {"Tipo": t, "Fecha": curr.name, "Precio": curr['Close'], "ADX": df['ADX'].iloc[-1], "Color": curr['Color']}
        
    return last_signal

def run_bot():
    print(f"--- START: {datetime.now()} ---")
    
    # Almacén de datos
    all_signals_list = []      # Para el reporte detallado ordenado por fecha
    market_summary = {}        # Para el reporte de semáforo (Mapa)
    
    # Inicializar diccionario de resumen
    for t in TICKERS: market_summary[t] = {}

    # --- CICLO DE ESCANEO ---
    for interval, label, period in TIMEFRAMES:
        print(f"Escaneando {label}...")
        try:
            data = yf.download(TICKERS, interval=interval, period=period, group_by='ticker', progress=False, auto_adjust=True)
            
            for ticker in TICKERS:
                try:
                    df = data[ticker].dropna() if len(TICKERS)>1 else data.dropna()
                    if df.empty or len(df)<50: continue
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                    # Analizar
                    sig = get_last_signal(df, ADX_TH)
                    
                    if sig:
                        # 1. Guardar para el Resumen (Mapa)
                        market_summary[ticker][interval] = sig['Color']
                        if interval == '1d': 
                            market_summary[ticker]['Price'] = sig['Precio']
                        
                        # 2. Guardar para la Lista Detallada
                        all_signals_list.append({
                            "Ticker": ticker,
                            "TF": label,
                            "Tipo": sig['Tipo'],
                            "Precio": sig['Precio'],
                            "ADX": sig['ADX'],
                            "Fecha": sig['Fecha'], # Objeto datetime para ordenar
                            "Fecha_Str": sig['Fecha'].strftime('%d-%m-%Y')
                        })
                except: pass
        except: pass

    # --- ENVÍO 1: REPORTE MAPA (SEMÁFORO) ---
    full_bull, starting_bull, pullback, full_bear = [], [], [], []
    
    for t, d in market_summary.items():
        if '1mo' not in d or '1wk' not in d or '1d' not in d: continue
        
        m, w, day = d['1mo'], d['1wk'], d['1d']
        p = d.get('Price', 0)
        line = f"• {t}: ${p:.2f}"
        
        if m==1 and w==1 and day==1: full_bull.append(line)
        elif m<=0 and w==1 and day==1: starting_bull.append(line)
        elif m==1 and w==1 and day==-1: pullback.append(line)
        elif m==-1 and w==-1 and day==-1: full_bear.append(line)

    map_msg = f"🗺️ **MAPA DE MERCADO** ({datetime.now().strftime('%d/%m')})\n\n"
    if starting_bull: map_msg += f"🌱 **NACIMIENTO TENDENCIA**\n" + "\n".join(starting_bull) + "\n\n"
    if full_bull: map_msg += f"🚀 **TENDENCIA FUERTE**\n" + "\n".join(full_bull) + "\n\n"
    if pullback: map_msg += f"⚠️ **CORRECCIÓN / PULLBACK**\n" + "\n".join(pullback) + "\n\n"
    if full_bear: map_msg += f"🩸 **TENDENCIA BAJISTA**\n" + "\n".join(full_bear[:10]) + (f"\n...y {len(full_bear)-10} más" if len(full_bear)>10 else "")
    
    send_message(map_msg)
    time.sleep(2)

    # --- ENVÍO 2: LISTA DE SEÑALES DETALLADA (ORDENADA POR FECHA) ---
    if all_signals_list:
        # Ordenar: La más reciente primero
        all_signals_list.sort(key=lambda x: x['Fecha'], reverse=True)
        
        # Filtro de cantidad para no saturar (ej: últimas 30 señales del mercado)
        # Puedes aumentar este número si quieres recibir más
        TOP_SIGNALS = 30
        
        header = f"📋 **ÚLTIMAS {TOP_SIGNALS} SEÑALES DETECTADAS**\n(Ordenadas por fecha reciente)\n"
        send_message(header)
        
        for s in all_signals_list[:TOP_SIGNALS]:
            icon = "🚨" if "VENTA" in s['Tipo'] else "🚀"
            
            # FORMATO EXACTO DE TU IMAGEN
            msg = (
                f"{icon} **{s['Ticker']} ({s['TF']})**\n"
                f"**{s['Tipo']}**\n"
                f"Precio: ${s['Precio']:.2f}\n"
                f"ADX: {s['ADX']:.1f}\n"
                f"Fecha Señal: {s['Fecha_Str']}"
            )
            send_message(msg)
            time.sleep(0.5) # Pausa leve para evitar bloqueo
            
    else:
        send_message("🤖 No se encontraron señales.")

if __name__ == "__main__":
    run_bot()
