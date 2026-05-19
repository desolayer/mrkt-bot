import requests
import time
import threading
import os
from datetime import datetime

MRKT_TOKEN = os.environ.get("MRKT_TOKEN", "1723deca-50dd-457c-ae7a-b314fe9fa5ca")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
DISCOUNT_THRESHOLD = 0.95
SCAN_INTERVAL = 120

MRKT_HEADERS = {
    "Authorization": MRKT_TOKEN,
    "Content-Type": "application/json",
    "Origin": "https://cdn.tgmrkt.io",
    "Referer": "https://cdn.tgmrkt.io/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

seen_ids = set()
is_paused = False
scan_count = 0
start_time = datetime.now()
last_scan_time = None

def send_telegram(message, chat_id=None):
    if not chat_id:
        chat_id = CHAT_ID
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=data, timeout=10)
        print(f"Отправка сообщения: {r.status_code}")
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def clear_old_updates():
    # Очищаем все старые апдейты при старте
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, params={"offset": -1}, timeout=10)
        data = r.json()
        results = data.get("result", [])
        if results:
            last_id = results[-1]["update_id"]
            requests.get(url, params={"offset": last_id + 1}, timeout=10)
            print(f"Очищено старых апдейтов, последний ID: {last_id}")
    except Exception as e:
        print(f"Ошибка очистки: {e}")

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 10, "offset": offset}
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Ошибка getUpdates: {e}")
    return None

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
        print(f"Ошибка коллекций: {e}")
    return {}

def get_listings(cursor=None):
    url = "https://api.tgmrkt.io/api/v1/gifts/saling"
    body = {
        "count": 50, "cursor": cursor, "ordering": "None",
        "lowToHigh": False, "collectionNames": [], "modelNames": [],
        "backdropNames": [], "symbolNames": []
    }
    try:
        response = requests.post(url, headers=MRKT_HEADERS, json=body, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Ошибка листингов: {e}")
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
                        "id": gift_id, "name": gift.get("name"),
                        "title": gift.get("title"), "collection": collection,
                        "model": gift.get("modelName"), "sale_price": sale_price,
                        "floor_price": floor_price, "discount": discount
                    })
                    seen_ids.add(gift_id)
        cursor = data.get("cursor")
        if not cursor:
            break
        pages += 1
        time.sleep(0.3)
    return new_deals

def handle_command(text, chat_id):
    global is_paused, DISCOUNT_THRESHOLD, seen_ids
    print(f"Обрабатываю команду: {text}")

    cmd = text.split()[0].lower()

    if cmd == "/start":
        msg = (
            "🤖 <b>MRKT Gift Scanner Bot</b>\n\n"
            "Слежу за подарками на MRKT!\n\n"
            "<b>Команды:</b>\n"
            "/start — это сообщение\n"
            "/status — статус бота\n"
            "/floor — топ флорпрайсов\n"
            "/pause — пауза\n"
            "/resume — возобновить\n"
            "/set10 — порог 10%\n"
            "/set15 — порог 15%\n"
            "/set20 — порог 20%\n"
            "/clear — очистить историю"
        )
        send_telegram(msg, chat_id)

    elif cmd == "/status":
        uptime = datetime.now() - start_time
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        status = "⏸ На паузе" if is_paused else "✅ Активен"
        last = last_scan_time.strftime("%H:%M:%S") if last_scan_time else "ещё не было"
        msg = (
            f"📊 <b>Статус</b>\n\n"
            f"Статус: {status}\n"
            f"Аптайм: {hours}ч {minutes}м\n"
            f"Сканирований: {scan_count}\n"
            f"Последнее: {last}\n"
            f"Порог: {int((1-DISCOUNT_THRESHOLD)*100)}%"
        )
        send_telegram(msg, chat_id)

    elif cmd == "/floor":
        floors = get_collections()
        if not floors:
            send_telegram("❌ Ошибка загрузки", chat_id)
            return
        top = sorted(floors.items(), key=lambda x: x[1], reverse=True)[:15]
        msg = "📈 <b>Топ флорпрайсов:</b>\n\n"
        for name, price in top:
            msg += f"• {name}: <b>{price:.2f} TON</b>\n"
        send_telegram(msg, chat_id)

    elif cmd == "/pause":
        is_paused = True
        send_telegram("⏸ Сканирование на паузе", chat_id)

    elif cmd == "/resume":
        is_paused = False
        send_telegram("▶️ Сканирование возобновлено!", chat_id)

    elif cmd == "/set10":
        DISCOUNT_THRESHOLD = 0.90
        send_telegram("✅ Порог: <b>10%</b>", chat_id)

    elif cmd == "/set15":
        DISCOUNT_THRESHOLD = 0.85
        send_telegram("✅ Порог: <b>15%</b>", chat_id)

    elif cmd == "/set20":
        DISCOUNT_THRESHOLD = 0.80
        send_telegram("✅ Порог: <b>20%</b>", chat_id)

    elif cmd == "/clear":
        seen_ids = set()
        send_telegram("🗑 История очищена!", chat_id)

    else:
        send_telegram(f"❓ Неизвестная команда. Напиши /start", chat_id)

def bot_polling():
    offset = None
    print("Polling запущен!")
    while True:
        try:
            updates = get_updates(offset)
            if updates and updates.get("ok"):
                results = updates.get("result", [])
                for update in results:
                    offset = update["update_id"] + 1
                    message = update.get("message", {})
                    text = message.get("text", "")
                    chat_id = str(message.get("chat", {}).get("id", ""))
                    if text and chat_id:
                        print(f"Получена команда: '{text}' от {chat_id}")
                        handle_command(text, chat_id)
        except Exception as e:
            print(f"Ошибка polling: {e}")
            time.sleep(5)

def scanner_loop():
    global scan_count, last_scan_time
    while True:
        if not is_paused:
            scan_count += 1
            now = datetime.now().strftime("%H:%M:%S")
            print(f"[{now}] Сканирование #{scan_count}...", end=" ", flush=True)
            floors = get_collections()
            if floors:
                deals = scan(floors)
                last_scan_time = datetime.now()
                print(f"найдено: {len(deals)}")
                for deal in sorted(deals, key=lambda x: x["discount"], reverse=True):
                    msg = (
                        f"🔥 <b>Подарок ниже флора!</b>\n\n"
                        f"🎁 <b>{deal['title']}</b> ({deal['name']})\n"
                        f"🎨 Модель: {deal['model']}\n\n"
                        f"💰 Цена: <b>{deal['sale_price']:.2f} TON</b>\n"
                        f"📊 Флор: {deal['floor_price']:.2f} TON\n"
                        f"📉 Скидка: <b>-{deal['discount']:.1f}%</b>\n\n"
                        f"🛒 <a href='https://t.me/mrkt_bot?start=gift_{deal['id']}'>Купить на MRKT</a>"
                    )
                    send_telegram(msg)
                    time.sleep(1)
            else:
                print("ошибка")
        time.sleep(SCAN_INTERVAL)

def main():
    print("=" * 50)
    print("  MRKT Gift Scanner Bot")
    print("=" * 50)

    print("Очищаю старые апдейты...")
    clear_old_updates()

    send_telegram(
        "🤖 <b>MRKT Scanner запущен!</b>\n\n"
        "Напиши /start чтобы увидеть команды."
    )
    print("✓ Бот запущен!\n")

    polling_thread = threading.Thread(target=bot_polling, daemon=True)
    polling_thread.start()

    scanner_loop()

if __name__ == "__main__":
    main()
