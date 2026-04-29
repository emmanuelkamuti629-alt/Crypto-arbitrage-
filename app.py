from gevent import monkey
monkey.patch_all()

import time
import ccxt
import threading
import os
from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# =============================
# CONFIG
# =============================
symbols = ["BTC/USDT", "ETH/USDT"]

MIN_PROFIT = 1.2
FEE = 0.0015
MAX_AGE = 2
COOLDOWN = 6
RISK_PER_TRADE = 0.02   # 2% capital risk

ORDERBOOKS = {}
TRADE_HISTORY = []
EQUITY = []
CAPITAL = 1000

TRADE_LOCK = {}

# =============================
# EXCHANGES
# =============================
exchanges = {
    "kucoin": ccxt.kucoin(),
    "mexc": ccxt.mexc(),
    "gateio": ccxt.gateio(),
    "coinex": ccxt.coinex()
}

# =============================
# ORDERBOOK
# =============================
def update(ex, sym, bid, ask):
    ORDERBOOKS[f"{ex}:{sym}"] = {
        "bid": bid,
        "ask": ask,
        "time": time.time()
    }

# =============================
# DATA FEED
# =============================
def feed():
    while True:
        for name, ex in exchanges.items():
            for sym in symbols:
                try:
                    t = ex.fetch_ticker(sym)
                    if t["bid"] and t["ask"]:
                        update(name, sym, t["bid"], t["ask"])
                except:
                    continue
        time.sleep(0.6)

# =============================
# POSITION SIZE (REALISTIC)
# =============================
def position_size():
    return CAPITAL * RISK_PER_TRADE

# =============================
# TRADE EXECUTION (SIMULATED)
# =============================
def record_trade(symbol, buy_ex, sell_ex, buy, sell):
    global CAPITAL

    size = position_size()

    entry_cost = size
    exit_value = size * (sell / buy)

    gross = exit_value - entry_cost
    fees = (entry_cost + exit_value) * FEE

    net = gross - fees

    CAPITAL += net
    EQUITY.append(CAPITAL)

    trade = {
        "symbol": symbol,
        "buy": buy_ex,
        "sell": sell_ex,
        "buy_price": buy,
        "sell_price": sell,
        "size": round(size, 2),
        "net": round(net, 4),
        "capital": round(CAPITAL, 2),
        "time": time.time()
    }

    TRADE_HISTORY.append(trade)
    return trade

# =============================
# STATS
# =============================
def stats():
    if not TRADE_HISTORY:
        return {}

    wins = sum(1 for t in TRADE_HISTORY if t["net"] > 0)
    losses = len(TRADE_HISTORY) - wins
    total = sum(t["net"] for t in TRADE_HISTORY)

    return {
        "trades": len(TRADE_HISTORY),
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / len(TRADE_HISTORY)) * 100, 2),
        "profit": round(total, 2),
        "capital": round(CAPITAL, 2)
    }

# =============================
# ARBITRAGE ENGINE (SAFE)
# =============================
def scan():
    global TRADE_LOCK

    grouped = {}
    results = []
    now = time.time()

    for k, v in ORDERBOOKS.items():
        ex, sym = k.split(":")
        grouped.setdefault(sym, {})[ex] = v

    for sym, data in grouped.items():
        if len(data) < 2:
            continue

        buy_ex = min(data, key=lambda x: data[x]["ask"])
        sell_ex = max(data, key=lambda x: data[x]["bid"])

        b = data[buy_ex]
        s = data[sell_ex]

        if now - b["time"] > MAX_AGE or now - s["time"] > MAX_AGE:
            continue

        buy = b["ask"]
        sell = s["bid"]

        if sell <= buy:
            continue

        profit = ((sell - buy) / buy) * 100
        profit -= (FEE * 200)

        if profit < MIN_PROFIT:
            continue

        # 🔒 BIDIRECTIONAL COOLDOWN LOCK
        key = f"{sym}:{buy_ex}:{sell_ex}"
        reverse_key = f"{sym}:{sell_ex}:{buy_ex}"

        if (key in TRADE_LOCK and now - TRADE_LOCK[key] < COOLDOWN) or \
           (reverse_key in TRADE_LOCK and now - TRADE_LOCK[reverse_key] < COOLDOWN):
            continue

        TRADE_LOCK[key] = now

        trade = record_trade(sym, buy_ex, sell_ex, buy, sell)

        results.append({
            "symbol": sym,
            "buy": buy_ex,
            "sell": sell_ex,
            "profit": round(profit, 3),
            "net": trade["net"],
            "capital": trade["capital"],
            "size": trade["size"]
        })

    return sorted(results, key=lambda x: x["profit"], reverse=True)

# =============================
# PUSH
# =============================
def push():
    while True:
        socketio.emit("update", scan())
        socketio.emit("stats", stats())
        socketio.emit("equity", EQUITY[-50:])
        time.sleep(1)

threading.Thread(target=feed, daemon=True).start()
threading.Thread(target=push, daemon=True).start()

# =============================
# UI
# =============================
HTML = """
<!DOCTYPE html>
<html>
<head>
<script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
</head>
<body style="background:#000;color:#0f0;font-family:Arial;padding:20px">

<h2>🔥 PRO ARBITRAGE SIMULATOR</h2>

<div id="stats"></div>
<hr>
<div id="data"></div>
<hr>
<canvas id="chart" width="600" height="200"></canvas>

<script>
const socket = io();

socket.on("stats", s => {
document.getElementById("stats").innerHTML = `
TRADES: ${s.trades||0} |
WIN RATE: ${s.win_rate||0}% |
PROFIT: ${s.profit||0} |
CAPITAL: ${s.capital||1000}
`;
});

socket.on("update", data => {
let html = "";
data.forEach(x => {
html += `
<div style="margin:10px;padding:10px;border:1px solid #333">
${x.symbol}<br>
BUY: ${x.buy} → SELL: ${x.sell}<br>
PROFIT: <b>${x.profit}%</b><br>
NET: ${x.net}<br>
SIZE: ${x.size}
</div>`;
});
document.getElementById("data").innerHTML = html;
});

socket.on("equity", eq => {
const c = document.getElementById("chart");
const ctx = c.getContext("2d");

ctx.clearRect(0,0,600,200);
ctx.beginPath();

if(eq.length < 2) return;

let min = Math.min(...eq);
let max = Math.max(...eq);

for(let i=0;i<eq.length;i++){
let x = i * 10;
let y = 200 - ((eq[i]-min)/(max-min+0.0001))*200;
ctx.lineTo(x,y);
}

ctx.strokeStyle = "#0f0";
ctx.stroke();
});
</script>

</body>
</html>
"""

@app.route("/")
def home():
    return HTML

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
