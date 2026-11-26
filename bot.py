import telebot
from telebot import types
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
rage_mode = {}      # дерзкий режим
deep_mode = {}      # режим философа

def save_games():
    save_json(GAMES_FILE, games)

# === КЛАВИАТУРА ===
def get_menu_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🌤 Погода", callback_data="cmd_weather"),
        types.InlineKeyboardButton("🧠 Факт", callback_data="cmd_fact")
    )
    keyboard.add(
        types.InlineKeyboardButton("🎲 Угадай число", callback_data="cmd_guess"),
        types.InlineKeyboardButton("🍷 Философ", callback_data="cmd_deep")
    )
    keyboard.add(
        types.InlineKeyboardButton("😈 Дерзкий", callback_data="cmd_rage"),
        types.InlineKeyboardButton("😇 Обычный", callback_data="cmd_nice")
    )
    keyboard.add(
        types.InlineKeyboardButton("❓ Помощь", callback_data="cmd_help")
    )
    return keyboard

def show_menu(chat_id, text="📋 <b>Выбери команду:</b>"):
    bot.send_message(chat_id, text, reply_markup=get_menu_keyboard(), parse_mode="HTML")

# === ОБРАБОТКА КНОПОК ===
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    handlers = {
        "cmd_weather": lambda: bot.send_message(call.message.chat.id, f"🌤 <b>Погода в Москве:</b>\n{get_weather()}", parse_mode="HTML"),
        "cmd_fact": lambda: bot.send_message(call.message.chat.id, f"🧠 <b>Факт дня:</b>\n{get_random_fact()}", parse_mode="HTML"),
        "cmd_guess": lambda: guess_command(call.message),
        "cmd_rage": lambda: _set_mode(call.message.chat.id, "rage"),
        "cmd_nice": lambda: _set_mode(call.message.chat.id, "nice"),
        "cmd_deep": lambda: _set_mode(call.message.chat.id, "deep"),
        "cmd_help": lambda: help_command(call.message),
    }
    bot.answer_callback_query(call.id)
    if call.data in handlers:
        handlers[call.data]()
        if call.data not in ("cmd_guess",):
            show_menu(call.message.chat.id)

def _set_mode(chat_id, mode):
    if mode == "rage":
        rage_mode[chat_id] = True
        deep_mode[chat_id] = False
        bot.send_message(chat_id, "😈 <b>РЕЖИМ ЯРОСТИ АКТИВИРОВАН!</b>\n\nОтвечаю дерзко.", parse_mode="HTML")
    elif mode == "deep":
        deep_mode[chat_id] = True
        rage_mode[chat_id] = False
        bot.send_message(chat_id, 
            "🍷 <b>РЕЖИМ ФИЛОСОФА АКТИВИРОВАН!</b>\n\n"
            "Теперь я буду рассуждать глубоко, с матом и жизненными аналогиями.\n"
            "Задай мне любой вопрос — типа 'в чём смысл жизни' или 'стакан наполовину пуст или полон'.\n\n"
            "Чтобы выключить — нажми 😇 Обычный",
            parse_mode="HTML"
        )
    elif mode == "nice":
        rage_mode[chat_id] = False
        deep_mode[chat_id] = False
        bot.send_message(chat_id, "😇 Вернулся в нормальный режим.")

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

# === СИСТЕМНЫЕ ПРОМПТЫ ===
DEEP_PROMPT = """Ты — философ-алкоголик с жизненным опытом, который сидит с другом на кухне в 3 часа ночи. 
Ты рассуждаешь ГЛУБОКО, но простым языком, с МАТОМ (блядь, сука, пиздец, нахуй, хуйня и т.д.), 
с неожиданными аналогиями из жизни, алкоголя, отношений, работы. 

ПРАВИЛА:
1. Используй мат естественно, как русский человек в баре — для усиления эмоций, не для оскорблений
2. Начинай с неожиданного поворота ("Блядь, это как...", "Слышь, вопрос не в том...")
3. Делай аналогии из реальной жизни: погода, бухло, бабы, работа, пробки, соседи
4. В конце всегда неожиданный философский вывод, который переворачивает вопрос
5. Отвечай на русском, 3-6 предложений, без списков
6. Обращайся к собеседнику как к другу: "брат", "слышь", "понимаешь"

ПРИМЕР стиля:
Вопрос: "Стакан наполовину пуст или полон?"
Ответ: "Блядь, брат, это как погода — для одних прекрасная, для других ну её нахуй. 
И вопрос-то не в том, наполовину ли пуст стакан, а с кем ты его пьёшь и какие чувства испытываешь. 
Понимаешь, сука, в чём прикол? Полстакана — это не математика, это настроение. 
Если рядом хороший человек — хоть пустой стакан, хоть без стакана, хоть вообще без крыши над головой — всё пиздец как хорошо."""

RAGE_PROMPT = """Ты дружелюбный помощник Nexus, но СЕЙЧАС в режиме ЯРОСТИ. 
Отвечай дерзко, с сарказмом, чёрным юмором и лёгким матом (блядь, сука, пиздец). 
Без оскорблений пользователя. Будь смешным и язвительным. Отвечай кратко на русском."""

NORMAL_PROMPT = """Ты дружелюбный помощник Nexus. Работаешь в Telegram 24/7. 
Каждое утро в 10:00 по Москве отправляешь погоду и интересный факт. 
Отвечай кратко на русском."""

def get_system_prompt(chat_id):
    if deep_mode.get(chat_id):
        return DEEP_PROMPT
    if rage_mode.get(chat_id):
        return RAGE_PROMPT
    return NORMAL_PROMPT

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
        "👇 <b>Выбери команду или просто задай вопрос:</b>",
        parse_mode="HTML"
    )
    show_menu(message.chat.id)

@bot.message_handler(commands=['menu'])
def menu_command(message):
    show_menu(message.chat.id)

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
    record = games["records"].get(str(chat_id), "—")
    bot.reply_to(message, 
        f"🎲 <b>Игра 'Угадай число'!</b>\n\n"
        f"Я загадал число от 1 до 100. Попробуй угадать!\n"
        f"Просто напиши число, и я подскажу — больше или меньше.\n\n"
        f"🏆 Твой рекорд: {record} попыток",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['rage'])
def rage_command(message):
    _set_mode(message.chat.id, "rage")

@bot.message_handler(commands=['deep'])
def deep_command(message):
    _set_mode(message.chat.id, "deep")

@bot.message_handler(commands=['nice'])
def nice_command(message):
    _set_mode(message.chat.id, "nice")

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(message,
        "🤖 <b>Мои команды:</b>\n\n"
        "/start — начать\n"
        "/menu — показать меню\n"
        "/weather — погода сейчас\n"
        "/fact — случайный факт\n"
        "/guess — игра 'Угадай число'\n"
        "/rage — дерзкий режим 😈\n"
        "/deep — режим философа 🍷\n"
        "/nice — обычный режим 😇\n"
        "/help — эта справка\n\n"
        "Или просто задай любой вопрос!",
        parse_mode="HTML"
    )
    show_menu(message.chat.id)

@bot.message_handler(func=lambda m: True)
def chat(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    # Игра "Угадай число"
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
            show_menu(chat_id)
            return
        except ValueError:
            pass
    
    # ИИ-ответ
    answer = ask_ai(text, chat_id)
    if answer:
        bot.reply_to(message, answer)
    else:
        bot.reply_to(message, "⚠️ ИИ сейчас недоступен.")
    show_menu(chat_id)

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
