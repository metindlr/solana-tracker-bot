import asyncio
import json
import requests
import time
from datetime import datetime
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Kullanıcı Bilgileri
TELEGRAM_BOT_TOKEN = "8624055135:AAFgB9-9Rhis97bFs4IJkpVzNcmukcH5MAA"
TELEGRAM_CHAT_ID = "916915195"
WALLETS = [
    "EuWbAc5zTpRzTpxx89RhQGZnvPntyrTSQozkLs5QwyH1",
    "CLM6E4zpTviEC77nWKogpVLQoXx9tgoQCYJ8NibxKg1Q"
]

# API Endpoint'leri (Solscan ve DexScreener)
SOLSCAN_API_URL = "https://api.solscan.io" # Not: Pro API anahtarı gerekebilir, genel kullanım için sınırlı olabilir
DEXSCREENER_API_URL = "https://api.dexscreener.com/latest/dex/tokens/"
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"

# Veri saklama (Önceki portföy durumlarını karşılaştırmak için)
previous_portfolios = {}

async def send_telegram_message(message):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram hatası: {e}")

def get_sol_balance(wallet_address):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [wallet_address]
    }
    try:
        response = requests.post(SOLANA_RPC_URL, json=payload)
        result = response.json()
        balance_lamports = result.get('result', {}).get('value', 0)
        return balance_lamports / 10**9
    except Exception as e:
        print(f"SOL bakiye çekme hatası: {e}")
        return 0

def get_token_accounts(wallet_address):
    # Bu kısım normalde Solscan Pro veya Helius gibi bir API gerektirir. 
    # Genel RPC üzerinden getProgramAccounts kullanılabilir ancak çok yavaştır.
    # Bu botta gösterim amaçlı Solscan'in halka açık (varsa) veya alternatif bir veri kaynağı simüle edilmiştir.
    # Gerçek uygulamada Helius veya Birdeye API anahtarı kullanılması önerilir.
    
    # Simülasyon/Basit Veri Çekme (Helius DAS API veya benzeri idealdir)
    # Şimdilik Solana RPC üzerinden token hesaplarını çekmeyi deneyelim
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet_address,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"}
        ]
    }
    try:
        response = requests.post(SOLANA_RPC_URL, json=payload)
        tokens = response.json().get('result', {}).get('value', [])
        token_list = []
        for token in tokens:
            data = token['account']['data']['parsed']['info']
            mint = data['mint']
            amount = float(data['tokenAmount']['uiAmount'])
            if amount > 0:
                token_list.append({'mint': mint, 'amount': amount})
        return token_list
    except Exception as e:
        print(f"Token listesi çekme hatası: {e}")
        return []

def get_token_price_and_info(mint_address):
    try:
        response = requests.get(f"{DEXSCREENER_API_URL}{mint_address}")
        data = response.json()
        pairs = data.get('pairs', [])
        if pairs:
            # En yüksek likiditeye sahip çifti al
            best_pair = pairs[0]
            return {
                'symbol': best_pair.get('baseToken', {}).get('symbol', 'UNKNOWN'),
                'price': float(best_pair.get('priceUsd', 0)),
                'name': best_pair.get('baseToken', {}).get('name', 'Unknown')
            }
    except:
        pass
    return {'symbol': '?', 'price': 0, 'name': 'Unknown'}

async def check_wallets():
    global previous_portfolios
    
    for wallet in WALLETS:
        print(f"Kontrol ediliyor: {wallet}")
        sol_balance = get_sol_balance(wallet)
        tokens = get_token_accounts(wallet)
        print(f"Bulunan token sayısı: {len(tokens)}")
        
        portfolio = []
        total_value = sol_balance * get_token_price_and_info("So11111111111111111111111111111111111111112")['price']
        
        # Hız için: Sadece belirli bir miktarın üzerindeki tokenları işle veya ilk 20'ye odaklan
        # Gerçek bir API (Helius/Birdeye) tüm fiyatları tek seferde verebilir.
        # Ücretsiz RPC ve Dexscreener ile sınırlı sayıda tokenı kontrol etmek daha mantıklı.
        
        # Filtreleme: Çok küçük miktarları ele
        filtered_tokens = [t for t in tokens if t['amount'] > 0]
        
        for t in filtered_tokens[:50]: # İlk 50 token ile sınırla (hız için)
            info = get_token_price_and_info(t['mint'])
            if info['price'] == 0: continue # Fiyat bulunamadıysa geç
            value = t['amount'] * info['price']
            total_value += value
            portfolio.append({
                'mint': t['mint'],
                'symbol': info['symbol'],
                'amount': t['amount'],
                'value': value,
                'price': info['price']
            })
        
        # Değere göre sırala ve ilk 10'u al
        portfolio.sort(key=lambda x: x['value'], reverse=True)
        top_10 = portfolio[:10]
        
        # Rapor Hazırla
        report = f"📊 *Cüzdan Özeti: {wallet[:6]}...{wallet[-4:]}*\n"
        report += f"💰 *Toplam Değer:* ${total_value:,.2f}\n"
        report += f"💎 *SOL Bakiyesi:* {sol_balance:.2f} SOL\n\n"
        report += "*İlk 10 Token (Yatırım Değerine Göre):*\n"
        
        for i, item in enumerate(top_10, 1):
            report += f"{i}. {item['symbol']}: {item['amount']:.2f} (${item['value']:,.2f})\n"
        
        # Yarım saatlik rutin rapor (Sadece loglara yazalım veya isteğe bağlı gönderelim)
        print(report)
        
        # Değişiklik Kontrolü ve Anlık Bildirim
        if wallet in previous_portfolios:
            prev_data = previous_portfolios[wallet]
            prev_mints = {p['mint'] for p in prev_data['portfolio']}
            current_mints = {p['mint'] for p in portfolio}
            
            # 1. Yeni Token Alımı
            new_tokens = current_mints - prev_mints
            for mint in new_tokens:
                token_info = next(p for p in portfolio if p['mint'] == mint)
                if token_info['value'] > 10: # Çok küçük bakiyeleri (dust) görmezden gel
                    msg = f"🚀 *YENİ TOKEN ALINDI!*\nCüzdan: `{wallet}`\nToken: {token_info['symbol']}\nMiktar: {token_info['amount']}\nDeğer: ${token_info['value']:,.2f}"
                    await send_telegram_message(msg)
            
            # 2. 1000$ Üstü Alım/Satım (Miktar değişimi üzerinden değer kontrolü)
            for curr in portfolio:
                prev = next((p for p in prev_data['portfolio'] if p['mint'] == curr['mint']), None)
                if prev:
                    diff_amount = curr['amount'] - prev['amount']
                    diff_value = abs(diff_amount * curr['price'])
                    if diff_value > 1000:
                        action = "ALIM" if diff_amount > 0 else "SATIM"
                        msg = f"🔔 *BÜYÜK İŞLEM TESPİT EDİLDİ ({action})*\nCüzdan: `{wallet}`\nToken: {curr['symbol']}\nDeğişim Değeri: ${diff_value:,.2f}"
                        await send_telegram_message(msg)
        
        # Durumu güncelle
        previous_portfolios[wallet] = {
            'total_value': total_value,
            'sol_balance': sol_balance,
            'portfolio': portfolio
        }

async def main():
    # İlk çalıştırmada mevcut durumu kaydet
    await check_wallets()
    
    # Zamanlayıcıyı başlat (30 dakikada bir)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_wallets, 'interval', minutes=30)
    scheduler.start()
    
    print("Bot çalışıyor... Çıkmak için Ctrl+C")
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    asyncio.run(main())
