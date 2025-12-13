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
    ("1mo", "1mo", "max"),  # Mes
    ("1wk", "1wk", "10y"),  # Semana
    ("1d", "1d", "5y")      # Día
]

ADX_TH = 20

# --- LISTA DE ACTIVOS COMPLETA ---
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
    
    # Telegram tiene un límite de 4096 caracteres por mensaje.
    # Si el reporte es muy largo, hay que partirlo.
    max_len = 4000
    if len(msg) <= max_len:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        # Dividir mensaje en partes
        parts = [msg[i:i+max_len] for i in range(0, len(msg), max_len)]
        for part in parts:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": CHAT_ID, "text": part, "parse_mode": "Markdown"})
            time.sleep(1)

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

# --- MOTOR PRINCIPAL ---
def run_bot():
    print(f"--- START: {datetime.now()} ---")
    
    # Memoria del estado de mercado
    market_state = {t: {} for t in TICKERS}
    
    # 1. ESCANEO MASIVO
    for interval, label_key, period in TIMEFRAMES:
        try:
            data = yf.download(TICKERS, interval=interval, period=period, group_by='ticker', progress=False, auto_adjust=True)
            for ticker in TICKERS:
                try:
                    df = data[ticker].dropna() if len(TICKERS)>1 else data.dropna()
                    if df.empty: continue
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                    # Indicadores
                    df['ADX'] = calculate_adx(df)
                    df_ha = calculate_heikin_ashi(df)
                    
                    # Guardamos datos de la última vela cerrada/actual
                    last = df_ha.iloc[-1]
                    prev = df_ha.iloc[-2]
                    
                    # Guardamos Estado (1 Verde, -1 Rojo) y Datos
                    market_state[ticker][label_key] = {
                        'Color': last['Color'],
                        'Prev_Color': prev['Color'], # Para detectar cambios recientes
                        'Price': last['Close'],
                        'ADX': last['ADX']
                    }
                except: pass
        except: pass

    # 2. CONSTRUCCIÓN DEL REPORTE DETALLADO
    # Categorías
    full_bull = []      # M+ S+ D+
    starting_bull = []  # S+ D+ (Mes recuperando)
    pullback = []       # M+ S+ D- (Oportunidad)
    full_bear = []      # M- S- D-
    mixed = []          # Ruido
    
    # Iconos
    icon_map = {1: "🟢", -1: "🔴", 0: "⚪"}

    for t, data in market_state.items():
        if '1mo' not in data or '1wk' not in data or '1d' not in data: continue
        
        m_col = data['1mo']['Color']
        w_col = data['1wk']['Color']
        d_col = data['1d']['Color']
        
        price = data['1d']['Price']
        adx_d = data['1d']['ADX']
        
        # Etiqueta Visual de la Matrioska: [M🟢 S🔴 D🟢]
        visual_matrix = f"[{icon_map[m_col]} {icon_map[w_col]} {icon_map[d_col]}]"
        
        # Detectar si la señal diaria es NUEVA (De ayer a hoy)
        is_new_signal = (data['1d']['Prev_Color'] != d_col)
        new_tag = "🆕 " if is_new_signal else ""
        
        line = f"{new_tag}**{t}:** ${price:.2f} {visual_matrix} (ADX {adx_d:.0f})"
        
        # CLASIFICACIÓN
        if m_col == 1 and w_col == 1 and d_col == 1:
            full_bull.append(line)
        elif m_col == -1 and w_col == 1 and d_col == 1:
            starting_bull.append(line)
        elif m_col == 1 and w_col == 1 and d_col == -1:
            pullback.append(line)
        elif m_col == -1 and w_col == -1 and d_col == -1:
            full_bear.append(line)
        else:
            mixed.append(line)

    # 3. ENVÍO DEL MENSAJE (Sin censura)
    report = f"📊 **INFORME COMPLETO** ({datetime.now().strftime('%d/%m')})\n"
    report += "Leyenda: [Mes Sem Dia]\n\n"
    
    if starting_bull:
        report += f"🌱 **NACIMIENTO DE TENDENCIA (Oportunidad)**\n" + "\n".join(starting_bull) + "\n\n"
        
    if full_bull:
        report += f"🚀 **TENDENCIA ALCISTA (Full Bull)**\n" + "\n".join(full_bull) + "\n\n"
        
    if pullback:
        report += f"⚠️ **CORRECCIÓN / PULLBACK (Atentos)**\n" + "\n".join(pullback) + "\n\n"
        
    if full_bear:
        report += f"🩸 **TENDENCIA BAJISTA (Full Bear)**\n" + "\n".join(full_bear) + "\n\n"
        
    # Descomentar si quieres ver también los activos en rango/ruido
    # if mixed:
    #    report += f"💤 **LATERAL / RUIDO**\n" + "\n".join(mixed) + "\n\n"
    
    send_message(report)

if __name__ == "__main__":
    run_bot()
