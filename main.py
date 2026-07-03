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

# Helius Gelişmiş Balans (Bakiye) API URL'si
BALANCES_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# Botun ilk başladığı andaki cüzdan değerlerini tutmak için (PnL hesaplama amaçlı)
INITIAL_WALLET_VALUES = {}

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

def get_wallet_portfolio(wallet_address):
    """Helius API kullanarak cüzdandaki tüm tokenları ve tahmini USD değerlerini çeker."""
    payload = {
        "jsonrpc": "2.0",
        "id": "my-id",
        "method": "getAssetsByOwner",
        "params": {
            "ownerAddress": wallet_address,
            "page": 1,
            "limit": 100,
            "displayOptions": {
                "showFungibleTokens": True  # SPL Tokenları (Coinleri) listele
            }
        }
    }
    try:
        response = requests.post(BALANCES_URL, json=payload)
        items = response.json().get("result", {}).get("items", [])
        
        portfolio = []
        total_usd_value = 0.0
        
        for item in items:
            # Sadece fungible (token/coin) olanları ve değeri olanları alalım
            if item.get("interface") == "FungibleToken":
                token_info = item.get("token_info", {})
                balance = token_info.get("balance", 0)
                decimals = token_info.get("decimals", 0)
                
                # Gerçek miktar hesaplama
                amount = balance / (10 ** decimals) if decimals > 0 else balance
                
                # Fiyat ve USD değerleri
                price_info = token_info.get("price_info", {})
                price_per_token = price_info.get("price_per_token", 0)
                total_token_usd = amount * price_per_token
                
                # Metadata (Sembol ve İsim)
                content = item.get("content", {})
                metadata = content.get("metadata", {})
                symbol = metadata.get("symbol", item.get("id", "Bilinmeyen")[:4]) # Sembol yoksa mint adresi kısaltması
                
                if total_token_usd > 1.0: # 1 dolardan değersiz çöp/scam tokenları listelemeyelim
                    portfolio.append({
                        "symbol": symbol,
                        "amount": amount,
                        "usd_value": total_token_usd
                    })
                    total_usd_value += total_token_usd
                    
        return portfolio, total_usd_value
    except Exception as e:
        print(f"Portföy çekilirken hata ({wallet_address[:5]}): {e}")
        return [], 0.0

def send_periodic_report():
    """Her 30 dakikada bir tetiklenecek raporlama fonksiyonu."""
    print("Yarım saatlik portföy raporu hazırlanıyor...")
    
    report_msg = "📊 *YARIM SAATLİK CÜZDAN PORTFÖY VE PnL RAPORU*\n"
    report_msg += "───────────────────\n\n"
    
    for wallet in TARGET_WALLETS:
        portfolio, total_value = get_wallet_portfolio(wallet)
        
        # İlk defa çalışıyorsa başlangıç değerini kaydet
        if wallet not in INITIAL_WALLET_VALUES:
            INITIAL_WALLET_VALUES[wallet] = total_value
            
        # PnL Hesaplama (Botun başladığı andan itibaren toplam değişim)
        initial_value = INITIAL_WALLET_VALUES[wallet]
        pnl_usd = total_value - initial_value
        pnl_percent = (pnl_usd / initial_value * 100) if initial_value > 0 else 0.0
        
        pnl_sign = "🟩 +" if pnl_usd >= 0 else "🟥 "
        
        report_msg += f"👤 *Cüzdan:* `{wallet[:6]}...{wallet[-6:]}`\n"
        report_msg += f"💰 *Toplam Portföy Değeri:* `${total_value:,.2f}`\n"
        report_msg += f"📈 *Bot Başlangıcından Beri PnL:* {pnl_sign}${abs(pnl_usd):,.2f} (%{pnl_percent:.2f})\n"
        report_msg += f"📦 *Varlıklar:*\n"
        
        if portfolio:
            for token in portfolio:
                report_msg += f" • *{token['symbol']}:* {token['amount']:,.2f} adet (~`${token['usd_value']:,.2f}`)\n"
        else:
            report_msg += "  _(1$ üzerinde değerli coin bulunamadı)_\n"
            
        report_msg += "───────────────────\n"
        
    send_telegram_message(report_msg)

def portfolio_timer_loop():
    """Her 30 dakikada bir (1800 saniye) rapor gönderen döngü."""
    # Bot ilk açıldığında verileri kaydetmek için 10 saniye bekle, sonra ilk raporu at
    time.sleep(10)
    send_periodic_report()
    
    while True:
        time.sleep(1800) # 30 dakika = 1800 saniye
        try:
            send_periodic_report()
        except Exception as e:
            print(f"Rapor döngüsünde hata: {e}")

if __name__ == "__main__":
    # Web sunucusunu başlat (Render için)
    server_thread = Thread(target=run_web_server)
    server_thread.start()
    
    # 30 dakikalık raporlama döngüsünü ayrı bir kanalda (thread) başlat
    report_thread = Thread(target=portfolio_timer_loop)
    report_thread.start()
    
    # NOT: Eğer istersen bir önceki mesajdaki anlık transferleri dinleyen `bot_loop()` fonksiyonunu da 
    # buraya ekleyip ikisini aynı anda çalıştırabilirsin. Şu an sadece yarım saatlik raporlama ana odak yapıldı.
