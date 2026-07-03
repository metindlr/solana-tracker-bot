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
JUPITER_PRICE_URL = "https://api.jup.ag/price/v2"

# Küresel olarak cüzdanların mevcut sahip olduğu token mint adreslerini tutacağız (Yeni alım kontrolü için)
KNOWN_WALLET_TOKENS = {wallet: set() for wallet in TARGET_WALLETS}

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

def get_token_prices(mint_addresses):
    """Jupiter API kullanarak toplu token fiyatlarını çeker."""
    if not mint_addresses: return {}
    prices = {}
    try:
        # Maksimum 100 token sınırı nedeniyle bölerek gönderebiliriz, şimdilik toplu atıyoruz
        ids = ",".join(mint_addresses)
        response = requests.get(f"{JUPITER_PRICE_URL}?ids={ids}")
        data = response.json().get("data", {})
        for mint, info in data.items():
            if info:
                prices[mint] = float(info.get("price", 0))
    except Exception as e:
        print(f"Jupiter fiyat çekme hatası: {e}")
    return prices

def get_wallet_portfolio_v2(wallet_address):
    """Cüzandaki token hesaplarını ham RPC ile çeker ve Jupiter ile fiyatlandırır."""
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
    total_usd_value = 0.0
    try:
        # Native SOL miktarını da ekleyelim
        sol_payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [wallet_address]}
        sol_res = requests.post(RPC_URL, json=sol_payload).json()
        sol_balance = sol_res.get("result", {}).get("value", 0) / 1000000000
        
        mint_list = ["So11111111111111111111111111111111111111112"] # SOL mint adresi
        token_balances = {"So11111111111111111111111111111111111111112": sol_balance}

        # SPL Tokenları çek
        response = requests.post(RPC_URL, json=payload)
        accounts = response.json().get("result", {}).get("value", [])
        
        for acc in accounts:
            info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            mint = info.get("mint")
            amount = float(info.get("tokenAmount", {}).get("uiAmount", 0))
            if amount > 0 and mint:
                mint_list.append(mint)
                token_balances[mint] = amount

        # Fiyatları eşleştir
        prices = get_token_prices(mint_list)
        
        current_tokens_set = set()
        for mint, amount in token_balances.items():
            price = prices.get(mint, 0)
            usd_val = amount * price
            # Sadece değeri olan veya bilinen tokenları listeye alalım
            symbol = "SOL" if mint == "So11111111111111111111111111111111111111112" else f"{mint[:4]}...{mint[-4:]}"
            
            if usd_val > 0.1 or mint == "So11111111111111111111111111111111111111112":
                portfolio.append({"mint": mint, "symbol": symbol, "amount": amount, "usd_value": usd_val})
                total_usd_value += usd_val
                current_tokens_set.add(mint)
                
        # Küresel seti güncelle (Yeni alım takibi için)
        if current_tokens_set:
            KNOWN_WALLET_TOKENS[wallet_address] = current_tokens_set

    except Exception as e:
        print(f"Portföy V2 hatası: {e}")
    
    # En yüksek USD değerine göre sırala
    portfolio.sort(key=lambda x: x["usd_value"], reverse=True)
    return portfolio[:10], total_usd_value  # İlk 10 tokenı dön

def check_transaction_details(signature, wallet):
    try:
        payload = {"transactions": [signature]}
        response = requests.post(PARSE_URL, json=payload)
        tx_data = response.json()
        if not tx_data: return

        tx = tx_data[0]
        if tx.get("type") != "SWAP": return

        token_transfers = tx.get("tokenTransfers", [])
        native_transfers = tx.get("nativeTransfers", [])
        
        incoming_mint, incoming_amount, outgoing_mint, outgoing_amount = None, 0, None, 0

        for tf in token_transfers:
            mint = tf.get("mint", "")
            amount = tf.get("tokenAmount", 0)
            if tf.get("toUser") == wallet:
                incoming_mint, incoming_amount = mint, amount
            if tf.get("fromUser") == wallet:
                outgoing_mint, outgoing_amount = mint, amount

        # Eğer SOL transferi varsa
        for nf in native_transfers:
            sol_amt = nf.get("amount", 0) / 1000000000
            if sol_amt > 0.01:
                if nf.get("toUser") == wallet: incoming_mint, incoming_amount = "So11111111111111111111111111111111111111112", sol_amt
                if nf.get("fromUser") == wallet: outgoing_mint, outgoing_amount = "So11111111111111111111111111111111111111112", sol_amt

        # Fiyat ve $1000 filtresi kontrolü
        mints_to_check = [m for m in [incoming_mint, outgoing_mint] if m]
        prices = get_token_prices(mints_to_check)

        in_price = prices.get(incoming_mint, 0) if incoming_mint else 0
        out_price = prices.get(outgoing_mint, 0) if outgoing_mint else 0
        
        tx_usd_value = max(incoming_amount * in_price, outgoing_amount * out_price)

        # 🚨 Kural 1: Sadece $1000 ve üzeri işlemleri bildir
        if tx_usd_value >= 1000:
            # 🚨 Kural 2: Yeni Alım Kontrolü
            is_new_token = incoming_mint not in KNOWN_WALLET_TOKENS[wallet] and incoming_mint != "So11111111111111111111111111111111111111112"
            
            islem_etiketi = "🚨 YENİ COIN ALIMI! (NEW BUY)" if is_new_token else "🟢 ALIM (SWAP BUY)"
            if outgoing_mint and not incoming_mint: islem_etiketi = "🔴 SATIM (SWAP SELL)"

            in_sym = "SOL" if incoming_mint == "So11111111111111111111111111111111111111112" else f"`{incoming_mint[:6]}...{incoming_mint[-6:]}`" if incoming_mint else "Bilinmeyen"
            out_sym = "SOL" if outgoing_mint == "So11111111111111111111111111111111111111112" else f"`{outgoing_mint[:6]}...{outgoing_mint[-6:]}`" if outgoing_mint else "Bilinmeyen"

            msg = (
                f"{islem_etiketi}\n\n"
                f"👤 *Cüzdan:* `{wallet[:6]}...{wallet[-6:]}`\n"
                f"💵 *Tahmini Hacim:* `${tx_usd_value:,.2f}`\n"
                f"📥 *Alınan:* {incoming_amount:,.2f} {in_sym}\n"
                f"📤 *Satılan:* {outgoing_amount:,.2f} {out_sym}\n\n"
                f"🔗 *Solscan:* [İşlem Detayı](https://solscan.io/tx/{signature})"
            )
            send_telegram_message(msg)
            
            # Eğer yeni bir coin ise hafızaya ekle ki tekrar yeni demesin
            if incoming_mint: KNOWN_WALLET_TOKENS[wallet].add(incoming_mint)

    except Exception as e:
        print(f"İşlem işlenirken hata: {e}")

def send_periodic_report():
    report_msg = "📊 *İLK 10 COIN PORTFÖY RAPORU (30 DK)*\n───────────────────\n"
    for wallet in TARGET_WALLETS:
        portfolio, total_val = get_wallet_portfolio_v2(wallet)
        report_msg += f"👤 *Cüzdan:* `{wallet[:6]}...{wallet[-6:]}`\n💰 *Toplam Değer:* `${total_val:,.2f}`\n📦 *İlk 10 Varlık:*\n"
        if portfolio:
            for t in portfolio:
                report_msg += f" • *{t['symbol']}:* {t['amount']:,.2f} adet (~`${t['usd_value']:,.2f}`)\n"
        else:
            report_msg += "  _(Varlık tespit edilemedi)_\n"
        report_msg += "───────────────────\n"
    send_telegram_message(report_msg)

def bot_loop():
    # İlk açılışta mevcut portföydeki tokenları hafızaya almak için bir kez çalıştır
    for wallet in TARGET_WALLETS: get_wallet_portfolio_v2(wallet)
    print("Anlık takip döngüsü aktif...")
    
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
            except Exception as e: print(f"Döngü hatası: {e}")
        time.sleep(12)

def portfolio_timer_loop():
    time.sleep(15)
    send_periodic_report()
    while True:
        time.sleep(1800) # 30 dakika
        try: send_periodic_report()
        except Exception as e: print(f"Rapor hatası: {e}")

if __name__ == "__main__":
    Thread(target=run_web_server).start()
    Thread(target=portfolio_timer_loop).start()
    bot_loop()
