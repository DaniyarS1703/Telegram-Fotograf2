import os
import time
import threading
import logging

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telebot.apihelper import ApiTelegramException

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === КОНСТАНТЫ ===
TELEGRAM_TOKEN = os.environ.get(
    "TELEGRAM_TOKEN",
    "7377508266:AAHv1EKkXgP3AjVbcJHnaf505N-37HELKQw"
)
API_KEY = os.environ.get("API_KEY", "77777")

bg_colors = [
    ("⬜", "white"), ("⬛", "black"), ("🟥", "red"), ("🟦", "blue"),
    ("🟩", "green"), ("🟨", "yellow"), ("🟧", "orange"),
    ("🟪", "purple"), ("🟫", "brown")
]
text_colors = [
    ("⚪", "white"), ("⚫", "black"), ("🔴", "red"), ("🔵", "blue"),
    ("🟢", "green"), ("🟡", "yellow"), ("🟠", "orange"),
    ("🟣", "purple"), ("🟤", "brown")
]
sizes = [
    ("100", "100"), ("120", "120"), ("140", "140"), ("160", "160"),
    ("180", "180"), ("200", "200"), ("220", "220"), ("240", "240"),
]
speed_options = [
    ("🐢 1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"),
    ("6", "6"), ("7", "7"), ("8", "8"), ("9", "9"), ("⚡️ 10", "10")
]
direction_options = [
    ("⬅️ Влево", "left"),
    ("🖥️ Экран",  "bounce"),
    ("🔒 Закрепить", "static")
]

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
latest_command = {
    "text": "Поздравляем с праздником! EMO",
    "color": "black",
    "bg": "white",
    "size": "100",
    "direction": "left",
    "speed": "3"
}
waiting_text = {}

# === ИНИЦИАЛИЗАЦИЯ ===
app = Flask(__name__)
CORS(app)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === УТИЛИТЫ ===
def safe_edit_reply_markup(chat_id, message_id, reply_markup):
    try:
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup
        )
    except ApiTelegramException as e:
        if "message is not modified" in str(e):
            return
        logger.exception("Ошибка при редактировании разметки")
        raise

# === КЛАВИАТУРЫ ===
def menu_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🎨 Меню"))
    return kb

def bg_keyboard():
    current = latest_command["bg"]
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = [
        InlineKeyboardButton(f"{emoji} {'✅' if color==current else ''}",
                             callback_data=f"setbg:{color}")
        for emoji, color in bg_colors
    ]
    for i in range(0, len(buttons), 3):
        kb.add(*buttons[i:i+3])
    kb.add(
        InlineKeyboardButton("Цвет текста", callback_data="show_text_colors"),
        InlineKeyboardButton("Размер шрифта", callback_data="show_sizes")
    )
    kb.add(InlineKeyboardButton("Изменить текст", callback_data="edit_text"))
    kb.add(
        InlineKeyboardButton("Скорость", callback_data="show_speed"),
        InlineKeyboardButton("Направление", callback_data="show_direction")
    )
    return kb

def text_color_keyboard():
    current = latest_command["color"]
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = [
        InlineKeyboardButton(f"{emoji} {'✅' if color==current else ''}",
                             callback_data=f"setcolor:{color}")
        for emoji, color in text_colors
    ]
    for i in range(0, len(buttons), 3):
        kb.add(*buttons[i:i+3])
    kb.add(
        InlineKeyboardButton("Цвет фона", callback_data="show_bg"),
        InlineKeyboardButton("Размер шрифта", callback_data="show_sizes")
    )
    kb.add(InlineKeyboardButton("Изменить текст", callback_data="edit_text"))
    kb.add(
        InlineKeyboardButton("Скорость", callback_data="show_speed"),
        InlineKeyboardButton("Направление", callback_data="show_direction")
    )
    kb.add(InlineKeyboardButton("◀️ Меню", callback_data="to_menu"))
    return kb

def size_keyboard():
    current = latest_command["size"]
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(f"{name} {'✅' if val==current else ''}",
                             callback_data=f"setsize:{val}")
        for name, val in sizes
    ]
    kb.add(*buttons)
    kb.add(
        InlineKeyboardButton("Цвет фона", callback_data="show_bg"),
        InlineKeyboardButton("Цвет текста", callback_data="show_text_colors")
    )
    kb.add(InlineKeyboardButton("Изменить текст", callback_data="edit_text"))
    kb.add(
        InlineKeyboardButton("Скорость", callback_data="show_speed"),
        InlineKeyboardButton("Направление", callback_data="show_direction")
    )
    kb.add(InlineKeyboardButton("◀️ Меню", callback_data="to_menu"))
    return kb

def speed_keyboard():
    current = latest_command["speed"]
    kb = InlineKeyboardMarkup(row_width=5)
    buttons = [
        InlineKeyboardButton(f"{name} {'✅' if val==current else ''}",
                             callback_data=f"setspeed:{val}")
        for name, val in speed_options
    ]
    kb.add(*buttons)
    kb.add(InlineKeyboardButton("◀️ Меню", callback_data="to_menu"))
    return kb

def direction_keyboard():
    current = latest_command["direction"]
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = [
        InlineKeyboardButton(f"{name} {'✅' if val==current else ''}",
                             callback_data=f"setdirection:{val}")
        for name, val in direction_options
    ]
    kb.add(*buttons)
    kb.add(InlineKeyboardButton("◀️ Меню", callback_data="to_menu"))
    return kb

# === ОБРАБОТЧИКИ ТЕЛЕБОТА ===
@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(
        message.chat.id,
        "Добро пожаловать! Управляй бегущей строкой кнопками 🎨 Меню ниже.",
        reply_markup=menu_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == "🎨 Меню")
def show_main_menu(message):
    bot.send_message(
        message.chat.id,
        "Измените цвет фона:",
        reply_markup=bg_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data == "to_menu")
def callback_to_menu(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "Измените цвет фона:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=bg_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("setbg:"))
def callback_set_bg(call):
    color = call.data.split(":",1)[1]
    latest_command["bg"] = color
    bot.answer_callback_query(call.id, "Фон сменён!")
    bot.edit_message_text(
        "Измените цвет фона:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=bg_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data == "show_text_colors")
def show_text_colors(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "Измените цвет текста:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=text_color_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data == "show_bg")
def show_bg(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "Измените цвет фона:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=bg_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data == "show_sizes")
def show_sizes(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "Измените размер шрифта:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=size_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data == "show_speed")
def show_speed(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "Измените скорость:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=speed_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data == "show_direction")
def show_direction(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "Измените направление:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=direction_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("setcolor:"))
def callback_set_color(call):
    color = call.data.split(":",1)[1]
    latest_command["color"] = color
    bot.answer_callback_query(call.id, f"Цвет текста: {color}")
    bot.edit_message_text(
        "Измените цвет текста:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=text_color_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("setsize:"))
def callback_set_size(call):
    size = call.data.split(":",1)[1]
    latest_command["size"] = size
    bot.answer_callback_query(call.id, f"Размер шрифта: {size}")
    bot.edit_message_text(
        "Измените размер шрифта:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=size_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("setspeed:"))
def callback_set_speed(call):
    speed = call.data.split(":",1)[1]
    latest_command["speed"] = speed
    bot.answer_callback_query(call.id, f"Скорость: {speed}")
    bot.edit_message_text(
        "Измените скорость:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=speed_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("setdirection:"))
def callback_set_direction(call):
    mode = call.data.split(":",1)[1]
    latest_command["direction"] = mode
    text = {
        "left":   "Режим: ⬅️ Классика",
        "bounce": "Режим: 🖥️ Экран",
        "static": "Режим: 🔒 Закрепить текст"
    }.get(mode, "")
    bot.answer_callback_query(call.id, text)
    bot.edit_message_text(
        "Измените направление:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=direction_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data == "edit_text")
def callback_edit_text(call):
    waiting_text[call.from_user.id] = True
    bot.answer_callback_query(call.id, "Введи новый текст")
    bot.edit_message_text(
        "Отправь новый текст для бегущей строки:",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    uid = message.from_user.id
    if waiting_text.get(uid):
        latest_command["text"] = message.text.strip()
        waiting_text[uid] = False
        bot.reply_to(message, "Текст обновлён!")
    else:
        text = message.text.strip()
        up = text.upper()
        if up.startswith("ТЕКСТ:"):
            latest_command["text"] = text[6:].strip()
            bot.reply_to(message, "Текст обновлён!")
        elif up.startswith("ЦВЕТ:"):
            latest_command["color"] = text[5:].strip()
            bot.reply_to(message, "Цвет текста обновлён!")
        elif up.startswith("ФОН:"):
            latest_command["bg"] = text[4:].strip()
            bot.reply_to(message, "Цвет фона обновлён!")
        elif up.startswith("РАЗМЕР:"):
            try:
                latest_command["size"] = str(int(text[7:].strip()))
                bot.reply_to(message, "Размер шрифта обновлён!")
            except:
                bot.reply_to(message, "Ошибка: размер — только число.")
        else:
            bot.reply_to(
                message,
                "Используй кнопки 🎨 Меню ниже или команды:\n"
                "ТЕКСТ: ...\nЦВЕТ: ...\nФОН: ...\nРАЗМЕР: ..."
            )

# === REST API ===
@app.route('/api/latest', methods=['GET'])
def api_latest():
    apikey = request.args.get("apikey")
    if apikey != API_KEY:
        return jsonify({"error": "unauthorized"}), 403
    return jsonify(latest_command)

@app.route('/')
def index():
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)),
        'index.html'
    )

# === ОБРАБОТЧИК ОШИБОК FLASK ===
@app.errorhandler(Exception)
def handle_exception(e):
    logger.exception("Unhandled exception in Flask:")
    return "Internal Server Error", 500

# === ЗАПУСК ===
if __name__ == '__main__':
    def run_bot():
        while True:
            try:
                bot.polling(none_stop=True)
            except Exception:
                logger.exception("Polling упал, перезапуск через 15 секунд")
                time.sleep(15)

    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
