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
TIMEFRAMES = [
    ("1mo", "MENSUAL", "max"),
    ("1wk", "SEMANAL", "10y"),
    ("1d", "DIARIO", "5y")
]

ADX_LEN = 14
ADX_TH = 20

# --- BASE DE DATOS (Tu lista completa) ---
TICKERS = [
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
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except: pass

# --- CÁLCULOS MATEMÁTICOS ---
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

# --- DETECTAR ÚLTIMA SEÑAL (Para ficha técnica) ---
def get_signal_details(df):
    """Devuelve la info exacta de la última señal para las fichas"""
    df['ADX'] = calculate_adx(df)
    df_ha = calculate_heikin_ashi(df)
    
    last_signal = None
    in_position = False
    
    for i in range(1, len(df_ha)):
        color = df_ha['Color'].iloc[i]
        adx = df['ADX'].iloc[i]
        date = df_ha.index[i]
        price = df_ha['Close'].iloc[i]
        
        if not in_position and color == 1 and adx > ADX_TH:
            in_position = True
            last_signal = {"Tipo": "COMPRA 🟢", "Fecha": date, "Precio": price, "ADX": adx, "Color": 1}
        elif in_position and color == -1:
            in_position = False
            last_signal = {"Tipo": "VENTA 🔴", "Fecha": date, "Precio": price, "ADX": adx, "Color": -1}
            
    # Si nunca hubo señal, devolvemos el estado actual
    if not last_signal:
        curr = df_ha.iloc[-1]
        t = "COMPRA 🟢" if curr['Color'] == 1 else "VENTA 🔴"
        last_signal = {"Tipo": t, "Fecha": curr.name, "Precio": curr['Close'], "ADX": df['ADX'].iloc[-1], "Color": curr['Color']}
        
    return last_signal

# --- MOTOR PRINCIPAL ---
def run_bot():
    print(f"--- START: {datetime.now()} ---")
    
    # Estructura para guardar el estado de cada activo
    # ticker -> { '1mo': 1/-1, '1wk': 1/-1, '1d': 1/-1, 'Details': {...} }
    market_state = {t: {} for t in TICKERS}
    
    # 1. ESCANEO Y CÁLCULO
    for interval, label, period in TIMEFRAMES:
        try:
            data = yf.download(TICKERS, interval=interval, period=period, group_by='ticker', progress=False, auto_adjust=True)
            for ticker in TICKERS:
                try:
                    df = data[ticker].dropna() if len(TICKERS)>1 else data.dropna()
                    if df.empty: continue
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                    # Obtener detalles completos (Señal, Fecha, Precio, ADX)
                    sig_data = get_signal_details(df)
                    
                    # Guardamos el estado (1 o -1) para el semáforo
                    market_state[ticker][interval] = sig_data['Color']
                    
                    # Si es Diario, guardamos los detalles para la ficha individual
                    if interval == '1d':
                        market_state[ticker]['Details'] = sig_data
                        
                except: pass
        except: pass

    # 2. GENERAR REPORTE CONSOLIDADO (Opción 1)
    full_bull, starting_bull, pullback, full_bear = [], [], [], []
    
    for t, d in market_state.items():
        if '1mo' not in d or '1wk' not in d or '1d' not in d: continue
        
        m, w, day = d['1mo'], d['1wk'], d['1d']
        price = d['Details']['Precio']
        
        line = f"• {t}: ${price:.2f}"
        
        if m==1 and w==1 and day==1: full_bull.append(line)
        elif m<=0 and w==1 and day==1: starting_bull.append(line)
        elif m==1 and w==1 and day==-1: pullback.append(line)
        elif m==-1 and w==-1 and day==-1: full_bear.append(line)

    # Enviar Reporte Semáforo
    report = f"📊 **MAPA DE MERCADO** ({datetime.now().strftime('%d/%m')})\n\n"
    if starting_bull: report += f"🌱 **OPORTUNIDAD (Nacimiento)**\n" + "\n".join(starting_bull) + "\n\n"
    if full_bull: report += f"🚀 **TENDENCIA FUERTE**\n" + "\n".join(full_bull) + "\n\n"
    if pullback: report += f"⚠️ **CORRECCIÓN (Atento)**\n" + "\n".join(pullback) + "\n\n"
    if full_bear: report += f"🩸 **BAJISTA (Full Bear)**\n" + "\n".join(full_bear[:10]) + (f"\n...y {len(full_bear)-10} más" if len(full_bear)>10 else "")
    
    send_message(report)
    time.sleep(2) # Pausa para que llegue primero el reporte

    # 3. ENVIAR FICHAS INDIVIDUALES (Opción 2 - Lo que pediste)
    # Filtramos: Solo enviamos fichas de lo "Interesante" (Nacimiento, Bull, Pullback). 
    # Ignoramos Full Bear para no spamear basura.
    
    interesting_tickers = [x.split(":")[0].replace("• ", "") for x in (starting_bull + full_bull + pullback)]
    
    for t in interesting_tickers:
        if t in market_state and 'Details' in market_state[t]:
            det = market_state[t]['Details']
            f_date = det['Fecha'].strftime('%d-%m-%Y')
            icon = "🚨" if "VENTA" in det['Tipo'] else "🚀"
            
            # Ficha Técnica exacta
            msg = (
                f"{icon} **{t} (DIARIO)**\n"
                f"**{det['Tipo']}**\n"
                f"Precio: ${det['Precio']:.2f}\n"
                f"ADX: {det['ADX']:.1f}\n"
                f"Fecha Señal: {f_date}"
            )
            send_message(msg)
            time.sleep(1) # Evitar bloqueo de Telegram por spam

if __name__ == "__main__":
    run_bot()
