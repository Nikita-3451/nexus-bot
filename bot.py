import telebot
from groq import Groq
from huggingface_hub import InferenceClient
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
import threading
import os
import json
import time
import random
from datetime import datetime
import pytz

# === КЛЮЧИ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_KEY = os.environ.get("GROQ_KEY")
HF_TOKEN = os.environ.get("HF_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)
groq_client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None
hf_client = InferenceClient(token=HF_TOKEN) if HF_TOKEN else None

# === ФАЙЛЫ ДЛЯ СОХРАНЕНИЯ ===
CHAT_ID_FILE = "chat_id.json"
GAMES_FILE = "games.json"

def load_json(filename, default=None):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default if default is not None else {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# === СОСТОЯНИЕ ===
games = load_json(GAMES_FILE, {"users": {}, "records": {}})
rage_mode = {}  # chat_id -> True/False

def save_games():
    save_json(GAMES_FILE, games)

# === БАЗА ФАКТОВ ===
FACTS = [
    "🦑 У осьминога три сердца и голубая кровь.",
    "🍯 Мёд никогда не портится. Археологи находили съедобный мёд в гробницах фараонов!",
    "🐌 Улитка может спать до 3 лет.",
    "🌍 На Земле больше деревьев, чем звёзд в Млечном Пути (~3 трлн против ~400 млрд).",
    "🦷 Акулы меняют зубы всю жизнь — до 30 000 зубов за жизнь!",
    "🐙 Осьминог может протиснуться в любую щель, куда пролезет его клюв.",
    "⚡ Молния в 5 раз горячее поверхности Солнца.",
    "🧠 Человеческий мозг генерирует около 70 000 мыслей в день.",
    "🐜 Муравьи никогда не спят. У них нет лёгких.",
    "🌊 В океане больше исторических артефактов, чем во всех музеях мира вместе взятых.",
    "🦒 Жирафы спят всего 30 минут в сутки.",
    "🍌 Бананы радиоактивны (слегка) из-за содержания калия-40.",
    "🐦 Колибри — единственная птица, которая может летать назад.",
    "🌙 Луна удаляется от Земли на 3.8 см каждый год.",
    "🦠 В человеческом теле больше бактерий, чем собственных клеток.",
    "🐋 Сердце синего кита размером с маленький автомобиль.",
    "🔥 На Венере день длится дольше, чем год.",
    "🧬 ДНК человека на 60% совпадает с ДНК банана.",
    "🐘 Слоны — единственные животные, которые не умеют прыгать.",
    "⏰ Самая короткая война в истории длилась 38 минут (Англо-занзибарская, 1896).",
    "🌋 На Юпитере идут алмазные дожди.",
    "🐢 Некоторые черепахи могут дышать через задницу. Серьёзно.",
    "🍫 Шоколад использовался как валюта у ацтеков.",
    "🦷 Зубы акулы тверже стали.",
    "🐧 Пингвины делают предложение руки и сердца, даря камешек.",
]

def get_random_fact():
    return random.choice(FACTS)

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
        return f"🌡 {temp}°C (ощущается {feels_like}°C)\n☁️ {description}\n💧 Влажность: {humidity}%\n💨 Ветер: {wind} км/ч"
    except Exception as e:
        return f"Не удалось получить погоду: {e}"

def send_daily_weather():
    chat_id = load_json(CHAT_ID_FILE, {}).get("chat_id")
    if chat_id:
        weather = get_weather()
        fact = get_random_fact()
        now = datetime.now(pytz.timezone('Europe/Moscow'))
        text = (
            f"☀️ Доброе утро! Сегодня {now.strftime('%d.%m.%Y')}\n\n"
            f"🌤 <b>Погода в Москве:</b>\n{weather}\n\n"
            f"🧠 <b>Факт дня:</b>\n{fact}"
        )
        try:
            bot.send_message(chat_id, text, parse_mode="HTML")
            print(f"✅ Утренняя рассылка отправлена в {now.strftime('%H:%M')} MSK")
        except Exception as e:
            print(f"❌ Ошибка рассылки: {e}")
    else:
        print("⚠️ Нет chat_id. Напиши боту /start")

# === ИИ С FALLBACK ===
def get_system_prompt(chat_id):
    base = "Ты дружелюбный помощник Nexus. Работаешь в Telegram 24/7. Каждое утро в 10:00 по Москве отправляешь погоду и интересный факт. Отвечай кратко на русском."
    if rage_mode.get(chat_id):
        return base + " СЕЙЧАС ТЫ В РЕЖИМЕ /RAGE — отвечай дерзко, с сарказмом, чёрным юмором и лёгким матом (без оскорблений пользователя). Можешь использовать слова типа 'блядь', 'сука', 'пиздец' для эмоционального усиления, но не переходи границы. Будь смешным и язвительным."
    return base

def ask_ai(question, chat_id):
    system_prompt = get_system_prompt(chat_id)
    
    if groq_client:
        try:
            completion = groq_client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ],
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Groq ошибка: {e}")
    
    if hf_client:
        try:
            response = hf_client.chat.completions.create(
                model="mistralai/Mistral-7B-Instruct-v0.3",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ],
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"HF ошибка: {e}")
    
    return None

# === ОБРАБОТЧИКИ ===
@bot.message_handler(commands=['start'])
def start(message):
    data = load_json(CHAT_ID_FILE, {})
    data["chat_id"] = message.chat.id
    save_json(CHAT_ID_FILE, data)
    bot.reply_to(message, 
        "Привет! Я Nexus 🤖\n\n"
        "✅ Я запомнил тебя!\n\n"
        "🌤 Погода + факт дня каждое утро в 10:00\n\n"
        "🎮 <b>Команды:</b>\n"
        "/weather — погода сейчас\n"
        "/fact — случайный факт\n"
        "/guess — начать игру 'Угадай число'\n"
        "/rage — включить дерзкий режим 😈\n"
        "/nice — выключить дерзкий режим 😇\n"
        "/help — справка\n\n"
        "Задай любой вопрос!",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['weather'])
def weather_command(message):
    bot.reply_to(message, f"🌤 <b>Погода в Москве:</b>\n{get_weather()}", parse_mode="HTML")

@bot.message_handler(commands=['fact'])
def fact_command(message):
    bot.reply_to(message, f"🧠 <b>Факт дня:</b>\n{get_random_fact()}", parse_mode="HTML")

@bot.message_handler(commands=['guess'])
def guess_command(message):
    chat_id = message.chat.id
    number = random.randint(1, 100)
    games["users"][str(chat_id)] = {"number": number, "attempts": 0}
    save_games()
    bot.reply_to(message, 
        "🎲 <b>Игра 'Угадай число'!</b>\n\n"
        "Я загадал число от 1 до 100. Попробуй угадать!\n"
        "Просто напиши число, и я подскажу — больше или меньше.\n\n"
        f"🏆 Твой рекорд: {games['records'].get(str(chat_id), '—')} попыток",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['rage'])
def rage_command(message):
    rage_mode[message.chat.id] = True
    bot.reply_to(message, "😈 <b>РЕЖИМ ЯРОСТИ АКТИВИРОВАН!</b>\n\nТеперь я буду отвечать дерзко. Чтобы выключить — напиши /nice", parse_mode="HTML")

@bot.message_handler(commands=['nice'])
def nice_command(message):
    rage_mode[message.chat.id] = False
    bot.reply_to(message, "😇 Вернулся в нормальный режим. Как скажешь, босс.")

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(message,
        "🤖 <b>Мои команды:</b>\n\n"
        "/start — начать\n"
        "/weather — погода сейчас\n"
        "/fact — случайный факт\n"
        "/guess — игра 'Угадай число'\n"
        "/rage — дерзкий режим 😈\n"
        "/nice — обычный режим 😇\n"
        "/help — эта справка\n\n"
        "Или просто задай любой вопрос!",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: True)
def chat(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    # Проверяем, играет ли пользователь в "Угадай число"
    if str(chat_id) in games["users"]:
        try:
            guess = int(text)
            game = games["users"][str(chat_id)]
            target = game["number"]
            game["attempts"] += 1
            
            if guess < target:
                bot.reply_to(message, f"📈 Больше! (попытка #{game['attempts']})")
            elif guess > target:
                bot.reply_to(message, f"📉 Меньше! (попытка #{game['attempts']})")
            else:
                attempts = game["attempts"]
                record = games["records"].get(str(chat_id))
                if record is None or attempts < record:
                    games["records"][str(chat_id)] = attempts
                    bot.reply_to(message, 
                        f"🎉 <b>УГАДАЛ!</b> Это было число {target}!\n"
                        f"Попыток: {attempts}\n"
                        f"🏆 <b>НОВЫЙ РЕКОРД!</b>",
                        parse_mode="HTML"
                    )
                else:
                    bot.reply_to(message, 
                        f"🎉 <b>УГАДАЛ!</b> Это было число {target}!\n"
                        f"Попыток: {attempts}\n"
                        f"🏆 Рекорд: {record} попыток",
                        parse_mode="HTML"
                    )
                del games["users"][str(chat_id)]
            save_games()
            return
        except ValueError:
            pass  # Не число — продолжаем как обычный чат
    
    # Обычный чат через ИИ
    answer = ask_ai(text, chat_id)
    if answer:
        bot.reply_to(message, answer)
    else:
        bot.reply_to(message, "⚠️ ИИ сейчас недоступен. Но базовые функции работают!\n\n/weather — погода\n/fact — факт\n/guess — игра")

# === ПЛАНИРОВЩИК ===
scheduler = BackgroundScheduler(timezone=pytz.timezone('Europe/Moscow'))
scheduler.add_job(send_daily_weather, 'cron', hour=10, minute=0, misfire_grace_time=3600)
scheduler.start()

# === FLASK ===
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

print("✅ Бот запущен!")
print(f"🌤 Погода + факт в 10:00 MSK")
print(f"🤖 Groq: {'✅' if groq_client else '❌'} | HF: {'✅' if hf_client else '❌'}")

while True:
    try:
        bot.polling(none_stop=True, interval=1, timeout=60)
    except Exception as e:
        print(f"❌ Polling ошибка: {e}. Перезапуск через 5 сек...")
        time.sleep(5)
