name: Bot de Alertas HA+ADX

on:
  schedule:
    # Horarios UTC (Lunes a Viernes)
    # 14:30 UTC = 11:30 AM Argentina (Apertura)
    # 17:00 UTC = 02:00 PM Argentina (Medio día)
    # 20:00 UTC = 05:00 PM Argentina (Cierre)
    - cron: '30 14 * * 1-5'
    - cron: '00 17 * * 1-5'
    - cron: '00 20 * * 1-5'
  workflow_dispatch: # Botón para ejecutar manual si quieres probar

jobs:
  run-bot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      
      - name: Instalar librerías
        run: pip install yfinance pandas pandas_ta requests numpy

      - name: Correr Robot
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python bot_telegram.py
