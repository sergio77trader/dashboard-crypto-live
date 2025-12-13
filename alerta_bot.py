import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# --- CREDENCIALES ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- CONFIGURACIÓN ESTRATEGIA (Periodos largos para precisión ADX) ---
TIMEFRAMES = [
    ("1mo", "MENSUAL", "max"),
    ("1wk", "SEMANAL", "10y"),
    ("1d", "DIARIO", "5y")
]

ADX_LEN = 14
ADX_TH = 20

# --- LISTA COMPLETA ---
WATCHLIST = [
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX',
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NFLX', 'CRM', 'ORCL', 'ADBE', 'IBM', 'CSCO', 'PLTR',
    'AMD', 'INTC', 'QCOM', 'AVGO', 'TXN', 'MU', 'ADI', 'AMAT', 'ARM', 'SMCI', 'TSM', 'ASML',
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B', 'PYPL', 'SQ', 'COIN',
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'TGT', 'HD', 'PG',
    'XOM', 'CVX', 'SLB', 'BA', 'CAT', 'GE', 'MMM',
    'BABA', 'JD', 'BIDU', 'PBR', 'VALE', 'ITUB',
    'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EWZ', 'XLE', 'XLF', 'XLK', 'XLV', 'ARKK', 'GLD', 'SLV', 'GDX'
]

def send_message(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

# --- CÁLCULOS MATEMÁTICOS NATIVOS ---
def calculate_heikin_ashi(df):
    df_ha = df.copy()
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    ha_open = [df['Open'].iloc[0]]
    for i in range(1, len(df)):
        prev_open = ha_open[-1]
        prev_close = df_ha['HA_Close'].iloc[i-1]
        ha_open.append((prev_open + prev_close) / 2)
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

    tr_smooth = wilder(df['TR'], period)
    p_dm_smooth = wilder(df['+DM'], period)
    n_dm_smooth = wilder(df['-DM'], period)
    
    p_di = 100 * (p_dm_smooth / tr_smooth.replace(0, 1))
    n_di = 100 * (n_dm_smooth / tr_smooth.replace(0, 1))
    dx = 100 * abs(p_di - n_di) / (p_di + n_di)
    adx = wilder(dx, period)
    
    return adx

# --- MOTOR DE BÚSQUEDA HISTÓRICA ---
def get_signal_status(df, adx_th):
    df['ADX'] = calculate_adx(df)
    df_ha = calculate_heikin_ashi(df)
    
    last_signal = None
    in_position = False
    
    for i in range(1, len(df_ha)):
        color = df_ha['Color'].iloc[i]
        adx = df['ADX'].iloc[i]
        
        # COMPRA
        if not in_position and color == 1 and adx > adx_th:
            in_position = True
            last_signal = {
                "Tipo": "🟢 COMPRA",
                "Fecha": df_ha.index[i],
                "Precio": df_ha['Close'].iloc[i],
                "ADX": adx
            }
        # VENTA
        elif in_position and color == -1:
            in_position = False
            last_signal = {
                "Tipo": "🔴 VENTA",
                "Fecha": df_ha.index[i],
                "Precio": df_ha['Close'].iloc[i],
                "ADX": adx
            }
            
    return last_signal

def run_bot():
    print(f"--- SCAN START: {datetime.now()} ---")
    msgs = 0
    
    for interval, label, period in TIMEFRAMES:
        print(f"Analizando {label}...")
        try:
            data = yf.download(WATCHLIST, interval=interval, period=period, group_by='ticker', progress=False, auto_adjust=True)
        except: continue

        for ticker in WATCHLIST:
            try:
                if len(WATCHLIST) > 1: df = data[ticker].dropna()
                else: df = data.dropna()
                
                if df.empty or len(df) < 50: continue
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                # Obtener la señal histórica
                sig = get_signal_status(df, ADX_TH)
                
                if sig:
                    # Formateo de fecha
                    f_date = sig['Fecha'].strftime('%d-%m-%Y')
                    
                    # Mensaje con formato exacto
                    txt = (
                        f"🚨 **{ticker} ({label})**\n"
                        f"**{sig['Tipo']}**\n"
                        f"Precio: ${sig['Precio']:.2f}\n"
                        f"ADX: {sig['ADX']:.1f}\n"
                        f"Fecha Señal: {f_date}"
                    )
                    send_message(txt)
                    msgs += 1
            except: pass
            
    if msgs == 0: send_message("🤖 Sin señales nuevas.")
    else: print(f"Enviadas {msgs} alertas.")

if __name__ == "__main__":
    run_bot()
