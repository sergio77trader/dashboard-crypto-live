import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# --- CREDENCIALES ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- LISTA DE ACTIVOS A VIGILAR ---
WATCHLIST = [
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'ADA-USD',
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NFLX',
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'MELI',
    'SPY', 'QQQ', 'IWM', 'EEM', 'XLE', 'XLF', 'ARKK'
]

def send_message(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Faltan credenciales de Telegram.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

# --- INDICADORES MATEMÁTICOS (SIN LIBRERÍAS EXTERNAS) ---
def calculate_heikin_ashi(df):
    df_ha = df.copy()
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    # Calculo iterativo para HA Open
    ha_open = [df['Open'].iloc[0]]
    for i in range(1, len(df)):
        ha_open.append((ha_open[-1] + df_ha['HA_Close'].iloc[i-1]) / 2)
    df_ha['HA_Open'] = ha_open
    
    df_ha['Color'] = np.where(df_ha['HA_Close'] > df_ha['HA_Open'], 1, -1)
    return df_ha

def calculate_adx(df, period=14):
    """Calcula ADX usando solo Pandas y Numpy (Más rápido y sin errores de instalación)"""
    df = df.copy()
    
    # True Range
    df['H-L'] = df['High'] - df['Low']
    df['H-C'] = abs(df['High'] - df['Close'].shift(1))
    df['L-C'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-C', 'L-C']].max(axis=1)
    
    # Directional Movement
    df['UpMove'] = df['High'] - df['High'].shift(1)
    df['DownMove'] = df['Low'].shift(1) - df['Low']
    df['+DM'] = np.where((df['UpMove'] > df['DownMove']) & (df['UpMove'] > 0), df['UpMove'], 0)
    df['-DM'] = np.where((df['DownMove'] > df['UpMove']) & (df['DownMove'] > 0), df['DownMove'], 0)
    
    # Suavizado (Exponential Weighted Moving Average)
    df['TR_Smooth'] = df['TR'].ewm(alpha=1/period, adjust=False).mean()
    df['+DM_Smooth'] = df['+DM'].ewm(alpha=1/period, adjust=False).mean()
    df['-DM_Smooth'] = df['-DM'].ewm(alpha=1/period, adjust=False).mean()

    # DI y DX
    df['+DI'] = 100 * (df['+DM_Smooth'] / df['TR_Smooth'])
    df['-DI'] = 100 * (df['-DM_Smooth'] / df['TR_Smooth'])
    df['DX'] = 100 * abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'])
    
    # ADX Final
    df['ADX'] = df['DX'].ewm(alpha=1/period, adjust=False).mean()
    
    return df['ADX']

def run_bot():
    print(f"--- SCAN START: {datetime.now()} ---")
    msgs = 0
    
    # Definimos temporalidades a escanear (Yahoo Format, Nombre)
    TIMEFRAMES = [("1mo", "MENSUAL"), ("1wk", "SEMANAL"), ("1d", "DIARIO")]
    
    for interval, label in TIMEFRAMES:
        print(f"Analizando {label}...")
        try:
            # Descarga masiva (Mucho más rápido)
            data = yf.download(WATCHLIST, interval=interval, period="2y", group_by='ticker', progress=False, auto_adjust=True)
        except Exception as e:
            print(f"Error descargando {label}: {e}")
            continue

        for ticker in WATCHLIST:
            try:
                # Extraer DF del ticker
                if len(WATCHLIST) > 1:
                    df = data[ticker].dropna()
                else:
                    df = data.dropna()
                
                if df.empty or len(df) < 50: continue
                
                # --- CÁLCULOS NATIVOS ---
                df['ADX'] = calculate_adx(df)
                df_ha = calculate_heikin_ashi(df)
                
                # --- LÓGICA DE SEÑAL ---
                curr = df_ha.iloc[-1]
                prev = df_ha.iloc[-2]
                adx_val = df.iloc[-1]['ADX']
                
                sig = None
                
                # COMPRA: Rojo -> Verde + ADX>20
                if prev['Color'] == -1 and curr['Color'] == 1 and adx_val > 20:
                    sig = "🟢 COMPRA"
                
                # VENTA: Verde -> Rojo
                elif prev['Color'] == 1 and curr['Color'] == -1:
                    sig = "🔴 VENTA"
                
                if sig:
                    txt = f"🚨 **{ticker}** ({label})\n{sig}\nPrecio: ${curr['Close']:.2f}\nADX: {adx_val:.1f}"
                    send_message(txt)
                    msgs += 1
                    
            except Exception as e:
                pass 
            
    if msgs == 0: print("Sin señales.")

if __name__ == "__main__":
    run_bot()
