import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="SystemaTrader - Radar MERVAL")

# --- BASE DE DATOS ARGENTINA ---

# Diccionario: Clave = Ticker Analizado (USD si es ADR), Valor = Ticker Local (BCBA)
# Priorizamos el ADR para el cálculo estadístico (Moneda Dura)
ADR_MAPPING = {
    'GGAL': 'GGAL',   'BMA': 'BMA',     'YPF': 'YPFD',    'PAMP': 'PAMP',
    'TGS': 'TGSU2',   'CEPU': 'CEPU',   'EDN': 'EDN',     'BFR': 'BBAR',
    'SUPV': 'SUPV',   'CRESY': 'CRES',  'IRS': 'IRSA',    'LOMA': 'LOMA',
    'TEO': 'TECO2',   'DESP': 'DESP'
}

# Acciones puramente locales (Análisis en PESOS - Riesgo Inflacionario)
LOCAL_ONLY = [
    'ALUA.BA', 'TXAR.BA', 'COME.BA', 'VALO.BA', 'BYMA.BA', 
    'CVH.BA', 'TGNO4.BA', 'TRAN.BA', 'MIRG.BA', 'AGRO.BA', 'LEDE.BA'
]

# Definición de Sectores (Manual SystemaTrader)
SECTOR_DATA = {
    'Bancos (ADRs)': ['GGAL', 'BMA', 'BFR', 'SUPV'],
    'Energía & Oil (ADRs)': ['YPF', 'PAMP', 'TGS', 'CEPU', 'EDN'],
    'Materiales & Agro': ['LOMA', 'TXAR.BA', 'ALUA.BA', 'AGRO.BA', 'LEDE.BA'],
    'Real Estate & Otros': ['CRESY', 'IRS', 'TEO', 'DESP'],
    'Panel General/Local (ARS)': ['COME.BA', 'VALO.BA', 'BYMA.BA', 'CVH.BA', 'TGNO4.BA', 'TRAN.BA', 'MIRG.BA']
}

MONTH_NAMES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
MONTH_DICT = {name: i+1 for i, name in enumerate(MONTH_NAMES)}

# --- FUNCIONES ---
@st.cache_data
def get_merval_stats(tickers, start_year=2010):
    start_date = f"{start_year}-01-01"
    try:
        # Descarga masiva
        data = yf.download(tickers, start=start_date, progress=False, group_by='ticker', auto_adjust=True)
    except Exception: return pd.DataFrame()

    stats_list = []
    # Manejo de estructura de yfinance
    if len(tickers) == 1: data_dict = {tickers[0]: data}
    else: data_dict = {t: data[t] for t in tickers}

    for ticker in tickers:
        try:
            if ticker not in data_dict: continue
            df = data_dict[ticker]
            if 'Close' not in df.columns: continue
            
            # Resampleo Mensual
            monthly_ret = df['Close'].resample('M').last().pct_change() * 100
            monthly_ret = monthly_ret.dropna()
            
            temp_df = pd.DataFrame(monthly_ret)
            temp_df.columns = ['Return']
            temp_df['Month'] = temp_df.index.month
            
            # Métricas de Riesgo
            def avg_win(x): return x[x > 0].mean() if len(x[x > 0]) > 0 else 0
            def avg_loss(x): return x[x < 0].mean() if len(x[x < 0]) > 0 else 0
            
            grouped = temp_df.groupby('Month')['Return'].agg([
                'mean', 'median', 'count', 
                lambda x: (x > 0).mean() * 100,
                avg_win,
                avg_loss
            ])
            grouped.columns = ['Avg_Return', 'Median_Return', 'Years', 'Win_Rate', 'Avg_Win', 'Avg_Loss']
            
            # Determinar si es ADR (Dólar) o Local (Peso)
            is_adr = ticker in ADR_MAPPING
            currency = "USD 💵" if is_adr else "ARS 💸"
            
            for m in range(1, 13):
                if m in grouped.index:
                    stats_list.append({
                        'Ticker': ticker,
                        'Currency': currency,
                        'Month_Num': m,
                        'Month_Name': MONTH_NAMES[m-1],
                        'Avg_Return': grouped.loc[m, 'Avg_Return'],
                        'Win_Rate': grouped.loc[m, 'Win_Rate'],
                        'Avg_Win': grouped.loc[m, 'Avg_Win'],
                        'Avg_Loss': grouped.loc[m, 'Avg_Loss'],
                        'Years': grouped.loc[m, 'Years']
                    })
        except Exception: continue
            
    return pd.DataFrame(stats_list)

def generate_bcba_link(ticker_analizado):
    """Genera link al ticker local en BCBA"""
    # Si analizamos GGAL (ADR), el link va a GGAL (Local)
    # Si analizamos COME.BA, limpiamos el .BA para el link
    
    if ticker_analizado in ADR_MAPPING:
        local_ticker = ADR_MAPPING[ticker_analizado]
    else:
        local_ticker = ticker_analizado.replace('.BA', '')
        
    return f"https://es.tradingview.com/chart/?symbol=BCBA%3A{local_ticker}"

# --- INTERFAZ ---
st.title("🇦🇷 SystemaTrader: Radar Estacional MERVAL")
st.markdown("""
**Nota Técnica:** 
*   Los activos marcados como **USD 💵** se analizan vía ADR (Hard Currency) para evitar distorsión inflacionaria.
*   Los activos marcados como **ARS 💸** se analizan en pesos (Cuidado con la inflación).
""")

with st.sidebar:
    st.header("Configuración")
    start_year = st.number_input("Año Inicio:", 2000, 2024, 2010)
    selected_month = st.selectbox("Mes Objetivo:", MONTH_NAMES, index=datetime.now().month - 1)

# --- FASE 1: SECTORES ---
st.subheader(f"1️⃣ Panorama Sectorial Argentino: {selected_month}")

if st.button("Escanear Merval"):
    with st.spinner("Analizando volatilidad argentina..."):
        # Aplanamos la lista de todos los tickers
        all_tickers = [t for sector in SECTOR_DATA.values() for t in sector]
        df_all = get_merval_stats(all_tickers, start_year)
        
        if not df_all.empty:
            month_num = MONTH_DICT[selected_month]
            df_month = df_all[df_all['Month_Num'] == month_num].copy()
            
            # Asignar Sector al DataFrame
            def get_sector(t):
                for sec_name, ticks in SECTOR_DATA.items():
                    if t in ticks: return sec_name
                return "Otros"
            
            df_month['Sector'] = df_month['Ticker'].apply(get_sector)
            
            # Agrupar por sector para el gráfico Macro
            sector_stats = df_month.groupby('Sector').agg({
                'Win_Rate': 'mean',
                'Avg_Return': 'mean',
                'Avg_Win': 'mean',
                'Avg_Loss': 'mean'
            }).reset_index()
            
            st.session_state['df_merval_month'] = df_month
            
            # Scatter Plot Sectorial
            fig = px.scatter(
                sector_stats, x="Avg_Return", y="Win_Rate", size="Win_Rate",
                color="Sector", text="Sector", hover_name="Sector",
                title=f"Sectores Merval en {selected_month} (Promedio)",
                range_y=[0, 105]
            )
            fig.add_hline(y=60, line_dash="dot", annotation_text="Zona Neutra Merval")
            fig.add_vline(x=0, line_color="white")
            st.plotly_chart(fig, use_container_width=True)
            
            # Risk/Reward Bars
            st.markdown("#### ⚖️ Riesgo vs Beneficio (Promedio del Sector)")
            df_risk = sector_stats[['Sector', 'Avg_Win', 'Avg_Loss']].melt(
                id_vars='Sector', value_vars=['Avg_Win', 'Avg_Loss'],
                var_name='Metric', value_name='Percent'
            )
            fig_risk = px.bar(
                df_risk, x='Sector', y='Percent', color='Metric',
                barmode='group', color_discrete_map={'Avg_Win': '#00CC96', 'Avg_Loss': '#EF553B'}
            )
            st.plotly_chart(fig_risk, use_container_width=True)

# --- FASE 2: ACTIVOS ---
st.divider()
st.subheader("2️⃣ Selección de Papeles (Panel Líder/General)")

if 'df_merval_month' in st.session_state:
    df_m = st.session_state['df_merval_month']
    
    # Selector de Sector
    sectores = list(SECTOR_DATA.keys())
    target_sector = st.selectbox("Filtrar por Sector:", sectores, index=0)
    
    # Filtrar Data
    df_filtered = df_m[df_m['Sector'] == target_sector].copy()
    df_filtered['Label'] = df_filtered['Ticker'] + " (" + df_filtered['Currency'] + ")"
    df_filtered = df_filtered.sort_values('Win_Rate', ascending=False)
    
    if not df_filtered.empty:
        # Scatter
        fig_s = px.scatter(
            df_filtered, x="Avg_Return", y="Win_Rate", color="Avg_Win",
            size="Win_Rate", text="Label", color_continuous_scale="Greens",
            title=f"Detalle: {target_sector}"
        )
        fig_s.update_traces(textposition='top center')
        fig_s.add_hline(y=70, line_dash="dash", line_color="green")
        st.plotly_chart(fig_s, use_container_width=True)
        
        # Tabla Ejecución
        df_filtered['Link'] = df_filtered['Ticker'].apply(generate_bcba_link)
        
        st.dataframe(
            df_filtered[['Ticker', 'Currency', 'Win_Rate', 'Avg_Return', 'Avg_Win', 'Avg_Loss', 'Link']],
            column_config={
                "Link": st.column_config.LinkColumn("BCBA", display_text="Ver Local 🇦🇷"),
                "Win_Rate": st.column_config.NumberColumn("Probabilidad", format="%.1f%%"),
                "Avg_Return": st.column_config.NumberColumn("Retorno Prom", format="%.2f%%"),
                "Avg_Win": st.column_config.NumberColumn("Ganancia Prom", format="%.2f%%"),
                "Avg_Loss": st.column_config.NumberColumn("Pérdida Prom", format="%.2f%%")
            },
            hide_index=True, use_container_width=True
        )
    else:
        st.warning("No hay datos para este sector.")
else:
    st.info("Ejecuta el Escaneo primero.")
