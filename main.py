import time
import requests
from threading import Thread
from flask import Flask

# --- RENDER KAPANMASIN DİYE WEB SUNUCUSU ---
app = Flask('')

@app.route('/')
def home():
    return "Bot 7/24 Aktif ve Calisiyor!"

def run_web_server():
    # Render varsayılan olarak 10000 portunu dinler
    app.run(host='0.0.0.0', port=10000)

# --- YAPILANDIRMA ---
TELEGRAM_BOT_TOKEN = "8624055135:AAFgB9-9Rhis97bFs4IJkpVzNcmukcH5MAA"
TELEGRAM_CHAT_ID = "916915195"
HELIUS_API_KEY = "fb2cae6c-1349-427d-8c05-b644ad06259c"  # Hata aldığın çalışan keyin

TARGET_WALLETS = [
    "CLM6E4zpTviEC77nWKogpVLQoXx9tgoQCYJ8NibxKg1Q",
    "7iVCXQn4u6tiTEfNVqbWSEsRdEi69E9oYsSMiepuECwi",
    "EuWbAc5zTpRzTpxx89RhQGZnvPntyrTSQozkLs5QwyH1"
]

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PARSE_URL = f"https://api.helius.xyz/v0/transactions?api-key={HELIUS_API_KEY}"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram hatası: {e}")

def get_latest_signatures(wallet_address):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [wallet_address, {"limit": 3}]
    }
    try:
        response = requests.post(RPC_URL, json=payload)
        result = response.json().get("result", [])
        return [tx["signature"] for tx in result if "signature" in tx]
    except Exception as e:
        print(f"İmzalar alınırken hata: {e}")
        return []

def check_transaction_details(signature, wallet):
    try:
        payload = {"transactions": [signature]}
        response = requests.post(PARSE_URL, json=payload)
        tx_data = response.json()
        
        if not tx_data or len(tx_data) == 0:
            return

        tx = tx_data[0]
        
        # Sadece Swap (Alım-Satım) işlemlerini yakala
        if tx.get("type") == "SWAP":
            description = tx.get("description", "")
            solscan_url = f"https://solscan.io/tx/{signature}"
            
            # NOT: $1000 ve üzeri işlemleri Helius açıklamalarındaki SOL veya büyük miktarlardan filtreleriz.
            # Ücretsiz sürümde tüm swapleri görmek istersen direkt gönderir.
            msg = (
                f"💰 *YENİ SWAP (ALIM/SATIM) TESPİT EDİLDİ*\n\n"
                f"👤 *Cüzdan:* `{wallet}`\n"
                f"📝 *Detay:* {description if description else 'Detaylar linkte.'}\n\n"
                f"🔗 *Solscan:* [İşlemi İncele]({solscan_url})"
            )
            send_telegram_message(msg)
            print(f"İşlem bildirildi: {signature}")

    except Exception as e:
        print(f"Detaylandırırken hata: {e}")

# --- BOTUN ANA DÖNGÜSÜ ---
def bot_loop():
    print("Bot döngüsü başlatıldı...")
    send_telegram_message("🚀 *Render Bulut Botu Aktif Edildi!*\nCüzdanlar 7/24 izleniyor, kısıtlama kaldırıldı.")
    
    known_signatures = {}
    for wallet in TARGET_WALLETS:
        known_signatures[wallet] = set(get_latest_signatures(wallet))
    
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
            except Exception as e:
                print(f"Döngü hatası: {e}")
        time.sleep(15)

if __name__ == "__main__":
    # Web sunucusunu arka planda başlat (Render'ı açık tutmak için)
    server_thread = Thread(target=run_web_server)
    server_thread.start()
    
    # Ana takip botunu başlat
    bot_loop()
