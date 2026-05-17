import requests
import time
import hmac
import hashlib
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
from config import *

MIN_NET_PROFIT = 0.5
STARTING_USDT = 100
SCAN_DELAY = 5
CHECK_INTERVAL = 300

FALLBACK_TRADE_FEE = 0.001
FALLBACK_USDT_WD_FEE = 1.0

class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    END = '\033[0m'

FEES_CACHE = {}
STATUS_CACHE = {}
LAST_UPDATE = 0

def sign_binance(params, secret):
    query_string = urlencode(params)
    signature = hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    params['signature'] = signature
    return params

def gateio_headers(method, path, query_string='', body=''):
    t = str(int(time.time()))
    m = hashlib.sha512()
    m.update(body.encode('utf-8') if body else b'')
    hashed_payload = m.hexdigest()
    s = f"{method}\n{path}\n{query_string}\n{hashed_payload}\n{t}"
    sign = hmac.new(GATEIO_API_SECRET.encode('utf-8'), s.encode('utf-8'), hashlib.sha512).hexdigest()
    return {
        'KEY': GATEIO_API_KEY,
        'Timestamp': t,
        'SIGN': sign,
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

def fetch_url(url, headers=None, params=None, timeout=20, retries=3):
    default_headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    if headers:
        default_headers.update(headers)

    for attempt in range(retries):
        try:
            r = requests.get(
                url,
                headers=default_headers,
                params=params,
                timeout=(5, timeout)
            )

            print(f"URL: {r.url} | Status: {r.status_code}")

            if r.status_code == 429:
                wait = 2 ** attempt
                print(f"Rate limited. Retrying in {wait}s...")
                time.sleep(wait)
                continue

            if r.status_code!= 200:
                print("Response:", r.text[:300])
                return {} if "capital/config/getall" in url or "withdraw_status" in url else []

            content_type = r.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                print("Non-JSON response:", r.text[:300])
                return []

            data = r.json()

            if isinstance(data, dict):
                if data.get("code") not in [None, 0, "0"]:
                    print("API Error:", data)
                    return {} if "capital/config/getall" in url or "withdraw_status" in url else []

            return data

        except requests.exceptions.Timeout:
            print(f"Timeout. Retry {attempt+1}/{retries}")
            time.sleep(1)

        except requests.exceptions.ConnectionError:
            print(f"Connection error. Retry {attempt+1}/{retries}")
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            print("Request failed:", e)
            return {} if "capital/config/getall" in url or "withdraw_status" in url else []

        except ValueError:
            print("JSON decode failed:", r.text[:300] if 'r' in locals() else "No response")
            return []

        except Exception as e:
            print("Other error:", e)
            return []

    return {} if "capital/config/getall" in url or "withdraw_status" in url else []

def get_binance_fees():
    if not API_KEY or API_KEY == "paste_your_binance_api_key":
        print(f"{C.YELLOW}Binance API key missing. Using fallback.{C.END}")
        return {}, {}
        
    url = f"{BASE_URL}/sapi/v1/capital/config/getall"
    params = {'timestamp': int(time.time() * 1000)}
    signed = sign_binance(params, API_SECRET)
    headers = {'X-MBX-APIKEY': API_KEY}
    data = fetch_url(url, headers=headers, params=signed)

    if not isinstance(data, list) or len(data) == 0:
        print(f"{C.YELLOW}Binance fees API failed. Using fallback.{C.END}")
        return {}, {}

    fees, status = {}, {}
    for coin in data:
        try:
            sym = coin.get('coin')
            if not sym: continue
            fees[sym] = {'trade': FALLBACK_TRADE_FEE, 'withdraw': 999}
            status[sym] = {'deposit': False, 'withdraw': False, 'network': 'N/A'}
            
            for net in coin.get('networkList', []):
                if sym == 'USDT' and net.get('network') == 'TRX':
                    fees[sym]['withdraw'] = float(net.get('withdrawFee', FALLBACK_USDT_WD_FEE))
                    status[sym] = {
                        'deposit': bool(net.get('depositEnable', False)),
                        'withdraw': bool(net.get('withdrawEnable', False)),
                        'network': 'TRC20'
                    }
                    break
                elif net.get('isDefault'):
                    fees[sym]['withdraw'] = float(net.get('withdrawFee', 999))
                    status[sym] = {
                        'deposit': bool(net.get('depositEnable', False)),
                        'withdraw': bool(net.get('withdrawEnable', False)),
                        'network': net.get('network', 'N/A')
                    }
        except: continue
    return fees, status

def get_gateio_fees():
    if not GATEIO_API_KEY or GATEIO_API_KEY == "your_gateio_key":
        print(f"{C.YELLOW}Gate.io API key missing. Using fallback.{C.END}")
        return {}, {}
        
    path = "/api/v4/wallet/withdraw_status"
    url = f"https://api.gateio.ws{path}"
    headers = gateio_headers("GET", path)
    data = fetch_url(url, headers=headers)

    if not isinstance(data, list) or len(data) == 0:
        print(f"{C.YELLOW}Gate.io fees API failed. Using fallback.{C.END}")
        return {}, {}

    fees, status = {}, {}
    for coin in data:
        try:
            sym = coin.get("currency")
            if not sym:
                continue

            fees[sym] = {
                "trade": FALLBACK_TRADE_FEE,
                "withdraw": float(coin.get("withdraw_fix", 999))
            }

            status[sym] = {
                "deposit": coin.get("deposit_status") == 1,
                "withdraw": coin.get("withdraw_status") == 1,
                "network": coin.get("chain", "N/A")
            }

        except:
            continue

    return fees, status

def update_fees_status():
    global FEES_CACHE, STATUS_CACHE, LAST_UPDATE
    if time.time() - LAST_UPDATE < CHECK_INTERVAL and FEES_CACHE: return

    print(f"{C.CYAN}Fetching fees from Binance + Gate.io APIs...{C.END}")
    with ThreadPoolExecutor(max_workers=2) as ex:
        b_fut = ex.submit(get_binance_fees)
        g_fut = ex.submit(get_gateio_fees)
        b_fees, b_stat = b_fut.result()
        g_fees, g_stat = g_fut.result()

    FEES_CACHE = {'binance': b_fees, 'gateio': g_fees}
    STATUS_CACHE = {'binance': b_stat, 'gateio': g_stat}
    LAST_UPDATE = time.time()
    print(f"{C.GREEN}Fees loaded.{C.END}")

def get_all_tickers():
    urls = {
        'binance': f"{BASE_URL}/api/v3/ticker/bookTicker",
        'gateio': "https://api.gateio.ws/api/v4/spot/tickers"
    }
    with ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(fetch_url, urls.values()))

    binance_data, gateio_data = results
    tickers = {'binance': {}, 'gateio': {}}

    for i in binance_data:
        if isinstance(i, dict) and i.get('symbol','').endswith('USDT'):
            try:
                if float(i.get('bidPrice',0)) > 0:
                    coin = i['symbol'].replace('USDT', '')
                    tickers['binance'] = {'bid': float(i['bidPrice']), 'ask': float(i['askPrice'])}
            except: continue

    for i in gateio_data:
        if isinstance(i, dict) and i.get('currency_pair','').endswith('_USDT'):
            try:
                if float(i.get('highest_bid',0)) > 0:
                    coin = i['currency_pair'].replace('_USDT', '')
                    tickers['gateio'] = {'bid': float(i['highest_bid']), 'ask': float(i['lowest_ask'])}
            except: continue

    return tickers

def calc_cross_arb(coin, buy_ex, sell_ex, tickers):
    if coin not in tickers[buy_ex] or coin not in tickers[sell_ex]: return None

    buy_stat = STATUS_CACHE.get(buy_ex, {}).get(coin, {})
    sell_stat = STATUS_CACHE.get(sell_ex, {}).get(coin, {})

    wd_ok = buy_stat.get('withdraw', True) if buy_stat else True
    dp_ok = sell_stat.get('deposit', True) if sell_stat else True
    if not wd_ok or not dp_ok: return None

    buy_ask = tickers[buy_ex]['ask']
    sell_bid = tickers[sell_ex]['bid']
    if buy_ask <= 0 or sell_bid <= 0: return None

    coins_bought = STARTING_USDT / buy_ask
    usdt_after_sell = coins_bought * sell_bid
    gross_profit = usdt_after_sell - STARTING_USDT
    gross_percent = (gross_profit / STARTING_USDT) * 100

    buy_trade_fee = STARTING_USDT * FEES_CACHE[buy_ex].get(coin, {}).get('trade', FALLBACK_TRADE_FEE)
    sell_trade_fee = usdt_after_sell * FEES_CACHE[sell_ex].get(coin, {}).get('trade', FALLBACK_TRADE_FEE)
    
    wd_fee = FEES_CACHE[buy_ex].get(coin, {}).get('withdraw', FALLBACK_USDT_WD_FEE)
    if coin == 'USDT':
        withdraw_fee = wd_fee
    else:
        withdraw_fee = wd_fee * sell_bid

    total_fees = buy_trade_fee + sell_trade_fee + withdraw_fee
    net_profit = gross_profit - total_fees
    net_percent = (net_profit / STARTING_USDT) * 100

    if net_percent < MIN_NET_PROFIT: return None

    return {
        'coin': coin, 'buy_ex': buy_ex, 'sell_ex': sell_ex,
        'buy_price': buy_ask, 'sell_price': sell_bid,
        'gross_percent': gross_percent, 'gross_usd': gross_profit,
        'buy_fee': buy_trade_fee, 'sell_fee': sell_trade_fee, 'withdraw_fee': withdraw_fee,
        'fees_usd': total_fees, 'net_percent': net_percent, 'net_usd': net_profit,
        'buy_wd_ok': wd_ok, 'sell_dp_ok': dp_ok,
        'network': buy_stat.get('network', 'TRC20')
    }

def print_opp(r):
    ts = time.strftime("%H:%M:%S")
    wd_status = f"{C.GREEN}WD:OK{C.END}" if r['buy_wd_ok'] else f"{C.RED}WD:OFF{C.END}"
    dp_status = f"{C.GREEN}DP:OK{C.END}" if r['sell_dp_ok'] else f"{C.RED}DP:OFF{C.END}"

    print(f"{C.MAGENTA}[{ts}]{C.END} {C.BOLD}{C.CYAN}{r['coin']}/USDT{C.END} | {C.RED}BUY {r['buy_ex'].upper()}@{r['buy_price']:.5g}{C.END} -> {C.GREEN}SELL {r['sell_ex'].upper()}@{r['sell_price']:.5g}{C.END}")
    print(f" {C.YELLOW}Gross: +{r['gross_percent']:.2f}% ${r['gross_usd']:.2f}{C.END} | {C.BLUE}Fees: Buy${r['buy_fee']:.2f} Sell${r['sell_fee']:.2f} WD${r['withdraw_fee']:.2f}{C.END} | {C.GREEN}{C.BOLD}Net: +{r['net_percent']:.2f}% ${r['net_usd']:.2f}{C.END}")
    print(f" Network: {r['network']} | {wd_status} | {dp_status}\n")

def scan():
    start = time.time()
    update_fees_status()
    tickers = get_all_tickers()

    coins = set(tickers['binance'].keys()) & set(tickers['gateio'].keys())
    results = []
    
    for coin in coins:
        res = calc_cross_arb(coin, 'gateio', 'binance', tickers)
        if res: results.append(res)
        res = calc_cross_arb(coin, 'binance', 'gateio', tickers)
        if res: results.append(res)

    results.sort(key=lambda x: x['net_percent'], reverse=True)
    elapsed = time.time() - start

    if results:
        print(f"\n{C.BOLD}{C.GREEN}Found {len(results)} USDT cross-ex opps >{MIN_NET_PROFIT}% net in {elapsed:.2f}s:{C.END}\n")
        for r in results[:5]: print_opp(r)
    else:
        print(f"\r{C.YELLOW}No USDT opps >{MIN_NET_PROFIT}% net | Scanned {len(coins)*2} pairs in {elapsed:.2f}s{C.END}", end='', flush=True)
    return len(results)

if __name__ == "__main__":
    print(f"{C.BOLD}{C.BLUE}USDT Cross-Exchange Scanner | Binance + Gate.io | Min net: {MIN_NET_PROFIT}%{C.END}")
    print(f"{C.YELLOW}WARNING: Verify WD:OK DP:OK + Network before trading.{C.END}\n")
    update_fees_status()
    while True:
        try:
            found = scan()
            time.sleep(0 if found else SCAN_DELAY)
        except KeyboardInterrupt:
            print(f"\n{C.YELLOW}Stopped{C.END}")
            break
        except Exception as e:
            print(f"\n{C.RED}Error: {e}{C.END}")
            time.sleep(5)
