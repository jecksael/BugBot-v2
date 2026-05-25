from typing import Tuple, List

def make_targets(side: str, entry: float, atr: float, k_atr: float = 1.2,
                 steps: tuple = (1, 2, 3)) -> tuple[float, list[float], float]:
    if side == "long":
        sl = entry - k_atr * atr
        R = entry - sl
        tps = [entry + m * R for m in steps]
    else:
        sl = entry + k_atr * atr
        R = sl - entry
        tps = [entry - m * R for m in steps]
    return sl, tps, R
