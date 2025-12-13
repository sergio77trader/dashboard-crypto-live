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

# --- CONFIGURACIÓN ESTRATEGIA ---
# Analizamos estas 3 temporalidades obligatorias
TIMEFRAMES = [
    ("1mo", "MENSUAL", "max"),  # Max historia para precisión en mensual
    ("1wk", "SEMANAL", "10y"),
    ("1d", "DIARIO", "5y")
]

ADX_TH = 20
ADX_LEN = 14

# --- BASE DE DATOS COMPLETA (Tu lista) ---
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
    # Gestión de errores y reintentos básicos
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

# --- CÁLCULOS MATEMÁTICOS NATIVOS (Sin librerías externas para evitar errores) ---

def calculate_heikin_ashi(df):
    """Cálculo iterativo idéntico a tu Streamlit/TradingView"""
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
    """Cálculo manual de ADX (Wilder) para robustez en servidor"""
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

# --- MOTOR DE BÚSQUEDA DE ÚLTIMA SEÑAL ---
def get_last_signal(df, adx_th):
    df['ADX'] = calculate_adx(df)
    df_ha = calculate_heikin_ashi(df)
    
    last_signal = None
    in_position = False
    
    # Recorremos la historia para simular la estrategia real
    for i in range(1, len(df_ha)):
        color = df_ha['Color'].iloc[i]
        adx = df['ADX'].iloc[i]
        date = df_ha.index[i]
        price = df_ha['Close'].iloc[i]
        
        # CONDICIÓN COMPRA: Vela Verde + ADX > 20
        if not in_position and color == 1 and adx > adx_th:
            in_position = True
            last_signal = {"Tipo": "🟢 COMPRA", "Fecha": date, "Precio": price, "ADX": adx}
            
        # CONDICIÓN VENTA: Vela Roja
        elif in_position and color == -1:
            in_position = False
            last_signal = {"Tipo": "🔴 VENTA", "Fecha": date, "Precio": price, "ADX": adx}
            
    return last_signal

# --- EJECUCIÓN PRINCIPAL ---
def run_bot():
    print(f"--- INICIO ESCANEO: {datetime.now()} ---")
    
    all_signals_found = []
    
    # 1. Escaneo por temporalidad
    for interval, label, period in TIMEFRAMES:
        print(f"Descargando {label}...")
        try:
            # Descarga masiva para no saturar
            data = yf.download(TICKERS, interval=interval, period=period, group_by='ticker', progress=False, auto_adjust=True)
            
            for ticker in TICKERS:
                try:
                    # Extraer DF
                    if len(TICKERS) > 1: df = data[ticker].dropna()
                    else: df = data.dropna()
                    
                    if df.empty or len(df) < 50: continue
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                    # Analizar
                    sig = get_last_signal(df, ADX_TH)
                    
                    if sig:
                        # Guardamos TODOS los datos para ordenar después
                        all_signals_found.append({
                            "Ticker": ticker,
                            "TF": label,
                            "Tipo": sig['Tipo'],
                            "Precio": sig['Precio'],
                            "ADX": sig['ADX'],
                            "Fecha": sig['Fecha'], # Objeto datetime para ordenar
                            "Fecha_Str": sig['Fecha'].strftime('%d-%m-%Y')
                        })
                except: pass
        except Exception as e:
            print(f"Error general en {label}: {e}")

    # 2. PROCESAMIENTO Y ENVÍO
    if not all_signals_found:
        send_message("🤖 Análisis completado. Sin señales detectadas.")
        return

    # A) REPORTE RESUMEN (Cantidad de señales)
    longs = len([x for x in all_signals_found if "COMPRA" in x['Tipo']])
    shorts = len([x for x in all_signals_found if "VENTA" in x['Tipo']])
    
    summary = (
        f"📊 **REPORTE DE MERCADO** ({datetime.now().strftime('%d/%m')})\n"
        f"Activos analizados: {len(TICKERS)}\n"
        f"🟢 Compras Activas: {longs}\n"
        f"🔴 Ventas Activas: {shorts}\n"
        f"⬇️ *Detalle ordenado por fecha a continuación:* ⬇️"
    )
    send_message(summary)
    time.sleep(2)

    # B) ENVÍO DE SEÑALES ORDENADAS (De más reciente a más antigua)
    # Ordenamos la lista completa por fecha descendente
    all_signals_found.sort(key=lambda x: x['Fecha'], reverse=True)
    
    # Enviamos TODAS las señales, una por una
    count = 0
    for s in all_signals_found:
        icon = "🚨" if "VENTA" in s['Tipo'] else "🚀"
        
        msg = (
            f"{icon} **{s['Ticker']} ({s['TF']})**\n"
            f"**{s['Tipo']}**\n"
            f"Precio: ${s['Precio']:.2f}\n"
            f"ADX: {s['ADX']:.1f}\n"
            f"Fecha Señal: {s['Fecha_Str']}"
        )
        send_message(msg)
        
        # Pausa anti-spam de Telegram (Importante para listas largas)
        time.sleep(0.5) 
        count += 1

    print(f"Finalizado. {count} mensajes enviados.")

if __name__ == "__main__":
    run_bot()
