import time
import requests
from threading import Thread
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "Bot 7/24 Aktif ve Calisiyor!"

def run_web_server():
    app.run(host='0.0.0.0', port=10000)

# --- YAPILANDIRMA ---
TELEGRAM_BOT_TOKEN = "8624055135:AAFgB9-9Rhis97bFs4IJkpVzNcmukcH5MAA"
TELEGRAM_CHAT_ID = "916915195"
HELIUS_API_KEY = "fb2cae6c-1349-427d-8c05-b644ad06259c"

TARGET_WALLETS = [
    "CLM6E4zpTviEC77nWKogpVLQoXx9tgoQCYJ8NibxKg1Q",
    "EuWbAc5zTpRzTpxx89RhQGZnvPntyrTSQozkLs5QwyH1"
]

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PARSE_URL = f"https://api.helius.xyz/v0/transactions?api-key={HELIUS_API_KEY}"

KNOWN_WALLET_TOKENS = {wallet: set() for wallet in TARGET_WALLETS}
TOKEN_METADATA_CACHE = {} # Coin isimlerini hafızada tutarak hızı artırır

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try: requests.post(url, json=payload)
    except Exception as e: print(f"Telegram hatası: {e}")

def get_token_metadata_batch(mint_list):
    """Jupiter API kullanarak kontrat adreslerinden gerçek coin isimlerini/sembollerini çeker."""
    needed_mints = [m for m in mint_list if m not in TOKEN_METADATA_CACHE]
    if not needed_mints: return
    
    try:
        # Belirli aralıklarla Jupiter'in geniş listesinden arama yapıyoruz
        # Önbelleğe SOL ekle
        TOKEN_METADATA_CACHE["So11111111111111111111111111111111111111112"] = "SOL"
        
        # Token adlarını toplu çözmek için popüler katmanları tarar
        for mint in needed_mints:
            if mint == "So11111111111111111111111111111111111111112": continue
            # Dexscreener API'sini isimleri en hızlı çözmek için yedek olarak kullanıyoruz
            res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}").json()
            pairs = res.get("pairs", [])
            if pairs:
                base_token = pairs[0].get("baseToken", {})
                symbol = base_token.get("symbol", f"{mint[:4]}..{mint[-4:]}")
                TOKEN_METADATA_CACHE[mint] = symbol.upper()
            else:
                TOKEN_METADATA_CACHE[mint] = f"{mint[:4]}..{mint[-4:]}"
    except Exception as e:
        print(f"Metadata çekilirken hata oluştu: {e}")

def get_solana_token_balances(wallet_address):
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet_address,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"}
        ]
    }
    portfolio = []
    try:
        sol_payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [wallet_address]}
        sol_res = requests.post(RPC_URL, json=sol_payload).json()
        sol_balance = sol_res.get("result", {}).get("value", 0) / 1000000000
        
        if sol_balance > 0.01:
            portfolio.append({"mint": "So11111111111111111111111111111111111111112", "amount": sol_balance})

        response = requests.post(RPC_URL, json=payload)
        accounts = response.json().get("result", {}).get("value", [])
        
        for acc in accounts:
            info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            mint = info.get("mint")
            amount = float(info.get("tokenAmount", {}).get("uiAmount", 0))
            
            if amount > 0 and mint:
                portfolio.append({"mint": mint, "amount": amount})
                KNOWN_WALLET_TOKENS[wallet_address].add(mint)
    except Exception as e:
        print(f"Bakiye tarama hatası: {e}")
    return portfolio

def get_token_prices_jup(mint_list):
    if not mint_list: return {}
    prices = {}
    try:
        ids = ",".join(mint_list)
        res = requests.get(f"https://api.jup.ag/price/v2?ids={ids}").json()
        data = res.get("data", {})
        for mint, info in data.items():
            if info: prices[mint] = float(info.get("price", 0))
    except Exception as e: print(f"Fiyat çekilemedi: {e}")
    return prices

def check_transaction_details(signature, wallet):
    try:
        payload = {"transactions": [signature]}
        tx_data = requests.post(PARSE_URL, json=payload).json()
        if not tx_data: return

        tx = tx_data[0]
        if tx.get("type") != "SWAP": return

        token_transfers = tx.get("tokenTransfers", [])
        incoming_mint, incoming_amount, outgoing_mint, outgoing_amount = None, 0, None, 0

        for tf in token_transfers:
            if tf.get("toUser") == wallet:
                incoming_mint = tf.get("mint", "")
                incoming_amount = tf.get("tokenAmount", 0)
            if tf.get("fromUser") == wallet:
                outgoing_mint = tf.get("mint", "")
                outgoing_amount = tf.get("tokenAmount", 0)

        if not incoming_mint and not outgoing_mint: return

        mints = [m for m in [incoming_mint, outgoing_mint] if m]
        get_token_metadata_batch(mints) # İsimleri bul
        prices = get_token_prices_jup(mints)
        
        in_price = prices.get(incoming_mint, 0)
        out_price = prices.get(outgoing_mint, 0)
        tx_usd_value = max(incoming_amount * in_price, outgoing_amount * out_price)

        if tx_usd_value >= 1000:
            is_new = incoming_mint not in KNOWN_WALLET_TOKENS[wallet] and incoming_mint != "So11111111111111111111111111111111111111112"
            etiket = "🚨 YENİ COIN ALIMI!" if is_new else "🟢 ALIM (SWAP BUY)"
            if outgoing_mint and not incoming_mint: etiket = "🔴 SATIM (SWAP SELL)"

            in_name = TOKEN_METADATA_CACHE.get(incoming_mint, "Bilinmeyen") if incoming_mint else "Bilinmeyen"
            out_name = TOKEN_METADATA_CACHE.get(outgoing_mint, "Bilinmeyen") if outgoing_mint else "Bilinmeyen"

            msg = (
                f"{etiket}\n\n"
                f"👤 *Cüzdan:* `{wallet[:6]}...{wallet[-6:]}`\n"
                f"💵 *Yatırım / Hacim:* `${tx_usd_value:,.2f}`\n"
                f"📥 *Alınan:* {incoming_amount:,.2f} *{in_name}*\n"
                f"📤 *Satılan:* {outgoing_amount:,.2f} *{out_name}*\n\n"
                f"🔗 [Solscan Detay](https://solscan.io/tx/{signature})"
            )
            send_telegram_message(msg)
            if incoming_mint: KNOWN_WALLET_TOKENS[wallet].add(incoming_mint)
    except Exception as e: print(f"İşlem hatası: {e}")

def send_periodic_report():
    report_msg = "📊 *CÜZDAN PORTFÖY RAPORU (İLK 10 COIN)*\n───────────────────\n"
    for wallet in TARGET_WALLETS:
        portfolio = get_solana_token_balances(wallet)
        mint_list = [t["mint"] for t in portfolio]
        
        get_token_metadata_batch(mint_list) # İsim havuzunu doldur
        prices = get_token_prices_jup(mint_list)
        
        total_wallet_usd = 0.0
        valued_portfolio = []
        
        for t in portfolio:
            price = prices.get(t["mint"], 0)
            usd_val = t["amount"] * price
            total_wallet_usd += usd_val
            
            coin_symbol = TOKEN_METADATA_CACHE.get(t["mint"], f"{t['mint'][:4]}..")
            
            valued_portfolio.append({
                "symbol": coin_symbol, "amount": t["amount"], "usd_value": usd_val
            })
            
        valued_portfolio.sort(key=lambda x: x["usd_value"], reverse=True)
        top_10 = valued_portfolio[:10]

        report_msg += f"👤 *Cüzdan:* `{wallet[:6]}...{wallet[-6:]}`\n💰 *Toplam Portföy Yatırımı:* `${total_wallet_usd:,.2f}`\n📦 *Varlık Değerleri:*\n"
        if top_10:
            for t in top_10:
                report_msg += f" • *{t['symbol']}:* {t['amount']:,.2f} adet (~`${t['usd_value']:,.2f}`)\n"
        else:
            report_msg += "  _(Varlık bulunamadı)_\n"
        report_msg += "───────────────────\n"
    send_telegram_message(report_msg)

def bot_loop():
    for wallet in TARGET_WALLETS: get_solana_token_balances(wallet)
    known_signatures = {w: set(get_latest_signatures(w)) for w in TARGET_WALLETS}
    while True:
        for wallet in TARGET_WALLETS:
            try:
                current_signatures = get_latest_signatures(wallet)
                for sig in current_signatures:
                    if sig not in known_signatures[wallet]:
                        check_transaction_details(sig, wallet)
                        known_signatures[wallet].add(sig)
                if len(known_signatures[wallet]) > 30:
                    known_signatures[wallet] = set(list(known_signatures[wallet])[-20:])
            except Exception as e: pass
        time.sleep(15)

def get_latest_signatures(wallet_address):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [wallet_address, {"limit": 3}]}
    try:
        res = requests.post(RPC_URL, json=payload).json()
        return [tx["signature"] for tx in res.get("result", []) if "signature" in tx]
    except: return []

def portfolio_timer_loop():
    time.sleep(10)
    send_periodic_report()
    while True:
        time.sleep(1800) # 30 Dakika bekler
        try: send_periodic_report()
        except Exception as e: print(f"Rapor hatası: {e}")

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    Thread(target=portfolio_timer_loop).start()
    bot_loop()
