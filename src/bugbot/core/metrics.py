from collections import Counter

signals_emitted = Counter()   # por símbolo
reasons_blocked = Counter()   # por motivo de bloqueo
from collections import Counter

signals_emitted = Counter()   # por símbolo
reasons_blocked = Counter()   # por motivo de bloqueo

def bump_signal(symbol: str):
    signals_emitted[symbol] += 1

def bump_reason(reason: str):
    # normaliza lo que nos llega: "atr_filter=false", "ema_cross_1h=no_signal", etc.
    reasons_blocked[reason] += 1

def snapshot(topn: int = 8) -> dict:
    return {
        "signals": signals_emitted.most_common(topn),
        "blocks": reasons_blocked.most_common(topn),
    }

def bump_signal(symbol: str):
    signals_emitted[symbol] += 1

def bump_reason(reason: str):
    # normaliza lo que nos llega: "atr_filter=false", "ema_cross_1h=no_signal", etc.
    reasons_blocked[reason] += 1

def snapshot(topn: int = 8) -> dict:
    return {
        "signals": signals_emitted.most_common(topn),
        "blocks": reasons_blocked.most_common(topn),
    }
