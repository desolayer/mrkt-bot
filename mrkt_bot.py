import requests
import time
import threading
import os
from datetime import datetime

# ===== НАСТРОЙКИ =====
MRKT_TOKEN = os.environ.get("MRKT_TOKEN", "1723deca-50dd-457c-ae7a-b314fe9fa5ca")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
DISCOUNT_THRESHOLD = 0.95
SCAN_INTERVAL = 120
# =====================

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
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    try:
        response = requests.get(url, params=params, timeout=35)
        if response.status_code == 200:
            return response.json()
    except:
        pass
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

def handle_command(text, chat_id):
    global is_paused, DISCOUNT_THRESHOLD, seen_ids

    if text == "/start":
        msg = (
            "🤖 <b>MRKT Gift Scanner Bot</b>\n\n"
            "Я слежу за подарками на MRKT и присылаю алерты когда цена ниже флора!\n\n"
            "<b>Команды:</b>\n"
            "/start — это сообщение\n"
            "/status — статус бота\n"
            "/floor — топ флорпрайсов\n"
            "/pause — пауза сканирования\n"
            "/resume — возобновить\n"
            "/threshold — текущий порог скидки\n"
            "/set10 — порог 10%\n"
            "/set15 — порог 15%\n"
            "/set20 — порог 20%\n"
            "/clear — очистить историю алертов"
        )
        send_telegram(msg, chat_id)

    elif text == "/status":
        uptime = datetime.now() - start_time
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        status = "⏸ На паузе" if is_paused else "✅ Активен"
        last = last_scan_time.strftime("%H:%M:%S") if last_scan_time else "ещё не сканировал"
        msg = (
            f"📊 <b>Статус бота</b>\n\n"
            f"Статус: {status}\n"
            f"Аптайм: {hours}ч {minutes}м\n"
            f"Сканирований: {scan_count}\n"
            f"Последнее: {last}\n"
            f"Порог скидки: {int((1 - DISCOUNT_THRESHOLD) * 100)}%\n"
            f"Интервал: каждые {SCAN_INTERVAL} сек"
        )
        send_telegram(msg, chat_id)

    elif text == "/floor":
        floors = get_collections()
        if not floors:
            send_telegram("❌ Не удалось загрузить данные", chat_id)
            return
        sorted_floors = sorted(floors.items(), key=lambda x: x[1], reverse=True)[:15]
        msg = "📈 <b>Топ флорпрайсов коллекций:</b>\n\n"
        for name, price in sorted_floors:
            msg += f"• {name}: <b>{price:.2f} TON</b>\n"
        send_telegram(msg, chat_id)

    elif text == "/pause":
        is_paused = True
        send_telegram("⏸ Сканирование приостановлено", chat_id)

    elif text == "/resume":
        is_paused = False
        send_telegram("▶️ Сканирование возобновлено!", chat_id)

    elif text == "/threshold":
        pct = int((1 - DISCOUNT_THRESHOLD) * 100)
        send_telegram(f"📉 Текущий порог скидки: <b>{pct}%</b>\n\nИзменить: /set10 /set15 /set20", chat_id)

    elif text == "/set10":
        DISCOUNT_THRESHOLD = 0.90
        send_telegram("✅ Порог скидки установлен: <b>10%</b>", chat_id)

    elif text == "/set15":
        DISCOUNT_THRESHOLD = 0.85
        send_telegram("✅ Порог скидки установлен: <b>15%</b>", chat_id)

    elif text == "/set20":
        DISCOUNT_THRESHOLD = 0.80
        send_telegram("✅ Порог скидки установлен: <b>20%</b>", chat_id)

    elif text == "/clear":
        seen_ids = set()
        send_telegram("🗑 История алертов очищена! Буду присылать все подарки заново.", chat_id)

def bot_polling():
    offset = None
    print("Слушаю команды...")
    while True:
        try:
            updates = get_updates(offset)
            if updates and updates.get("ok"):
                for update in updates.get("result", []):
                    offset = update["update_id"] + 1
                    message = update.get("message", {})
                    text = message.get("text", "")
                    chat_id = message.get("chat", {}).get("id")
                    if text and chat_id:
                        print(f"Команда: {text} от {chat_id}")
                        handle_command(text, str(chat_id))
        except Exception as e:
            print(f"Ошибка polling: {e}")
            time.sleep(5)

def scanner_loop():
    global scan_count, last_scan_time
    while True:
        if not is_paused:
            scan_count += 1
            now = datetime.now().strftime("%H:%M:%S")
            print(f"[{now}] Сканирование #{scan_count}...", end=" ")
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
                        f"💰 Цена:  <b>{deal['sale_price']:.2f} TON</b>\n"
                        f"📊 Флор:  {deal['floor_price']:.2f} TON\n"
                        f"📉 Скидка: <b>-{deal['discount']:.1f}%</b>\n\n"
                        f"🛒 <a href='https://t.me/mrkt_bot?start=gift_{deal['id']}'>Купить на MRKT</a>"
                    )
                    send_telegram(msg)
                    time.sleep(1)
            else:
                print("ошибка загрузки")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] На паузе...")
        time.sleep(SCAN_INTERVAL)

def main():
    print("=" * 50)
    print("  MRKT Gift Scanner Bot")
    print("=" * 50)

    send_telegram(
        "🤖 <b>MRKT Scanner запущен!</b>\n\n"
        "Буду присылать подарки дешевле флора.\n"
        "Напиши /start чтобы увидеть все команды."
    )
    print("✓ Бот запущен! Жди алертов в Telegram.\n")

    polling_thread = threading.Thread(target=bot_polling, daemon=True)
    polling_thread.start()

    scanner_loop()

if __name__ == "__main__":
    main()
