import telebot
from groq import Groq
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
import threading
import os
import json
import time
from datetime import datetime
import pytz

# === КЛЮЧИ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_KEY = os.environ.get("GROQ_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

# === ФАЙЛ ДЛЯ СОХРАНЕНИЯ CHAT_ID ===
CHAT_ID_FILE = "chat_id.json"

def load_chat_id():
    if os.path.exists(CHAT_ID_FILE):
        with open(CHAT_ID_FILE, 'r') as f:
            return json.load(f).get("chat_id")
    return None

def save_chat_id(chat_id):
    with open(CHAT_ID_FILE, 'w') as f:
        json.dump({"chat_id": chat_id}, f)

# === ПОГОДА ===
def get_weather():
    try:
        response = requests.get("https://wttr.in/Moscow?format=j1&lang=ru")
        data = response.json()
        current = data['current_condition'][0]
        temp = current['temp_C']
        feels_like = current['FeelsLikeC']
        description = current['lang_ru'][0]['value'] if 'lang_ru' in current else current['weatherDesc'][0]['value']
        humidity = current['humidity']
        wind = current['windspeedKmph']
        return f"🌤 Погода в Москве:\n🌡 Температура: {temp}°C (ощущается как {feels_like}°C)\n☁️ {description}\n💧 Влажность: {humidity}%\n💨 Ветер: {wind} км/ч"
    except Exception as e:
        return f"Не удалось получить погоду: {e}"

def send_daily_weather():
    chat_id = load_chat_id()
    if chat_id:
        weather_text = get_weather()
        now = datetime.now(pytz.timezone('Europe/Moscow'))
        bot.send_message(chat_id, f"☀️ Доброе утро! Сегодня {now.strftime('%d.%m.%Y')}\n\n{weather_text}")
        print(f"✅ Погода отправлена в {now.strftime('%H:%M')} MSK")
    else:
        print("⚠️ Нет сохранённого chat_id. Напиши боту /start")

# === ОБРАБОТЧИКИ КОМАНД ===
@bot.message_handler(commands=['start'])
def start(message):
    save_chat_id(message.chat.id)
    bot.reply_to(message, "Привет! Я Nexus 🤖\n\n✅ Я запомнил тебя и буду присылать погоду каждое утро в 10:00 по Москве!\n\nКоманды:\n/weather — погода сейчас\n/help — помощь\n\nЗадай мне любой вопрос!")

@bot.message_handler(commands=['weather'])
def weather_command(message):
    bot.reply_to(message, get_weather())

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(message, "🤖 Мои команды:\n/start — начать\n/weather — погода сейчас\n/help — эта справка\n\nЯ также отвечаю на обычные вопросы через ИИ!")

@bot.message_handler(func=lambda m: True)
def chat(message):
    # Сначала пробуем через ИИ
    if client:
        try:
            completion = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": "Ты дружелюбный помощник Nexus. Работаешь в Telegram 24/7. Каждое утро в 10:00 по Москве отправляешь погоду. Отвечай кратко на русском."}
                ] + [{"role": "user", "content": message.text}],
            )
            answer = completion.choices[0].message.content
            bot.reply_to(message, answer)
            return
        except Exception as e:
            print(f"Groq ошибка: {e}")
            bot.reply_to(message, "⚠️ ИИ временно недоступен (лимит исчерпан). Но я могу показать погоду! Напиши /weather")
            return
    else:
        bot.reply_to(message, "⚠️ ИИ не настроен. Но я могу показать погоду! Напиши /weather")

# === ПЛАНИРОВЩИК (МОСКОВСКОЕ ВРЕМЯ) ===
scheduler = BackgroundScheduler(timezone=pytz.timezone('Europe/Moscow'))
scheduler.add_job(send_daily_weather, 'cron', hour=10, minute=0, misfire_grace_time=3600)
scheduler.start()

# === FLASK ДЛЯ RENDER ===
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

threading.Thread(target=run_flask, daemon=True).start()

print("✅ Бот запущен! Жду сообщений...")
print(f"🌤 Погода будет присылаться в 10:00 MSK")
print(f"💾 Сохранённый chat_id: {load_chat_id()}")

# === POLLING С АВТОПЕРЕЗАПУСКОМ ===
while True:
    try:
        bot.polling(none_stop=True, interval=1, timeout=60)
    except Exception as e:
        print(f"❌ Polling ошибка: {e}. Перезапуск через 5 секунд...")
        time.sleep(5)
