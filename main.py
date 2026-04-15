import os
import time
import json
import requests
from datetime import datetime

WB_API_KEY = os.environ.get("WB_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL_MINUTES", "30")) * 60

PRODUCT_CATEGORY = "одежда и обувь"
ANSWERED_FILE = "answered_reviews.json"

def load_answered():
    if os.path.exists(ANSWERED_FILE):
        with open(ANSWERED_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_answered(answered):
    with open(ANSWERED_FILE, "w") as f:
        json.dump(list(answered), f)

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def get_unanswered_reviews():
    url = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks"
    headers = {"Authorization": WB_API_KEY}
    params = {
        "isAnswered": False,
        "take": 100,
        "skip": 0,
        "order": "dateDesc"
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("feedbacks", [])
    except Exception as e:
        print(f"[{now()}] Ошибка получения отзывов: {e}")
        return []

def generate_reply(review_text, rating):
    if rating <= 2:
        tone = "извиняющийся, предложи решение проблемы"
    elif rating == 3:
        tone = "нейтральный, поблагодари и учти замечания"
    else:
        tone = "дружелюбный и тёплый, поблагодари и пригласи снова"

    prompt = f"""Ты — вежливый продавец {PRODUCT_CATEGORY} на Wildberries.
Напиши ответ на отзыв покупателя.

Оценка: {rating} из 5
Отзыв: "{review_text}"
Тон: {tone}

Требования:
- Ответ на русском, обращение на "Вы"
- 3-5 предложений, живой язык
- Не начинай с "Спасибо за отзыв"
- Только текст ответа, без пояснений"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 400, "temperature": 0.7}
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[{now()}] Ошибка Gemini: {e}")
        return None

def post_reply(feedback_id, reply_text):
    url = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks"
    headers = {
        "Authorization": WB_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"id": feedback_id, "text": reply_text}
    try:
        resp = requests.patch(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[{now()}] Ошибка отправки ответа: {e}")
        return False

def run():
    print(f"[{now()}] Бот запущен. Интервал: {CHECK_INTERVAL//60} мин.")
    answered = load_answered()

    while True:
        print(f"[{now()}] Проверяю новые отзывы...")
        reviews = get_unanswered_reviews()
        new_count = 0

        for review in reviews:
            rid = review.get("id")
            if not rid or rid in answered:
                continue

            text = review.get("text", "").strip()
            rating = review.get("productValuation", 5)

            if not text:
                answered.add(rid)
                continue

            print(f"[{now()}] Отзыв {rid} | Оценка: {rating}★ | {text[:60]}...")

            reply = generate_reply(text, rating)
            if not reply:
                print(f"[{now()}] Пропускаю {rid} — не удалось сгенерировать ответ")
                continue

            success = post_reply(rid, reply)
            if success:
                print(f"[{now()}] ✓ Отправлено: {reply[:80]}...")
                answered.add(rid)
                new_count += 1
                save_answered(answered)
                time.sleep(3)
            else:
                print(f"[{now()}] ✗ Ошибка отправки {rid}")

        print(f"[{now()}] Готово. Новых: {new_count}. Следующая проверка через {CHECK_INTERVAL//60} мин.")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run()
