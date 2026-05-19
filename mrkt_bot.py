import requests
import time
from datetime import datetime

# ===== НАСТРОЙКИ =====
import os

MRKT_TOKEN = os.environ.get("MRKT_TOKEN", "1723deca-50dd-457c-ae7a-b314fe9fa5ca")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
DISCOUNT_THRESHOLD = 0.95  # алерт если цена < 95% от флора
SCAN_INTERVAL = 120  # сканировать каждые 120 секунд
# =====================

MRKT_HEADERS = {
    "Authorization": MRKT_TOKEN,
    "Content-Type": "application/json",
    "Origin": "https://cdn.tgmrkt.io",
    "Referer": "https://cdn.tgmrkt.io/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

seen_ids = set()  # чтобы не присылать одинаковые алерты

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def get_collections():
    url = "https://api.tgmrkt.io/api/v1/gifts/collections"
    try:
        response = requests.get(url, headers=MRKT_HEADERS, timeout=10)
        if response.status_code == 200:
            floors = {}
            for item in response.json():
                name = item.get("name")
                floor = item.get("floorPriceNanoTons", 0)
                if name and floor:
                    floors[name] = floor / 1_000_000_000
            return floors
    except Exception as e:
        print(f"Ошибка загрузки коллекций: {e}")
    return {}

def get_listings(cursor=None):
    url = "https://api.tgmrkt.io/api/v1/gifts/saling"
    body = {
        "count": 50,
        "cursor": cursor,
        "ordering": "None",
        "lowToHigh": False,
        "collectionNames": [],
        "modelNames": [],
        "backdropNames": [],
        "symbolNames": []
    }
    try:
        response = requests.post(url, headers=MRKT_HEADERS, json=body, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Ошибка загрузки листингов: {e}")
    return None

def scan(floors):
    global seen_ids
    new_deals = []
    cursor = None
    pages = 0

    while pages < 5:
        data = get_listings(cursor)
        if not data:
            break

        gifts = data.get("gifts", [])
        if not gifts:
            break

        for gift in gifts:
            gift_id = gift.get("id")
            collection = gift.get("collectionName")
            sale_price = gift.get("salePrice", 0) / 1_000_000_000
            floor_price = floors.get(collection, 0)

            if floor_price > 0 and gift_id not in seen_ids:
                ratio = sale_price / floor_price
                discount = (1 - ratio) * 100

                if ratio < DISCOUNT_THRESHOLD:
                    new_deals.append({
                        "id": gift_id,
                        "name": gift.get("name"),
                        "title": gift.get("title"),
                        "collection": collection,
                        "model": gift.get("modelName"),
                        "sale_price": sale_price,
                        "floor_price": floor_price,
                        "discount": discount
                    })
                    seen_ids.add(gift_id)

        cursor = data.get("cursor")
        if not cursor:
            break
        pages += 1
        time.sleep(0.3)

    return new_deals

def main():
    print("=" * 50)
    print("  MRKT Gift Scanner Bot")
    print("=" * 50)

    # Проверяем настройки
    if "ВСТАВЬ" in BOT_TOKEN or "ВСТАВЬ" in str(CHAT_ID):
        print("\n⚠ ОШИБКА: Вставь BOT_TOKEN и CHAT_ID в начало файла!")
        input("\nНажми Enter для выхода...")
        return

    send_telegram("🤖 <b>MRKT Scanner запущен!</b>\nБуду присылать подарки дешевле флора.")
    print("\n✓ Бот запущен! Жди алертов в Telegram.\n")

    scan_count = 0

    while True:
        scan_count += 1
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] Сканирование #{scan_count}...", end=" ")

        floors = get_collections()
        if not floors:
            print("Ошибка загрузки коллекций")
            time.sleep(30)
            continue

        deals = scan(floors)
        print(f"найдено сделок: {len(deals)}")

        for deal in sorted(deals, key=lambda x: x["discount"], reverse=True):
            discount_pct = deal['discount']
            sale = deal['sale_price']
            floor = deal['floor_price']
            title = deal['title']
            name = deal['name']
            model = deal['model']
            gift_id = deal['id']

            msg = (
                f"🔥 <b>Подарок ниже флора!</b>\n\n"
                f"🎁 <b>{title}</b> ({name})\n"
                f"🎨 Модель: {model}\n\n"
                f"💰 Цена:  <b>{sale:.2f} TON</b>\n"
                f"📊 Флор:  {floor:.2f} TON\n"
                f"📉 Скидка: <b>-{discount_pct:.1f}%</b>\n\n"
                f"🛒 <a href='https://t.me/mrkt_bot?start=gift_{gift_id}'>Купить на MRKT</a>"
            )
            send_telegram(msg)
            print(f"  → Алерт: {title} -{discount_pct:.1f}%")
            time.sleep(1)

        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    main()
