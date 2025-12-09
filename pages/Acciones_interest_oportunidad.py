import streamlit as st
import yfinance as yf
import pandas as pd
import time

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader: Scanner de Lotes")

# --- BASE DE DATOS (CEDEARS / USA) ---
CEDEAR_DATABASE = sorted([
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'AMD', 'NFLX', 
    'GGAL', 'YPF', 'BMA', 'PAMP', 'TGS', 'CEPU', 'EDN', 'BFR', 'SUPV', 'MELI',
    'KO', 'PEP', 'MCD', 'SBUX', 'DIS', 'XOM', 'CVX', 'JPM', 'BAC', 'C', 'WFC',
    'SPY', 'QQQ', 'IWM', 'EEM', 'XLE', 'XLF', 'GLD', 'SLV', 'ARKK'
])

# --- FUNCIÓN DE ANÁLISIS ---
def analyze_ticker_safe(ticker):
    log = {
        "Ticker": ticker, 
        "Precio": 0.0, 
        "Call Wall": 0.0, 
        "Proximidad %": 0.0,
        "Status": "Pendiente", 
        "Info": ""
    }
    
    try:
        # 1. OBTENER DATOS (Sin pasar session custom para evitar error curl_cffi)
        tk = yf.Ticker(ticker)
        
        # Historial corto para precio actual (Fastest way)
        hist = tk.history(period="1d")
        
        if hist.empty:
            log["Status"] = "❌ Sin Datos"
            return log
            
        current_price = hist['Close'].iloc[-1]
        log["Precio"] = round(float(current_price), 2)

        # 2. PROCESAR OPCIONES (Detectar Muro de Calls)
        exps = tk.options
        if not exps:
            log["Status"] = "⚠️ Sin Opciones"
            return log

        # Buscamos en el vencimiento más próximo
        # (Si falla el primero, intenta el segundo por si el primero vence hoy mismo)
        found_data = False
        for date in exps[:2]:
            try:
                opt = tk.option_chain(date)
                calls = opt.calls
                
                if not calls.empty:
                    # Encontrar el Strike con mayor Open Interest (Call Wall)
                    max_oi_row = calls.loc[calls['openInterest'].idxmax()]
                    call_wall = max_oi_row['strike']
                    call_oi = max_oi_row['openInterest']
                    
                    log["Call Wall"] = call_wall
                    
                    # CÁLCULO DE PROXIMIDAD
                    # Qué tan lejos está el precio del Call Wall
                    # Negativo = Precio debajo del muro / Positivo = Precio cruzó el muro
                    dist_pct = ((current_price - call_wall) / call_wall) * 100
                    
                    log["Proximidad %"] = round(dist_pct, 2)
                    log["Info"] = f"OI: {int(call_oi)} @ {date}"
                    log["Status"] = "✅ OK"
                    found_data = True
                    break
            except Exception:
                continue
        
        if not found_data:
            log["Status"] = "⚠️ Cadena Vacía"

    except Exception as e:
        log["Status"] = "🔥 Error"
        log["Info"] = str(e)[0:50] # Recortar mensaje de error
        
    return log

# --- INTERFAZ STREAMLIT ---
st.title("📡 SystemaTrader: Escáner por Lotes")
st.markdown("Este modo permite escanear acciones en grupos pequeños para evitar bloqueos de Yahoo Finance.")

# Inicializar almacenamiento en sesión
if "scan_data" not in st.session_state:
    st.session_state["scan_data"] = []

# --- BARRA LATERAL: CONTROL DE LOTES ---
with st.sidebar:
    st.header("🎮 Centro de Control")
    
    # Tamaño del lote
    batch_size = st.slider("Tamaño del Lote", min_value=1, max_value=10, value=3, help="Menos es más seguro contra bloqueos.")
    
    # Crear los grupos
    batches = [CEDEAR_DATABASE[i:i + batch_size] for i in range(0, len(CEDEAR_DATABASE), batch_size)]
    batch_options = [f"Lote {i+1} ({b[0]}...{b[-1]})" for i, b in enumerate(batches)]
    
    selected_batch_index = st.selectbox("Seleccionar Lote a procesar:", range(len(batches)), format_func=lambda x: batch_options[x])
    
    col1, col2 = st.columns(2)
    
    run_btn = col1.button("▶️ Escanear Lote", type="primary")
    clear_btn = col2.button("🗑️ Borrar Todo")

    if clear_btn:
        st.session_state["scan_data"] = []
        st.rerun()

    st.info(f"Total acumulado: {len(st.session_state['scan_data'])} acciones.")

# --- LÓGICA DE EJECUCIÓN ---
if run_btn:
    targets = batches[selected_batch_index]
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Verificar duplicados para no procesar lo mismo dos veces si el usuario cliquea de nuevo
    existing_tickers = [d['Ticker'] for d in st.session_state["scan_data"]]
    
    for i, ticker in enumerate(targets):
        # Si ya lo tenemos, lo saltamos o lo actualizamos (aquí elegimos saltar para ahorrar llamadas)
        if ticker in existing_tickers:
            status_text.warning(f"{ticker} ya está en la lista. Saltando...")
            time.sleep(0.1)
            continue
            
        status_text.text(f"⏳ Consultando {ticker} en Yahoo Finance...")
        
        # Llamada a la función
        data = analyze_ticker_safe(ticker)
        
        # Guardar
        st.session_state["scan_data"].append(data)
        
        # Barra de progreso
        progress_bar.progress((i + 1) / len(targets))
        
        # Pausa anti-bloqueo (Importante)
        time.sleep(1) 
    
    status_text.success("✅ Lote completado exitosamente.")
    time.sleep(1)
    status_text.empty()
    st.rerun()

# --- MOSTRAR RESULTADOS ---
st.subheader("📊 Tablero de Control Acumulado")

if st.session_state["scan_data"]:
    df = pd.DataFrame(st.session_state["scan_data"])
    
    # Reordenar columnas
    cols = ["Ticker", "Precio", "Call Wall", "Proximidad %", "Status", "Info"]
    df = df[cols]
    
    # Estilos Condicionales
    def style_proximity(val):
        """
        Rojo: Muy cerca del muro (posible resistencia).
        Verde: Lejos del muro (espacio para correr).
        """
        if isinstance(val, (int, float)):
            if abs(val) < 2.0: # A menos de un 2% del muro
                return 'color: #ff4b4b; font-weight: bold' 
            elif val > 0: # Rompió el muro
                return 'color: #00c853; font-weight: bold'
        return ''

    def style_status(val):
        if val == "✅ OK": return 'color: lightgreen'
        if "Error" in val: return 'color: red'
        return 'color: orange'

    st.dataframe(
        df.style.map(style_proximity, subset=['Proximidad %'])
                .map(style_status, subset=['Status'])
                .format({"Precio": "${:.2f}", "Call Wall": "${:.2f}", "Proximidad %": "{:.2f}%"}),
        use_container_width=True,
        height=500
    )
    
    # Métricas rápidas
    total_ok = len(df[df['Status'] == "✅ OK"])
    st.caption(f"Acciones escaneadas correctamente: {total_ok} / {len(df)}")

else:
    st.info("👋 Selecciona un lote en el menú lateral y presiona 'Escanear' para comenzar a acumular datos.")
