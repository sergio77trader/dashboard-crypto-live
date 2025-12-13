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

# --- CONFIGURACIÓN ESPECÍFICA (Solo Mensual y Semanal) ---
TIMEFRAMES = [
    ("1mo", "MENSUAL", "max"),  # Historia completa para ADX mensual
    ("1wk", "SEMANAL", "10y")   # 10 años para semanal
    # ("1d", "DIARIO", "5y")    # (Opcional: Descomentar si quieres diario también)
]

ADX_LEN = 14
ADX_TH = 20

# --- BASE DE DATOS COMPLETA ---
# --- BASE DE DATOS COMPLETA (Actualizada) ---
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
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except: pass

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
    
    # Recorrido histórico para encontrar la última señal real
    for i in range(1, len(df_ha)):
        color = df_ha['Color'].iloc[i]
        adx = df['ADX'].iloc[i]
        date = df_ha.index[i]
        price = df_ha['Close'].iloc[i]
        
        # COMPRA
        if not in_position and color == 1 and adx > adx_th:
            in_position = True
            last_signal = {"Tipo": "🟢 COMPRA", "Fecha": date, "Precio": price, "ADX": adx}
        # VENTA
        elif in_position and color == -1:
            in_position = False
            last_signal = {"Tipo": "🔴 VENTA", "Fecha": date, "Precio": price, "ADX": adx}
            
    return last_signal

def run_bot():
    print(f"--- START MTF SCAN: {datetime.now()} ---")
    all_signals = []

    for interval, label, period in TIMEFRAMES:
        print(f"Procesando {label}...")
        try:
            data = yf.download(TICKERS, interval=interval, period=period, group_by='ticker', progress=False, auto_adjust=True)
            for ticker in TICKERS:
                try:
                    df = data[ticker].dropna() if len(TICKERS)>1 else data.dropna()
                    if df.empty or len(df)<50: continue
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                    sig = get_last_signal(df, ADX_TH)
                    
                    if sig:
                        all_signals.append({
                            "Ticker": ticker,
                            "TF": label,
                            "Tipo": sig['Tipo'],
                            "Precio": sig['Precio'],
                            "ADX": sig['ADX'],
                            "Fecha": sig['Fecha'],
                            "Fecha_Str": sig['Fecha'].strftime('%d-%m-%Y')
                        })
                except: pass
        except: pass

    # --- ENVÍO DE RESULTADOS ---
    if not all_signals:
        send_message("🤖 MTF: Sin señales detectadas.")
        return

    # Ordenar por fecha (Más reciente primero)
    all_signals.sort(key=lambda x: x['Fecha'], reverse=True)
    
    # Cabecera
    send_message(f"📊 **REPORTE MENSUAL Y SEMANAL**\nEnviando las últimas señales de {len(TICKERS)} activos...")
    time.sleep(1)

    # Enviar TODAS las señales (Sin límites)
    for s in all_signals:
        icon = "🚨" if "VENTA" in s['Tipo'] else "🚀"
        msg = (
            f"{icon} **{s['Ticker']} ({s['TF']})**\n"
            f"**{s['Tipo']}**\n"
            f"Precio: ${s['Precio']:.2f}\n"
            f"ADX: {s['ADX']:.1f}\n"
            f"Fecha Señal: {s['Fecha_Str']}"
        )
        send_message(msg)
        # Pausa leve para que Telegram no bloquee por spam (flood limit)
        time.sleep(0.3)

    send_message("✅ Fin del reporte.")

if __name__ == "__main__":
    run_bot()
