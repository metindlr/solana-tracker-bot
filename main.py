import asyncio
import requests
import json
from datetime import datetime
from telegram import Bot
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- YAPILANDIRMA ---
TELEGRAM_BOT_TOKEN = "8624055135:AAFgB9-9Rhis97bFs4IJkpVzNcmukcH5MAA"
TELEGRAM_CHAT_ID = "916915195"
WALLETS = [
    "EuWbAc5zTpRzTpxx89RhQGZnvPntyrTSQozkLs5QwyH1",
    "CLM6E4zpTviEC77nWKogpVLQoXx9tgoQCYJ8NibxKg1Q"
]

# API Endpoint'leri
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
DEXSCREENER_API_URL = "https://api.dexscreener.com/latest/dex/tokens/"

# Veri saklama
previous_portfolios = {}

async def send_telegram_message(message):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, 
            text=message, 
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )
    except Exception as e:
        print(f"Telegram hatası: {e}")

def get_sol_price():
    try:
        response = requests.get(f"{DEXSCREENER_API_URL}So11111111111111111111111111111111111111112")
        data = response.json()
        pairs = data.get('pairs', [])
        if pairs:
            return float(pairs[0].get('priceUsd', 0))
    except:
        pass
    return 140.0 # Yedek fiyat

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
            decimals = int(data['tokenAmount']['decimals'])
            if amount > 0:
                token_list.append({'mint': mint, 'amount': amount, 'decimals': decimals})
        return token_list
    except Exception as e:
        print(f"Token listesi çekme hatası: {e}")
        return []

def get_token_details_batch(mints):
    # DexScreener toplu aramayı desteklemez, ancak biz anlamlı bakiyesi olanları tek tek hızlıca çekeceğiz
    results = {}
    # Not: Gerçek bir uygulamada burada rate limit kontrolü yapılmalıdır.
    for i, mint in enumerate(mints):
        print(f"  [{i+1}/{len(mints)}] Fiyat çekiliyor: {mint}")
        try:
            response = requests.get(f"{DEXSCREENER_API_URL}{mint}", timeout=5)
            data = response.json()
            pairs = data.get('pairs', [])
            if pairs:
                # En yüksek likiditeye sahip çifti bul
                best_pair = sorted(pairs, key=lambda x: x.get('liquidity', {}).get('usd', 0), reverse=True)[0]
                results[mint] = {
                    'name': best_pair.get('baseToken', {}).get('name', 'Bilinmiyor'),
                    'symbol': best_pair.get('baseToken', {}).get('symbol', '???'),
                    'price': float(best_pair.get('priceUsd', 0)),
                    'url': best_pair.get('url', f"https://dexscreener.com/solana/{mint}")
                }
            else:
                results[mint] = {'name': 'Bilinmiyor', 'symbol': '???', 'price': 0, 'url': f"https://dexscreener.com/solana/{mint}"}
        except:
            results[mint] = {'name': 'Bilinmiyor', 'symbol': '???', 'price': 0, 'url': f"https://dexscreener.com/solana/{mint}"}
    return results

async def check_wallets():
    global previous_portfolios
    sol_price = get_sol_price()
    
    for wallet in WALLETS:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Kontrol ediliyor: {wallet}")
        sol_balance = get_sol_balance(wallet)
        token_accounts = get_token_accounts(wallet)
        
        # Sadece anlamlı bakiyesi olanları işle (Hız için)
        # Önce tüm mintleri alalım
        mints = [t['mint'] for t in token_accounts]
        
        # Detayları çek (Bu kısım cüzdandaki token sayısına göre zaman alabilir)
        # Optimizasyon: Sadece ilk 20-30 tokenı detaylandır
        token_details = get_token_details_batch(mints[:30])
        
        portfolio = []
        sol_value = sol_balance * sol_price
        total_value = sol_value
        
        portfolio.append({
            'mint': 'So11111111111111111111111111111111111111112',
            'name': 'Solana',
            'symbol': 'SOL',
            'amount': sol_balance,
            'price': sol_price,
            'value': sol_value,
            'url': 'https://dexscreener.com/solana/So11111111111111111111111111111111111111112'
        })

        for t in token_accounts:
            mint = t['mint']
            if mint in token_details:
                details = token_details[mint]
                value = t['amount'] * details['price']
                if value > 0.01: # 1 cent altını listeye alma
                    total_value += value
                    portfolio.append({
                        'mint': mint,
                        'name': details['name'],
                        'symbol': details['symbol'],
                        'amount': t['amount'],
                        'price': details['price'],
                        'value': value,
                        'url': details['url']
                    })
        
        # Değere göre sırala
        portfolio.sort(key=lambda x: x['value'], reverse=True)
        top_10 = portfolio[:10]
        
        # Rapor Hazırla
        report = f"📊 *Cüzdan Durumu:* `{wallet[:6]}...{wallet[-4:]}`\n"
        report += f"💰 *Toplam Değer:* `${total_value:,.2f}`\n"
        report += f"💎 *SOL:* `{sol_balance:.4f}` (~${sol_value:,.2f})\n\n"
        report += "*İlk 10 Token (Yatırım Değerine Göre):*\n"
        
        for i, item in enumerate(top_10, 1):
            report += f"{i}. [{item['name']} ({item['symbol']})]({item['url']}): `{item['amount']:,.0f}` (~${item['value']:,.2f})\n"
        
        print(f"Cüzdan {wallet} için rapor hazırlandı. Toplam Değer: ${total_value:,.2f}")

        # Bildirim Kontrolü
        if wallet in previous_portfolios:
            prev_data = previous_portfolios[wallet]
            prev_mints = {p['mint'] for p in prev_data['portfolio']}
            
            # 1. Yeni Token Alımı
            for curr in portfolio:
                if curr['mint'] not in prev_mints and curr['value'] > 50: # 50$ üstü yeni alımlar
                    msg = f"🚀 *YENİ TOKEN ALINDI!*\n"
                    msg += f"Cüzdan: `{wallet}`\n"
                    msg += f"Token: [{curr['name']}]({curr['url']})\n"
                    msg += f"Miktar: `{curr['amount']:,.0f}`\n"
                    msg += f"Değer: `${curr['value']:,.2f}`"
                    await send_telegram_message(msg)
            
            # 2. 1000$ Üstü Alım/Satım
            for curr in portfolio:
                prev = next((p for p in prev_data['portfolio'] if p['mint'] == curr['mint']), None)
                if prev:
                    diff_amount = curr['amount'] - prev['amount']
                    diff_value = abs(diff_amount * curr['price'])
                    if diff_value > 1000:
                        action = "ALIM" if diff_amount > 0 else "SATIM"
                        msg = f"🔔 *BÜYÜK İŞLEM ({action})*\n"
                        msg += f"Cüzdan: `{wallet}`\n"
                        msg += f"Token: [{curr['name']}]({curr['url']})\n"
                        msg += f"Değişim Değeri: `${diff_value:,.2f}`"
                        await send_telegram_message(msg)
        
        # Güncelle
        previous_portfolios[wallet] = {
            'total_value': total_value,
            'portfolio': portfolio
        }

async def main():
    print("Bot başlatılıyor...")
    await check_wallets() # İlk kontrol
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_wallets, 'interval', minutes=30)
    scheduler.start()
    
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    asyncio.run(main())
