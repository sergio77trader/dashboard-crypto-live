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
# Temporalidades a analizar (Intervalo Yahoo, Nombre Bonito, Periodo Histórico)
TIMEFRAMES = [
    ("1mo", "MENSUAL", "max"),
    ("1wk", "SEMANAL", "10y"),
    ("1d", "DIARIO", "5y")
]

ADX_LEN = 14
ADX_TH = 20

# --- BASE DE DATOS (Tu lista completa) ---
TICKERS = sorted([
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'CRESY', 'IRS', 'TEO', 'LOMA', 'DESP', 'VIST', 'GLOB', 'MELI', 'BIOX',
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NFLX', 'CRM', 'ORCL', 'ADBE', 'IBM', 'CSCO', 'PLTR',
    'AMD', 'INTC', 'QCOM', 'AVGO', 'TXN', 'MU', 'ADI', 'AMAT', 'ARM', 'SMCI', 'TSM', 'ASML',
    'JPM', 'BAC', 'C', 'WFC', 'GS', 'MS', 'V', 'MA', 'AXP', 'BRK-B', 'PYPL', 'SQ', 'COIN',
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'NKE', 'WMT', 'COST', 'TGT', 'HD', 'PG',
    'XOM', 'CVX', 'SLB', 'BA', 'CAT', 'GE', 'MMM',
    'BABA', 'JD', 'BIDU', 'PBR', 'VALE', 'ITUB',
    'SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EWZ', 'XLE', 'XLF', 'XLK', 'XLV', 'ARKK', 'GLD', 'SLV', 'GDX'
])

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

# --- MOTOR DE BÚSQUEDA ---
def get_last_signal(df, adx_th):
    df['ADX'] = calculate_adx(df)
    df_ha = calculate_heikin_ashi(df)
    
    last_signal = None
    in_position = False
    
    for i in range(1, len(df_ha)):
        color = df_ha['Color'].iloc[i]
        adx = df['ADX'].iloc[i]
        date = df_ha.index[i]
        price = df_ha['Close'].iloc[i]
        
        # COMPRA
        if not in_position and color == 1 and adx > adx_th:
            in_position = True
            last_signal = {"Tipo": "COMPRA 🟢", "Fecha": date, "Precio": price, "ADX": adx}
        # VENTA
        elif in_position and color == -1:
            in_position = False
            last_signal = {"Tipo": "VENTA 🔴", "Fecha": date, "Precio": price, "ADX": adx}
            
    return last_signal

def run_bot():
    print(f"--- START SCAN: {datetime.now()} ---")
    
    all_signals = [] # Aquí guardaremos todas las señales para ordenarlas

    for interval, label, period in TIMEFRAMES:
        print(f"Descargando {label}...")
        try:
            data = yf.download(TICKERS, interval=interval, period=period, group_by='ticker', progress=False, auto_adjust=True)
            
            for ticker in TICKERS:
                try:
                    df = data[ticker].dropna() if len(TICKERS)>1 else data.dropna()
                    if df.empty or len(df)<50: continue
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                    sig = get_last_signal(df, ADX_TH)
                    
                    if sig:
                        # Guardamos en la lista maestra con toda la info
                        all_signals.append({
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

    # --- ORDENAMIENTO Y ENVÍO ---
    
    if not all_signals:
        send_message("🤖 Sin señales activas.")
        return

    # Ordenar: Las más recientes PRIMERO
    all_signals.sort(key=lambda x: x['Fecha'], reverse=True)
    
    # Enviar solo las TOP 20 más recientes (para no saturar si es la primera vez)
    # O enviar todo si prefieres. Aquí pongo un límite de seguridad.
    TOP_LIMIT = 20 
    
    send_message(f"📊 **REPORTE DE SEÑALES ({len(all_signals)} encontradas)**\nMostrando las {min(len(all_signals), TOP_LIMIT)} más recientes:")
    
    for s in all_signals[:TOP_LIMIT]:
        icon = "🚨" if "VENTA" in s['Tipo'] else "🚀"
        
        # FORMATO EXACTO QUE PEDISTE
        msg = (
            f"{icon} **{s['Ticker']} ({s['TF']})**\n"
            f"**{s['Tipo']}**\n"
            f"Precio: ${s['Precio']:.2f}\n"
            f"ADX: {s['ADX']:.1f}\n"
            f"Fecha Señal: {s['Fecha_Str']}"
        )
        send_message(msg)

    print("Finalizado.")

if __name__ == "__main__":
    run_bot()
