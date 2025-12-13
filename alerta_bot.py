import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# --- CREDENCIALES ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- CONFIGURACIÓN IDÉNTICA A TU STREAMLIT ---
# (Intervalo Yahoo, Nombre para mostrar, Periodo de datos)
TIMEFRAMES = [
    ("1mo", "MENSUAL", "max"),  # Max historia para que el ADX mensual coincida
    ("1wk", "SEMANAL", "10y"),
    ("1d", "DIARIO", "5y")
]

ADX_LEN = 14
ADX_TH = 20

# --- LISTA DE ACTIVOS (Tu base de datos completa) ---
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

# --- CÁLCULOS MATEMÁTICOS (Versión Nativa) ---

def calculate_heikin_ashi(df):
    df_ha = df.copy()
    # HA Close
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    # HA Open Iterativo (Clave para coincidir con TradingView/Streamlit)
    ha_open = [df['Open'].iloc[0]]
    for i in range(1, len(df)):
        prev_open = ha_open[-1]
        prev_close = df_ha['HA_Close'].iloc[i-1]
        ha_open.append((prev_open + prev_close) / 2)
    df_ha['HA_Open'] = ha_open
    
    # Color: 1 = Verde, -1 = Rojo
    df_ha['Color'] = np.where(df_ha['HA_Close'] > df_ha['HA_Open'], 1, -1)
    return df_ha

def calculate_adx(df, period=14):
    """Calcula ADX manual (Wilder's Smoothing) sin librerías externas"""
    df = df.copy()
    df['H-L'] = df['High'] - df['Low']
    df['H-C'] = abs(df['High'] - df['Close'].shift(1))
    df['L-C'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-C', 'L-C']].max(axis=1)
    
    df['UpMove'] = df['High'] - df['High'].shift(1)
    df['DownMove'] = df['Low'].shift(1) - df['Low']
    df['+DM'] = np.where((df['UpMove'] > df['DownMove']) & (df['UpMove'] > 0), df['UpMove'], 0)
    df['-DM'] = np.where((df['DownMove'] > df['UpMove']) & (df['DownMove'] > 0), df['DownMove'], 0)
    
    # Función auxiliar para media móvil exponencial de Wilder
    def wilder(x, period):
        return x.ewm(alpha=1/period, adjust=False).mean()

    tr_smooth = wilder(df['TR'], period)
    p_dm_smooth = wilder(df['+DM'], period)
    n_dm_smooth = wilder(df['-DM'], period)
    
    # Evitar división por cero
    tr_smooth = tr_smooth.replace(0, 1)
    
    p_di = 100 * (p_dm_smooth / tr_smooth)
    n_di = 100 * (n_dm_smooth / tr_smooth)
    
    dx = 100 * abs(p_di - n_di) / (p_di + n_di)
    adx = wilder(dx, period)
    return adx

# --- MOTOR DE ANÁLISIS ---
def get_last_signal_status(df, adx_th):
    """
    Recorre el historial para encontrar la ÚLTIMA señal válida y su fecha.
    """
    df['ADX'] = calculate_adx(df)
    df_ha = calculate_heikin_ashi(df)
    
    last_signal = None
    in_position = False # Asumimos flat al inicio de la historia
    
    # Iteramos fila por fila para simular el comportamiento real
    for i in range(1, len(df_ha)):
        date = df_ha.index[i]
        price = df_ha['Close'].iloc[i]
        color = df_ha['Color'].iloc[i]
        adx = df['ADX'].iloc[i]
        
        # CONDICIÓN DE ENTRADA (COMPRA)
        # Vela Verde + ADX > 20 + No estamos comprados
        if not in_position and color == 1 and adx > adx_th:
            in_position = True
            last_signal = {
                "Tipo": "COMPRA 🟢",
                "Fecha": date,
                "Precio": price,
                "ADX": adx
            }
            
        # CONDICIÓN DE SALIDA (VENTA)
        # Vela Roja + Estamos comprados (o simplemente tendencia bajista)
        elif in_position and color == -1:
            in_position = False
            last_signal = {
                "Tipo": "VENTA 🔴",
                "Fecha": date,
                "Precio": price,
                "ADX": adx
            }
            
    return last_signal

def run_bot():
    print(f"--- INICIANDO REPORTE MASIVO: {datetime.now()} ---")
    msgs_sent = 0
    
    for interval, label, period in TIMEFRAMES:
        print(f"Descargando datos {label}...")
        try:
            # Descarga grupal para velocidad
            data = yf.download(TICKERS, interval=interval, period=period, group_by='ticker', progress=False, auto_adjust=True)
        except Exception as e:
            print(f"Error descarga general: {e}")
            continue

        for ticker in TICKERS:
            try:
                # Extraer DataFrame individual
                if len(TICKERS) > 1:
                    df = data[ticker].dropna()
                else:
                    df = data.dropna()
                
                if df.empty or len(df) < 50: continue
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                # Obtener la ficha técnica de la última señal
                signal = get_last_signal(df, ADX_TH)
                
                if signal:
                    # Formateo de fecha
                    sig_date = signal['Fecha'].strftime('%d-%m-%Y')
                    
                    # FILTRO DE RELEVANCIA (OPCIONAL):
                    # Si quieres que te mande TODO lo que está activo (incluso señales de 2022), deja esto así.
                    # Si quieres solo señales NUEVAS de hoy, habría que comparar la fecha.
                    # Como pediste "al primer momento que lo activo me de señales", enviamos TODO el estado actual.
                    
                    # FORMATO DEL MENSAJE (IDÉNTICO A TU IMAGEN 1)
                    icon = "🚨" if "VENTA" in signal['Tipo'] else "🚀"
                    
                    msg = (
                        f"{icon} **{ticker} ({label})**\n"
                        f"**{signal['Tipo']}**\n"
                        f"Precio: ${signal['Price']:.2f}\n"
                        f"ADX: {signal['ADX']:.1f}\n"
                        f"Fecha Señal: {sig_date}"
                    )
                    
                    send_message(msg)
                    msgs += 1
                    
            except Exception as e:
                # print(f"Error {ticker}: {e}")
                pass
            
    if msgs == 0:
        send_message("🤖 Análisis finalizado. No se encontraron señales activas en la base de datos.")
    else:
        print(f"Reporte enviado: {msgs} activos analizados.")

if __name__ == "__main__":
    run_bot()
