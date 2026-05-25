from dataclasses import dataclass
from typing import List, Literal

Side = Literal["long", "short"]

@dataclass
class Signal:
    ts_utc: str
    exchange: str
    symbol: str
    timeframe: str
    rule: str
    side: Side
    reasons: List[str]
    entry: float
    sl: float
    tp: List[float]
    R: float
    score: float = 0.0