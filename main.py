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
        token_transfers = tx.get("tokenTransfers", [])
        
        # Eğer token transferi yoksa ama SOL transferi varsa (Native SOL swapleri için)
        native_transfers = tx.get("nativeTransfers", [])

        incoming_tokens = []
        outgoing_tokens = []

        # Token transferlerini ayrıştır (SPL Tokens)
        for tf in token_transfers:
            mint = tf.get("mint", "Bilinmeyen")
            amount = tf.get("tokenAmount", 0)
            from_user = tf.get("fromUser", "")
            to_user = tf.get("toUser", "")
            
            if from_user == wallet:
                outgoing_tokens.append(f"{amount} adet (`{mint[:6]}...{mint[-6:]}`)")
            if to_user == wallet:
                incoming_tokens.append(f"{amount} adet (`{mint[:6]}...{mint[-6:]}`)")

        # SOL transferlerini ayrıştır
        for nf in native_transfers:
            amount_sol = nf.get("amount", 0) / 1000000000 # Lamports to SOL
            from_user = nf.get("fromUser", "")
            to_user = nf.get("toUser", "")
            
            if amount_sol > 0.001: # Çok küçük fee/rent ücretlerini yoksay
                if from_user == wallet:
                    outgoing_tokens.append(f"{amount_sol} SOL")
                if to_user == wallet:
                    incoming_tokens.append(f"{amount_sol} SOL")

        # İşlem türünü belirle
        islem_tipi = "🔴 TRANSFER / ETKİLEŞİM"
        if outgoing_tokens and incoming_tokens:
            # Eğer cüzdandan SOL veya stablecoin (USDC/USDT) çıkıp başka bir şey girdiyse ALIMDIR
            # Tam tersi durumda SATIMDIR. Basit bir mantık oturtalım:
            is_sol_or_usdc_out = any("SOL" in x or "EPjFWb" in x for x in outgoing_tokens) # EPjFWb = USDC Mint adresi başlangıcı
            
            if is_sol_or_usdc_out:
                islem_tipi = "🟢 ALIM (SWAP BUY)"
            else:
                islem_tipi = "🔴 SATIM (SWAP SELL)"
        elif incoming_tokens:
            islem_tipi = "📥 GELEN TRANSFER (INCOMING)"
        elif outgoing_tokens:
            islem_tipi = "📤 GİDEN TRANSFER (OUTGOING)"

        # Mesajı oluştur
        solscan_url = f"https://solscan.io/tx/{signature}"
        
        # Eğer kayda değer bir hareket varsa bildir
        if incoming_tokens or outgoing_tokens:
            msg = f"🔔 *CÜZDAN HAREKETİ TESPİT EDİLDİ*\n\n"
            msg += f"👤 *Cüzdan:* `{wallet}`\n"
            msg += f"📊 *İşlem Türü:* {islem_tipi}\n\n"
            
            if outgoing_tokens:
                msg += f"📉 *Harcanan / Satılan:* \n" + "\n".join([f"• {x}" for x in outgoing_tokens]) + "\n"
            if incoming_tokens:
                msg += f"📈 *Alınan / Gelen:* \n" + "\n".join([f"• {x}" for x in incoming_tokens]) + "\n"
                
            msg += f"\n🔗 *Solscan:* [Detayları Gör]({solscan_url})"
            
            send_telegram_message(msg)
            print(f"Detaylı işlem bildirildi: {signature}")

    except Exception as e:
        print(f"Detaylandırırken hata: {e}")

def bot_loop():
    print("Bot döngüsü başlatıldı...")
    send_telegram_message("🚀 *Gelişmiş Filtreli Takip Botu Aktif Edildi!*\nAlım, satım ve coin kontratları detaylandırılıyor.")
    
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
    server_thread = Thread(target=run_web_server)
    server_thread.start()
    bot_loop()
