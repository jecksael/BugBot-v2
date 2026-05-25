# BUG Trading Bot

Bot de trading modular para generar y (opcional) publicar señales en Telegram.  
Actualmente incluye:

- **Escáner por consola** (sin Telegram) con *failover* de exchanges.
- Estrategia simple: **cruce de EMAs** (rápida vs lenta).
- Parametrización por **.env** (exchanges, símbolos, timeframe, TP/SL).
- Cliente de exchange con **CCXT** y resolución automática de símbolos (BTC/XBT).

---

## 📦 Requisitos

- Python 3.11+
- Windows PowerShell (o bash)  
- Dependencias: `ccxt`, `pandas`, `numpy`, `python-dotenv`, `pytest`

