diff --git a/src/bugbot/adapters/webhook.py b/src/bugbot/adapters/webhook.py
index 6822e70..8f06029 100644
--- a/src/bugbot/adapters/webhook.py
+++ b/src/bugbot/adapters/webhook.py
@@ -28,7 +28,12 @@ from fastapi import FastAPI, Request, HTTPException
 
 from ..config.settings import get_settings
 from ..config.logging import setup_logging
-from ..core.risk import calculate_contracts, CONTRACT_SPECS
+from ..core.risk import (
+    calculate_contracts,
+    calculate_contracts_dynamic,
+    CONTRACT_SPECS,
+)
+from ..adapters.data import fetch_ohlcv
 from ..core.journal import log_signal
 from ..core.formatting_v2 import fmt_signal
 from ..adapters.telegram import send_text
@@ -42,6 +47,13 @@ app = FastAPI(title="BugBot v2.0 Webhook", version="2.0")
 # NO en la URL (la URL puede quedar en logs/historial).
 WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
 
+# ─── Config SL/TP dinámico con ATR ───────────────────────────────
+# Timeframe y parámetros para el cálculo del ATR (ajustables por env).
+ATR_TIMEFRAME = os.getenv("ATR_TIMEFRAME", "5m")
+ATR_PERIOD    = int(os.getenv("ATR_PERIOD", "14"))
+ATR_MULT      = float(os.getenv("ATR_MULT", "1.0"))
+ATR_BARS      = int(os.getenv("ATR_BARS", "200"))
+
 VALID_SYMBOLS = {"MNQ", "MES", "MGC"}
 VALID_SIDES   = {"LONG", "SHORT"}
 
@@ -71,18 +83,12 @@ async def tradingview_webhook(request: Request):
         raise HTTPException(status_code=401, detail="token inválido")
 
     # 3. Normalizar y validar campos
+    #    El SL ya NO se lee del payload: lo calcula el bot con ATR dinámico.
+    #    Solo necesitamos symbol, side y entry del cruce del SMC.
     try:
         symbol = str(payload["symbol"]).upper().strip()
         side   = str(payload["side"]).upper().strip()
         entry  = float(payload["entry"])
-        # SL opcional: si no viene o es igual al entry (ej. {{close}}),
-        # lo calcula el bot con el default_stop del símbolo.
-        raw_sl = payload.get("sl")
-        if raw_sl is None or float(raw_sl) == entry:
-            stop_pts = CONTRACT_SPECS[symbol]["default_stop"]
-            sl = entry - stop_pts if side == "LONG" else entry + stop_pts
-        else:
-            sl = float(raw_sl)
     except (KeyError, ValueError, TypeError) as e:
         log.warning("payload incompleto/ inválido: %s | %s", payload, e)
         raise HTTPException(status_code=422, detail=f"campos faltantes o inválidos: {e}")
@@ -97,21 +103,37 @@ async def tradingview_webhook(request: Request):
     bias = str(payload.get("bias", side)).upper()
 
     s = get_settings()
-    log.info("ALERT %s %s entry=%.2f sl=%.2f zona=%s", symbol, side, entry, sl, zona)
+    log.info("ALERT %s %s entry=%.2f zona=%s (SL/TP dinámico ATR)", symbol, side, entry, zona)
+
+    # 4a. Bajar velas para el ATR. Si yfinance falla, descartamos y avisamos.
+    try:
+        df = fetch_ohlcv(symbol, timeframe=ATR_TIMEFRAME, bars=ATR_BARS)
+    except Exception as e:
+        log.exception("no se pudieron bajar velas para ATR")
+        send_text(
+            f"⚠️ {symbol} {side} descartado — sin datos para ATR "
+            f"({ATR_TIMEFRAME}). Detalle: {e}"
+        )
+        return {"status": "skipped", "reason": f"sin datos ATR: {e}"}
 
-    # 4. Risk Engine
+    # 4b. Risk Engine dinámico (SL y TP calculados desde el ATR)
     try:
-        risk = calculate_contracts(
+        risk = calculate_contracts_dynamic(
             symbol=symbol,
             account_size=s.account_size,
             entry=entry,
-            stop=sl,
             side=side,
+            df=df,
+            atr_period=ATR_PERIOD,
+            atr_mult=ATR_MULT,
         )
     except Exception as e:
-        log.exception("error en risk engine")
+        log.exception("error en risk engine dinámico")
         raise HTTPException(status_code=500, detail=f"risk engine: {e}")
 
+    # El SL dinámico calculado por el ATR (para journal / telegram)
+    sl = risk.stop
+
     if not risk.viable:
         log.info("%s | descartado por riesgo: %s", symbol, risk.reason)
         # Avisamos pero devolvemos 200: el alert llegó bien, solo no operamos.
@@ -123,11 +145,14 @@ async def tradingview_webhook(request: Request):
         "side": side, "entry": entry, "sl": sl,
         "zona": zona, "bias": bias, "event": zona,
     }
+    # Acceso seguro a los TP: algunos símbolos (ej. MES) tienen menos de 3.
+    _tp = [lvl.price for lvl in risk.tp_levels]
+    tp1 = _tp[0] if len(_tp) > 0 else None
+    tp2 = _tp[1] if len(_tp) > 1 else None
+    tp3 = _tp[2] if len(_tp) > 2 else None
     log_signal(
         symbol=symbol, side=side, entry=entry, sl=sl,
-        tp1=risk.tp_levels[0].price,
-        tp2=risk.tp_levels[1].price,
-        tp3=risk.tp_levels[2].price,
+        tp1=tp1, tp2=tp2, tp3=tp3,
         risk_usd=risk.risk_dollars,
         zona=zona, bias=bias,
         session="TV",
diff --git a/src/bugbot/core/risk.py b/src/bugbot/core/risk.py
index 9755306..7b75260 100644
--- a/src/bugbot/core/risk.py
+++ b/src/bugbot/core/risk.py
@@ -185,7 +185,9 @@ EXIT_PLANS = {
         {"name": "TP3", "r_multiple": 4, "contracts": 1},  # 1 contrato en 4R
     ],
     "MGC": [
-        {"name": "TP2", "r_multiple": 2, "contracts": 1},  # 1 contrato en 2R
+        {"name": "TP1", "r_multiple": 1, "contracts": 1},  # 1R
+        {"name": "TP2", "r_multiple": 2, "contracts": 1},  # 2R
+        {"name": "TP3", "r_multiple": 3, "contracts": 1},  # 3R
     ],
 }
