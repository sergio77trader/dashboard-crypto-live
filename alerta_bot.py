import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# --- CREDENCIALES ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- CONFIGURACIÓN ---
# TFs a analizar: (Intervalo Yahoo, Nombre Bonito, Periodo de datos)
TIMEFRAMES = [
    ("1mo", "MENSUAL", "max"),
    ("1wk", "SEMANAL", "5y"),
    ("1d", "DIARIO", "2y") 
]

# Misma lista que en Streamlit
WATCHLIST = [
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'MELI', 'GLOB', 'VIST', 'BIOX',
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NFLX',
    'AMD', 'INTC', 'QCOM', 'AVGO', 'TSM', 'MU',
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA',
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT',
    'XOM', 'CVX', 'SLB', 'BA', 'CAT', 'GE',
    'BABA', 'JD', 'BIDU', 'PBR', 'VALE', 'ITUB',
    'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EWZ', 'XLE', 'XLF', 'ARKK', 'GLD', 'SLV'
]

def send_message(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

# --- INDICADORES (MATEMÁTICA NATIVA - IDÉNTICA A STREAMLIT) ---
def calculate_heikin_ashi(df):
    df_ha = df.copy()
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    ha_open = [df['Open'].iloc[0]]
    for i in range(1, len(df)):
        ha_open.append((ha_open[-1] + df_ha['HA_Close'].iloc[i-1]) / 2)
    df_ha['HA_Open'] = ha_open
    
    # 1 = Verde, -1 = Rojo
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
    
    # Suavizado Wilder (Clave para coincidir con TradingView/Streamlit)
    df['TR_Smooth'] = df['TR'].ewm(alpha=1/period, adjust=False).mean()
    df['+DM_Smooth'] = df['+DM'].ewm(alpha=1/period, adjust=False).mean()
    df['-DM_Smooth'] = df['-DM'].ewm(alpha=1/period, adjust=False).mean()

    df['+DI'] = 100 * (df['+DM_Smooth'] / df['TR_Smooth'])
    df['-DI'] = 100 * (df['-DM_Smooth'] / df['TR_Smooth'])
    df['DX'] = 100 * abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'])
    df['ADX'] = df['DX'].ewm(alpha=1/period, adjust=False).mean()
    
    return df['ADX']

def run_bot():
    print(f"--- SCAN START: {datetime.now()} ---")
    
    # Filtro ADX para compra (Venta no necesita ADX para salir)
    ADX_TH = 20
    msgs = 0
    
    for interval, label, period in TIMEFRAMES:
        try:
            # Descarga Masiva
            data = yf.download(WATCHLIST, interval=interval, period=period, group_by='ticker', progress=False, auto_adjust=True)
        except: continue

        for ticker in WATCHLIST:
            try:
                # Extraer DF
                if len(WATCHLIST) > 1: df = data[ticker].dropna()
                else: df = data.dropna()
                
                if df.empty or len(df) < 50: continue

                # Cálculos
                df['ADX'] = calculate_adx(df)
                df_ha = calculate_heikin_ashi(df)
                
                # --- DETECCIÓN DE SEÑAL ---
                # Miramos la ÚLTIMA vela disponible (en curso o cerrada) y la ANTERIOR
                curr = df_ha.iloc[-1]
                prev = df_ha.iloc[-2]
                
                signal_type = None
                icon = ""
                
                # COMPRA: Giro a Verde + Fuerza
                if prev['Color'] == -1 and curr['Color'] == 1 and curr['ADX'] > ADX_TH:
                    signal_type = "COMPRA (LONG)"
                    icon = "🟢"
                
                # VENTA: Giro a Rojo (Salida)
                elif prev['Color'] == 1 and curr['Color'] == -1:
                    signal_type = "VENTA (SHORT)"
                    icon = "🔴"
                
                # ENVIAR MENSAJE (Formato Ficha Técnica)
                if signal_type:
                    # Fecha de la vela (importante para saber cuándo se dio)
                    sig_date = curr.name.strftime('%d-%m-%Y')
                    
                    msg = (
                        f"🚨 **ALERTA DE MERCADO**\n"
                        f"-----------------------\n"
                        f"📈 **ACTIVO:** {ticker}\n"
                        f"⏱ **TF:** {label}\n"
                        f"{icon} **TIPO:** {signal_type}\n"
                        f"💰 **PRECIO:** ${curr['Close']:.2f}\n"
                        f"📊 **ADX:** {curr['ADX']:.2f}\n"
                        f"📅 **FECHA:** {sig_date}"
                    )
                    send_message(msg)
                    msgs += 1
                    
            except: pass
            
    if msgs == 0:
        # Mensaje opcional para saber que está vivo (puedes borrarlo luego)
        send_message("🤖 Escaneo finalizado. Sin cambios de tendencia en este turno.")

if __name__ == "__main__":
    run_bot()
