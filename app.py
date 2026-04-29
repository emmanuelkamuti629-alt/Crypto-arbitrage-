from flask import Flask
from flask_socketio import SocketIO, emit
import random
import time
from threading import Thread

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Arbitrage Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>

<style>
body {
    margin:0;
    font-family: Arial, sans-serif;
    background: #0b0f19;
    color: white;
}
h2 {
    text-align:center;
    padding: 15px;
    color: #00ffcc;
    margin: 0;
}
.container {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    padding: 10px;
}
.card {
    width: 320px;
    margin: 10px;
    padding: 15px;
    border-radius: 12px;
    background: #111827;
    box-shadow: 0 0 10px rgba(0,255,200,0.1);
    transition: 0.3s;
}
.card:hover {
    transform: scale(1.03);
    box-shadow: 0 0 20px rgba(0,255,200,0.3);
}
.green { border-left: 5px solid #00ff6a; }
.yellow { border-left: 5px solid #ffcc00; }
.red { border-left: 5px solid #ff4d4d; }
.symbol {
    font-size: 18px;
    font-weight: bold;
    color: #00d4ff;
    margin-bottom: 8px;
}
.profit {
    font-size: 20px;
    font-weight: bold;
    margin: 8px 0;
}
.small {
    font-size: 13px;
    color: #aaa;
    line-height: 1.5;
}
.status {
    text-align: center;
    color: #00ffcc;
    font-size: 12px;
    padding-bottom: 10px;
}
</style>
</head>
<body>
<h2>🔥 Live Arbitrage Scanner</h2>
<div class="status" id="status">Connecting...</div>
<div class="container" id="data">
    <p style='text-align:center;color:#aaa'>Waiting for data...</p>
</div>

<script>
const socket = io({
    transports: ['websocket', 'polling']
});

socket.on("connect", () => {
    document.getElementById("status").innerText = "PRO ARBITRAGE ENGINE ACTIVE";
});

socket.on("connect_error", (err) => {
    document.getElementById("status").innerText = "Connection error. Retrying...";
    console.log("Socket error:", err);
});

socket.on("update", function(data) {
    let html = "";
    if(data.length === 0){
        html = "<p style='text-align:center;color:#aaa'>No opportunities found</p>";
    }

    data.forEach(d => {
        let cls = "red";
        if(d.net_profit > 1) cls = "green";
        else if(d.net_profit > 0.6) cls = "yellow";

        html += `
        <div class="card ${cls}">
            <div class="symbol">${d.symbol}</div>
            <div>BUY: ${d.buy} @ $${d.buy_price}</div>
            <div>SELL: ${d.sell} @ $${d.sell_price}</div>
            <div class="profit">${d.net_profit}%</div>
            <div class="small">
                💧 Buy Liquidity: $${d.buy_liquidity}<br>
                🔓 Withdraw: ${d.buy_withdraw}<br>
                🔐 Deposit: ${d.sell_deposit}
            </div>
        </div>`;
    });
    document.getElementById("data").innerHTML = html;
});
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return HTML

# Fake data generator - replace this with your real arbitrage logic
def generate_arbitrage_data():
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    exchanges = ["Binance", "KuCoin", "Bybit", "OKX", "Gate.io"]
    
    data = []
    for _ in range(random.randint(0, 6)):
        buy_ex = random.choice(exchanges)
        sell_ex = random.choice([e for e in exchanges if e != buy_ex])
        base_price = random.uniform(20000, 60000)
        spread = random.uniform(0.1, 2.5)
        
        data.append({
            "symbol": random.choice(symbols),
            "buy": buy_ex,
            "sell": sell_ex,
            "buy_price": round(base_price, 2),
            "sell_price": round(base_price * (1 + spread/100), 2),
            "net_profit": round(spread - 0.2, 2),  # minus fees
            "buy_liquidity": f"{random.uniform(0.5, 10):.1f}M",
            "sell_liquidity": f"{random.uniform(0.5, 10):.1f}M",
            "buy_withdraw": random.choice(["OK", "Slow", "OK"]),
            "sell_deposit": random.choice(["OK", "OK", "Delayed"])
        })
    
    # Sort by profit desc
    return sorted(data, key=lambda x: x["net_profit"], reverse=True)

def background_task():
    """Send fake data every 3 seconds. Replace with your real scanner."""
    while True:
        socketio.sleep(3)
        data = generate_arbitrage_data()
        socketio.emit("update", data)

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit("update", generate_arbitrage_data())

if __name__ == '__main__':
    thread = Thread(target=background_task)
    thread.daemon = True
    thread.start()
    socketio.run(app, host='0.0.0.0', port=10000)
