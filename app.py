import asyncio
import ccxt.async_support as ccxt
import time
import threading
from flask import Flask
from flask_socketio import SocketIO
import random

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# =============================
# CONFIG
# =============================
MIN_PROFIT = 0.15
FEE = 0.0015
SLEEP = 1

exchanges = {
    "kucoin": ccxt.kucoin(),
    "mexc": ccxt.mexc(),
    "gateio": ccxt.gateio(),
    "coinex": ccxt.coinex()
}

orderbooks = {}
symbols = []

# =============================
# LOAD SYMBOLS
# =============================
async def load_symbols():
    global symbols
    common = None

    for name, ex in exchanges.items():
        markets = await ex.load_markets()

        pairs = {
            s for s in markets
            if s.endswith("/USDT") and markets[s]["active"]
        }

        common = pairs if common is None else common & pairs

    symbols = list(common)
    print("Loaded symbols:", len(symbols))

# =============================
# WORKER (STABLE STREAM)
# =============================
async def worker(ex_name, ex, worker_id):
    i = worker_id

    while True:
        if not symbols:
            await asyncio.sleep(3)
            continue

        try:
            sym = symbols[i % len(symbols)]

            book = await ex.fetch_order_book(sym, 5)

            bids = book["bids"]
            asks = book["asks"]

            if not bids or not asks:
                continue

            orderbooks[(ex_name, sym)] = {
                "bid": bids[0][0],
                "bid_vol": bids[0][1],
                "ask": asks[0][0],
                "ask_vol": asks[0][1],
                "time": time.time()
            }

            i += 5

        except:
            pass

        await asyncio.sleep(SLEEP + random.uniform(0, 0.5))

# =============================
# SCANNER (PRO LOGIC)
# =============================
def scan():
    results = []
    grouped = {}
    now = time.time()

    for (ex, sym), data in orderbooks.items():
        grouped.setdefault(sym, {})[ex] = data

    for sym, data in grouped.items():
        if len(data) < 2:
            continue

        buy_ex = min(data, key=lambda x: data[x]["ask"])
        sell_ex = max(data, key=lambda x: data[x]["bid"])

        buy = data[buy_ex]["ask"]
        sell = data[sell_ex]["bid"]

        # stale filter
        if now - data[buy_ex]["time"] > 3:
            continue
        if now - data[sell_ex]["time"] > 3:
            continue

        # liquidity check (PRO FEATURE)
        if data[buy_ex]["ask_vol"] < 1 or data[sell_ex]["bid_vol"] < 1:
            continue

        profit = ((sell - buy) / buy) * 100
        profit -= FEE * 200

        if profit >= MIN_PROFIT:
            results.append({
                "symbol": sym,
                "buy": buy_ex,
                "sell": sell_ex,
                "profit": round(profit, 3)
            })

    return sorted(results, key=lambda x: x["profit"], reverse=True)[:20]

# =============================
# ENGINE
# =============================
async def engine():
    await load_symbols()

    tasks = []

    for ex_name, ex in exchanges.items():
        for w in range(3):  # controlled workers
            tasks.append(worker(ex_name, ex, w))

    await asyncio.gather(*tasks)

# =============================
# PUSH
# =============================
def push():
    while True:
        socketio.emit("update", scan())
        time.sleep(1)

# =============================
# RUN
# =============================
@app.route("/")
def home():
    return "PRO ARBITRAGE ENGINE ACTIVE"

if __name__ == "__main__":
    threading.Thread(target=push, daemon=True).start()

    loop = asyncio.new_event_loop()
    threading.Thread(target=lambda: loop.run_until_complete(engine()), daemon=True).start()

    socketio.run(app, host="0.0.0.0", port=5000)
