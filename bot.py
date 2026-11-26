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
    if call.data
