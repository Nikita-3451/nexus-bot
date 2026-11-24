import telebot
from groq import Groq
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
import threading
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_KEY = os.environ.get("GROQ_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_KEY)
history = []
WEATHER_CHAT_ID = None

def get_weather():
    try:
        response = requests.get("https://wttr.in/Moscow?format=j1")
        data = response.json()
        current = data['current_condition'][0]
        temp = current['temp_C']
        description = current['lang_ru'][0]['value'] if 'lang_ru' in current else current['weatherDesc'][0]['value']
        humidity = current['humidity']
        wind = current['windspeedKmph']
        return f"🌤 Погода в Москве:\n🌡 Температура: {temp}°C\n☁️ {description}\n💧 Влажность: {humidity}%\n💨 Ветер: {wind} км/ч"
    except Exception as e:
        return f"Не удалось получить погоду: {e}"

def send_daily_weather():
    if WEATHER_CHAT_ID:
        weather_text = get_weather()
        bot.send_message(WEATHER_CHAT_ID, f"☀️ Доброе утро!\n\n{weather_text}")
        print("✅ Погода отправлена!")

@bot.message_handler(commands=['start'])
def start(message):
    global WEATHER_CHAT_ID
    WEATHER_CHAT_ID = message.chat.id
    bot.reply_to(message, "Привет! Я Nexus 🤖\n\nТеперь я буду присылать тебе погоду в Москве каждое утро в 8:00!\n\nЗадай мне любой вопрос или напиши /weather.")

@bot.message_handler(commands=['weather'])
def weather_command(message):
    bot.reply_to(message, get_weather())

@bot.message_handler(func=lambda m: True)
def chat(message):
    history.append({"role": "user", "content": message.text})
    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": "Ты дружелюбный и полезный помощник по имени Nexus. Отвечай кратко, понятно и по делу на русском языке."}
            ] + history,
        )
        answer = completion.choices[0].message.content
        history.append({"role": "assistant", "content": answer})
        bot.reply_to(message, answer)
    except Exception as e:
        bot.reply_to(message, "Ой, произошла ошибка. Попробуй еще раз!")
        print("Ошибка:", e)

scheduler = BackgroundScheduler()
scheduler.add_job(send_daily_weather, 'cron', hour=8, minute=0)
scheduler.start()

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

threading.Thread(target=run_flask).start()

print("✅ Бот запущен! Жду сообщений...")
bot.polling(none_stop=True)
