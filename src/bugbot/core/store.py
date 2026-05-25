import sqlite3, json, time, os
from typing import Dict, Any

DB_PATH = "data/bugbot.sqlite"
os.makedirs("data", exist_ok=True)

def _conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = _conn(); cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS signals(
        id INTEGER PRIMARY KEY,
        ts INTEGER,
        exchange TEXT,
        symbol TEXT,
        side TEXT,
        rule TEXT,
        score INTEGER,
        entry REAL,
        sl REAL,
        tp1 REAL,
        tp2 REAL,
        tp3 REAL,
        R REAL,
        reasons TEXT
    )""")
    con.commit(); con.close()

def save_signal(d: Dict[str, Any]) -> int:
    con = _conn(); cur = con.cursor()
    cur.execute("""INSERT INTO signals
      (ts,exchange,symbol,side,rule,score,entry,sl,tp1,tp2,tp3,R,reasons)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (int(time.time()), d.get("exchange"), d["symbol"], d["side"],
       d.get("rule","rules_v1"), int(d.get("score",0)),
       float(d["entry"]), float(d["sl"]),
       float(d["tp"][0]) if d.get("tp") else None,
       float(d["tp"][1]) if d.get("tp") and len(d["tp"])>1 else None,
       float(d["tp"][2]) if d.get("tp") and len(d["tp"])>2 else None,
       float(d.get("R", 0.0)),
       json.dumps(d.get("reasons", []))
      ))
    sid = cur.lastrowid
    con.commit(); con.close()
    return sid
