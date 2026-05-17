import requests
import time
import hmac
import hashlib
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

# Your existing config – make sure config.py exists with your API keys
from config import *

# ---------- Your existing constants & functions (keep them all) ----------
MIN_NET_PROFIT = 0.5
STARTING_USDT = 100
SCAN_DELAY = 5
CHECK_INTERVAL = 300
FALLBACK_TRADE_FEE = 0.001
FALLBACK_USDT_WD_FEE = 1.0

# ... (copy all your existing functions exactly as you have them: 
# sign_binance, gateio_headers, fetch_url, get_binance_fees, 
# get_gateio_fees, update_fees_status, get_all_tickers, 
# calc_cross_arb, print_opp, scan)

# ---------- FastAPI app ----------
app = FastAPI(title="Crypto Arbitrage Scanner")

class ArbitrageOpportunity(BaseModel):
    coin: str
    buy_ex: str
    sell_ex: str
    buy_price: float
    sell_price: float
    gross_percent: float
    gross_usd: float
    buy_fee: float
    sell_fee: float
    withdraw_fee: float
    fees_usd: float
    net_percent: float
    net_usd: float
    network: str
    buy_wd_ok: bool
    sell_dp_ok: bool

@app.get("/")
def root():
    return {"message": "Arbitrage Scanner API. Use /scan to get opportunities."}

@app.get("/scan", response_model=List[ArbitrageOpportunity])
def scan_endpoint():
    """Run one scan and return top opportunities as JSON."""
    update_fees_status()
    tickers = get_all_tickers()
    coins = set(tickers['binance'].keys()) & set(tickers['gateio'].keys())
    results = []
    for coin in coins:
        res = calc_cross_arb(coin, 'gateio', 'binance', tickers)
        if res:
            results.append(res)
        res = calc_cross_arb(coin, 'binance', 'gateio', tickers)
        if res:
            results.append(res)
    results.sort(key=lambda x: x['net_percent'], reverse=True)
    return results[:10]  # return top 10

# If you still want the continuous scanner when run directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
