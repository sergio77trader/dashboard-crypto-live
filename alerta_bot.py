import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# --- CREDENCIALES ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- CONFIGURACIÓN IDÉNTICA A STREAMLIT ---
# (Intervalo, Etiqueta, Periodo Histórico para que coincida el ADX)
TIMEFRAMES = [
    ("1mo", "MENSUAL", "max"),
    ("1wk", "SEMANAL", "10y"),
    ("1d", "DIARIO", "5y")
]

ADX_LEN = 14
ADX_TH = 20

# --- WATCHLIST COMPLETA ---
TICKERS = [
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

# --- CÁLCULOS MATEMÁTICOS EXACTOS ---

def calculate_heikin_ashi(df):
    df_ha = df.copy()
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    # Cálculo iterativo (Igual que Streamlit/TradingView)
    ha_open = [df['Open'].iloc[0]]
    for i in range(1, len(df)):
        prev_open = ha_open[-1]
        prev_close = df_ha['HA_Close'].iloc[i-1]
        ha_open.append((prev_open + prev_close) / 2)
        
    df_ha['HA_Open'] = ha_open
    df_ha['Color'] = np.where(df_ha['HA_Close'] > df_ha['HA_Open'], 1, -1)
    return df_ha

def calculate_adx(df, period=14):
    """Cálculo manual de ADX (Wilder's Smoothing) para coincidir con Pandas TA"""
    df = df.copy()
    
    # True Range
    df['H-L'] = df['High'] - df['Low']
    df['H-C'] = abs(df['High'] - df['Close'].shift(1))
    df['L-C'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-C', 'L-C']].max(axis=1)
    
    # DM
    df['UpMove'] = df['High'] - df['High'].shift(1)
    df['DownMove'] = df['Low'].shift(1) - df['Low']
    df['+DM'] = np.where((df['UpMove'] > df['DownMove']) & (df['UpMove'] > 0), df['UpMove'], 0)
    df['-DM'] = np.where((df['DownMove'] > df['UpMove']) & (df['DownMove'] > 0), df['DownMove'], 0)
    
    # Wilder's Smoothing (Esta es la clave para que coincida)
    def wilder_smooth(series, n):
        return series.ewm(alpha=1/n, adjust=False).mean()

    tr_smooth = wilder_smooth(df['TR'], period)
    p_dm_smooth = wilder_smooth(df['+DM'], period)
    n_dm_smooth = wilder_smooth(df['-DM'], period)
    
    p_di = 100 * (p_dm_smooth / tr_smooth)
    n_di = 100 * (n_dm_smooth / tr_smooth)
    
    dx = 100 * abs(p_di - n_di) / (p_di + n_di)
    adx = wilder_smooth(dx, period)
    
    return adx

# --- MOTOR DE ANÁLISIS ---
def get_last_signal(df, adx_th):
    # Calcular Indicadores
    df['ADX'] = calculate_adx(df)
    df_ha = calculate_heikin_ashi(df)
    
    # Recorrer para encontrar la última señal
    # (Exactamente la lógica de tu script de Streamlit)
    last_signal = None
    in_position = False
    
    for i in range(1, len(df_ha)):
        date = df_ha.index[i]
        ha_color = df_ha['Color'].iloc[i]
        adx_val = df['ADX'].iloc[i]
        price = df_ha['Close'].iloc[i]
        
        # COMPRA
        if not in_position and ha_color == 1 and adx_val > adx_th:
            in_position = True
            last_signal = {
                "Type": "🟢 COMPRA",
                "Date": date,
                "Price": price,
                "ADX": adx_val
            }
            
        # VENTA
        elif in_position and ha_color == -1:
            in_position = False
            last_signal = {
                "Type": "🔴 VENTA",
                "Date": date,
                "Price": price,
                "ADX": adx_val
            }
            
    return last_signal

def run_bot():
    print(f"--- SCAN START: {datetime.now()} ---")
    msgs = 0
    
    # Descarga masiva para optimizar (agrupada por tickers)
    # NOTA: Para mensual y semanal descargamos por separado para asegurar periodos correctos
    
    for interval, label, period in TIMEFRAMES:
        print(f"Procesando {label}...")
        
        # Procesamos uno por uno para asegurar consistencia de datos históricos
        for ticker in TICKERS:
            try:
                df = yf.download(ticker, interval=interval, period=period, progress=False, auto_adjust=True)
                
                if df.empty or len(df) < 50: continue
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                # Obtener la ÚLTIMA señal histórica
                signal = get_last_signal(df, ADX_TH)
                
                if signal:
                    # VALIDACIÓN DE FECHA:
                    # ¿Queremos que avise SIEMPRE de la última señal (aunque sea vieja)?
                    # ¿O solo si es RECIENTE?
                    # Como pediste "para saber si funciona, que me envie", enviamos SIEMPRE
                    # la última señal vigente, pero marcamos la fecha.
                    
                    sig_date = signal['Date'].strftime('%d-%m-%Y')
                    
                    # Formato FICHA TÉCNICA (Tu imagen 1)
                    icon = "🚨" if "VENTA" in signal['Type'] else "🚀"
                    
                    msg = (
                        f"{icon} **{ticker} ({label})**\n"
                        f"**{signal['Type']}**\n"
                        f"Precio: ${signal['Price']:.2f}\n"
                        f"ADX: {signal['ADX']:.1f}\n"
                        f"Fecha Señal: {sig_date}"
                    )
                    
                    # FILTRO ANTI-SPAM (Opcional):
                    # Si quieres que solo avise si la señal es de "ESTA SEMANA" o "ESTE MES",
                    # descomenta y ajusta esta lógica. Por ahora envía todo para que veas que anda.
                    
                    send_message(msg)
                    msgs += 1
                    
            except Exception as e:
                print(f"Error {ticker}: {e}")
                pass
            
    if msgs == 0:
        send_message("🤖 Escaneo finalizado. Sin señales detectadas.")
    else:
        print(f"Enviados {msgs} mensajes.")

if __name__ == "__main__":
    run_bot()
