HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Arbitrage Dashboard</title>
<script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>

<style>
body {
    margin:0;
    font-family: Arial;
    background: #0b0f19;
    color: white;
}

h2 {
    text-align:center;
    padding: 15px;
    color: #00ffcc;
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

.green {
    border-left: 5px solid #00ff6a;
}

.yellow {
    border-left: 5px solid #ffcc00;
}

.red {
    border-left: 5px solid #ff4d4d;
}

.symbol {
    font-size: 18px;
    font-weight: bold;
    color: #00d4ff;
}

.profit {
    font-size: 20px;
    font-weight: bold;
}

.small {
    font-size: 13px;
    color: #aaa;
}
</style>
</head>

<body>

<h2>🔥 Live Arbitrage Scanner</h2>
<div class="container" id="data"></div>

<script>
const socket = io();

socket.on("update", function(data) {
    let html = "";

    if(data.length === 0){
        html = "<p style='text-align:center;color:#aaa'>No opportunities</p>";
    }

    data.forEach(d => {

        let cls = "red";
        if(d.net_profit > 1) cls = "green";
        else if(d.net_profit > 0.6) cls = "yellow";

        html += `
        <div class="card ${cls}">
            <div class="symbol">${d.symbol}</div>
            <div>BUY: ${d.buy}</div>
            <div>SELL: ${d.sell}</div>

            <div class="profit">
                ${d.net_profit}%
            </div>

            <div class="small">
                💧 Buy Liquidity: ${d.buy_liquidity || d.sell_liquidity}<br>
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
