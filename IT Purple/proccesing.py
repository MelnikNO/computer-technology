import os
import logging
import pymongo
import requests
from telebot import TeleBot, types
from transformers import pipeline
from time import time
from typing import List, Dict, Any
import asyncio
import csv

# 1. Настройка
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("Telegram token not found in environment variables.")

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = "shopping_assistant"
CLOTHING_COLLECTION = "clothing_items"
USER_COLLECTION = "users"

WILDBERRIES_API_URL = "https://catalog.wb.ru/catalog/electronic14/v2/catalog"
WILDBERRIES_API_TOKEN = os.environ.get("WILDBERRIES_API_TOKEN", "WILDBERRIES_API_TOKEN")

MODEL_NAME = "meta-llama/Llama-2-7b-chat-hf"

bot = TeleBot(TELEGRAM_TOKEN)

# 2. Инициализация LLM
generator = pipeline("text-generation", model=MODEL_NAME, device_map="auto")

# 3. Инициализация MongoDB
client = pymongo.MongoClient(MONGODB_URI)
db = client[DB_NAME]
clothing_items_collection = db[CLOTHING_COLLECTION]
users_collection = db[USER_COLLECTION]

# 4. Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 5. Состояния диалога
user_states: Dict[int, Dict[str, Any]] = {}
STATE_START = "start"
STATE_OCCASION = "occasion"
STATE_CATEGORY = "category"
STATE_STYLE_PREFERENCES = "style_preferences"
STATE_BUDGET = "budget"
STATE_SHOW_OUTFIT = "show_outfit"
STATE_SIZE = "size"
STATE_COLOR = "color"
STATE_COMPOSITION = "composition"
STATE_ORIGINAL = "original"
STATE_SEASON = "season"

proxies = {
    'http': 'http://bot_proxy:8080',
    'https': 'https://bot_proxy:8080',
}

# 6. Функции для работы с CSV
def load_categories_from_csv(situation: str = None, style: str = None, size: str = None,
                             age_group: str = None, season: str = None, filename="wildberries_menu.csv"):
    """Загружает категории одежды из CSV-файла, фильтруя по заданным параметрам."""
    categories = []
    with open(filename, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if situation and row.get("situation") and situation not in row["situation"].split(","):
                continue
            if style and row.get("style") and style not in row["style"].split(","):
                continue
            if size and row.get("size") and size not in row["size"].split(","):  # Изменили параметр
                continue
            if age_group and row.get("age_group") and age_group not in row["age_group"].split(","):
                continue
            if season and row.get("season") and season not in row["season"].split(","):
                continue

            categories.append(row)
    return categories

# 7. Функции для работы с API Wildberries
async def get_clothing_items_from_api(category_id: str, style_preferences: List[str], budget: int,
                                       size: str, color: str, composition: str, original: str,
                                       season: str) -> List[Dict[str, Any]]:
    """Получает готовые образы с API Wildberries."""
    query_params = {
        'appType': '1',
        'curr': 'rub',
        'dest': '-1185367',
        'sort': 'popular',
        'spp': '30',
        'cat': category_id
    }

    if style_preferences:
        query_params["subject"] = ",".join(style_preferences)

    query_params = {
        'appType': '1',
        'curr': 'rub',
        'dest': '-1185367',
        'sort': 'popular',
        'spp': '30',
        'cat': category_id
    }

    headers = {
        'Accept': '*/*',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'DNT': '1',
        'Origin': 'https://www.wildberries.ru',
        'Referer': 'https://www.wildberries.ru',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Not)A;Brand";v="99", "OpenAI Chrome";v="127", "Chromium";v="127"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    }

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, requests.get, WILDBERRIES_API_URL, headers=headers, params=query_params, proxies=proxies)
        response.raise_for_status()
        data = response.json()

        clothing_items = []
        for item in data["data"]["products"]:
            clothing_items.append({
                "_id": item["id"],
                "name": item["name"],
                "description": item["brand"],
                "price": item["priceU"] / 100,
                "image_url": item["image"],
                "marketplace_url": f"https://www.wildberries.ru/catalog/{item['id']}/detail.aspx",
                "items": [],
                "last_updated": time()
            })
        return clothing_items

    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при запросе к API Wildberries: {e}")
        return []
    except Exception as e:
        logging.exception("Неожиданная ошибка при получении данных из API Wildberries")
        return []

# 8. Функции для работы с базой данных (MongoDB)
def cache_clothing_items(clothing_items: List[Dict[str, Any]]):
    """Кэширует образы в MongoDB."""
    for item in clothing_items:
        existing_item = clothing_items_collection.find_one({"_id": item["_id"]})

        if existing_item:
            clothing_items_collection.update_one({"_id": item["_id"]}, {"$set": item})
            logging.info(f"Обновлен образ {item['name']} в кэше.")
        else:
            clothing_items_collection.insert_one(item)
            logging.info(f"Добавлен образ {item['name']} в кэш.")

def get_cached_clothing_items(occasion: str, style_preferences: List[str], budget: int, body_type: str, age_group: str) -> List[Dict[str, Any]]:
    """Получает закэшированные образы из MongoDB"""
    return list(clothing_items_collection.find({}))

# 9. Функции для работы с LLM
def generate_outfit_description(clothing_items: List[Dict[str, Any]], occasion: str, style_preferences: List[str],
                                 size: str, color: str, composition: str, original: str,
                                 season: str) -> str:
    """Генерирует описание образа с использованием LLM, учитывая все параметры."""
    items_str = ", ".join([item['name'] for item in clothing_items])  # Возвращает названия товаров
    prompt = f"Опиши стильный образ, подходящий для {occasion}. Он состоит из: {items_str}.  Учитывай стиль: {', '.join(style_preferences)}.  Этот образ размера {size}, цвета {color}, и с составом ткани {composition}.  Только оригинальные товары: {original}.  Подходит для сезона: {season}."

    logging.info(f"Prompting LLM: {prompt}")
    try:
        result = generator(prompt, max_length=500, num_return_sequences=1, do_sample=True)
        description = result[0]['generated_text']
    except Exception as e:
        logging.error(f"Error generating description: {e}")
        description = "Не удалось сгенерировать описание для этого образа."
    return description

def format_outfit_result(clothing_items: List[Dict[str, Any]], description: str) -> str:
    """Форматирует результат для отправки пользователю."""
    message = "<b>Рекомендуемый образ:</b>\n\n"
    for item in clothing_items:
        message += f"- <a href='{item['marketplace_url']}'>{item['name']}</a>\n"
        message += f"Описание: {item['description']}\n"
        message += f"Состав: {item['items']}\n\n"
    message += f"\n<b>Описание от AI:</b>\n{description}"
    return message

def send_outfit_result(chat_id: int, outfit: str):
    """Отправляет результат пользователю."""
    bot.send_message(chat_id, outfit, parse_mode="HTML", disable_web_page_preview=True)

# 10. Функции управления интерфейсом (кнопки, сообщения)
def set_occasion_buttons(chat_id: int):
    """Предлагает выбор ситуации (InlineKeyboard)."""
    markup = types.InlineKeyboardMarkup()
    occasions = ["Прогулка в городе", "Прогулка на природе", "Работа в офисе", "Свидание", "Театр", "Бассейн", "Спортзал","Дом"]
    for occasion in occasions:
        item = types.InlineKeyboardButton(occasion, callback_data=f"occasion:{occasion}")
        markup.add(item)

    # ReplyKeyboard для "Назад"
    markup_reply = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    item_back = types.KeyboardButton("Назад")
    markup_reply.add(item_back)

    bot.send_message(chat_id, "Для какой ситуации вы подбираете образ?", reply_markup=markup_reply, reply_to_message_id=None)
    bot.send_message(chat_id, "Выберите один из вариантов:", reply_markup=markup)

    user_states[chat_id] = {"history": [], "data": {}}
    user_states[chat_id]["history"].append({"state": STATE_OCCASION, "data": {}})

def set_category_buttons(chat_id: int, situation: str):
    """Предлагает выбор категории одежды (InlineKeyboard)."""
    categories = load_categories_from_csv(situation=situation)  # Фильтруем категории
    markup = types.InlineKeyboardMarkup()
    for category in categories:
        item = types.InlineKeyboardButton(category["name"], callback_data=f"category:{category['id']}")
        markup.add(item)

    # ReplyKeyboard для "Назад"
    markup_reply = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    item_back = types.KeyboardButton("Назад")
    markup_reply.add(item_back)

    bot.send_message(chat_id, "Выберите категорию одежды:", reply_markup=markup_reply, reply_to_message_id=None)
    bot.send_message(chat_id, "Или введите свою:", reply_markup=markup)

    user_states[chat_id]["history"].append({"state": STATE_CATEGORY, "data": {}})

def set_style_preferences_options(chat_id: int):
    """Запрашивает стилевые предпочтения (InlineKeyboard)."""
    markup = types.InlineKeyboardMarkup()
    styles = ["Классический", "Повседневный", "Элегантный", "Спортивный", "Пляжный", "Домашний"]
    for style in styles:
        item = types.InlineKeyboardButton(style, callback_data=f"style:{style}")
        markup.add(item)
    back_button = types.InlineKeyboardButton("Назад", callback_data="style:back")
    markup.add(back_button)

    # ReplyKeyboard для "Другое" и "Назад"
    markup_reply = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    item_other = types.KeyboardButton("Другое")
    item_back = types.KeyboardButton("Назад")
    markup_reply.add(item_other, item_back)

    bot.send_message(chat_id, "Какие стили вы предпочитаете?", reply_markup=markup_reply, reply_to_message_id=None)
    bot.send_message(chat_id, "Выберите один из вариантов:", reply_markup=markup)
    user_states[chat_id]["history"].append({"state": STATE_STYLE_PREFERENCES, "data": {}})

def set_budget_options(chat_id: int):
    """Запрашивает бюджет (ForceReply)."""
    markup = types.ForceReply(selective=False)
    bot.send_message(chat_id, "Какой у вас бюджет на этот образ (в рублях)?", reply_markup=markup)
    user_states[chat_id]["history"].append({"state": STATE_BUDGET, "data": {}})

def set_size_options(chat_id: int):
    """Запрашивает размер одежды (ForceReply)."""
    markup = types.ForceReply(selective=False)
    bot.send_message(chat_id, "Какой у вас размер одежды? Введите число от 38 до 80", reply_markup=markup)
    user_states[chat_id]["history"].append({"state": STATE_SIZE, "data": {}})

def set_color_options(chat_id: int):
    """Предлагает пользователю выбрать цвет (InlineKeyboard)."""
    markup = types.InlineKeyboardMarkup()
    colors = ["Черный", "Белый", "Красный", "Синий", "Зеленый", "Желтый"]
    for color in colors:
        item = types.InlineKeyboardButton(color, callback_data=f"color:{color}")
        markup.add(item)
    back_button = types.InlineKeyboardButton("Назад", callback_data="color:back")
    markup.add(back_button)

     # ReplyKeyboard для "Другое" и "Назад"
    markup_reply = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    item_other = types.KeyboardButton("Другой")
    item_back = types.KeyboardButton("Назад")
    markup_reply.add(item_other, item_back)

    bot.send_message(chat_id, "Какой цвет вы предпочитаете?", reply_markup=markup_reply, reply_to_message_id=None)
    bot.send_message(chat_id, "Выберите один из вариантов:", reply_markup=markup)
    user_states[chat_id]["history"].append({"state": STATE_COLOR, "data": {}})

def set_composition_options(chat_id: int):
    """Предлагает пользователю выбрать состав ткани (InlineKeyboard)."""
    markup = types.InlineKeyboardMarkup()
    compositions = ["Хлопок", "Шерсть", "Шелк", "Лен", "Синтетика", "Другой"]
    for composition in compositions:
        item = types.InlineKeyboardButton(composition, callback_data=f"composition:{composition}")
        markup.add(item)
    back_button = types.InlineKeyboardButton("Назад", callback_data="composition:back")
    markup.add(back_button)

    # ReplyKeyboard для "Другое" и "Назад"
    markup_reply = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    item_other = types.KeyboardButton("Другой")
    item_back = types.KeyboardButton("Назад")
    markup_reply.add(item_other, item_back)

    bot.send_message(chat_id, "Какой состав ткани вы предпочитаете?", reply_markup=markup_reply,
                     reply_to_message_id=None)
    bot.send_message(chat_id, "Выберите один из вариантов:", reply_markup=markup)
    user_states[chat_id]["history"].append({"state": STATE_COMPOSITION, "data": {}})

def set_original_options(chat_id: int):  # Добавили функцию
    """Предлагает пользователю выбрать, нужен ли оригинальный товар (InlineKeyboard)."""
    markup = types.InlineKeyboardMarkup()
    original_options = ["Да", "Нет"]
    for option in original_options:
        item = types.InlineKeyboardButton(option, callback_data=f"original:{option}")
        markup.add(item)
    back_button = types.InlineKeyboardButton("Назад", callback_data="original:back")
    markup.add(back_button)
    bot.send_message(chat_id, "Нужен ли вам только оригинальный товар?", reply_markup=markup,
                     reply_to_message_id=None)
    bot.send_message(chat_id, "Выберите один из вариантов:", reply_markup=markup)
    user_states[chat_id]["history"].append({"state": STATE_ORIGINAL, "data": {}})

def set_season_options(chat_id: int):
    """Предлагает пользователю выбрать сезон (InlineKeyboard)."""
    markup = types.InlineKeyboardMarkup()
    seasons = ["Демисезон","Зима", "Круглогодичный", "Лето", "Сезон не задан"]
    for season in seasons:
        item = types.InlineKeyboardButton(season, callback_data=f"season:{season}")
        markup.add(item)
    back_button = types.InlineKeyboardButton("Назад", callback_data="season:back")
    markup.add(back_button)

    bot.send_message(chat_id, "Для какого сезона вы ищете одежду?", reply_markup=markup,
                     reply_to_message_id=None)
    bot.send_message(chat_id, "Выберите один из вариантов:", reply_markup=markup)
    user_states[chat_id]["history"].append({"state": STATE_SEASON, "data": {}})

# 11. Проверка состояния пользователя
def check_occasion_state(message: types.Message) -> bool:
    """Проверяет, находится ли пользователь в состоянии выбора ситуации."""
    chat_id = message.chat.id
    if not user_states.get(chat_id) or not user_states[chat_id].get("history"):
        return False
    return user_states[chat_id]["history"][-1]["state"] == STATE_OCCASION

# 12. Обработчики сообщений и callback-запросов
@bot.message_handler(commands=['start'])
def handle_start(message: types.Message):
    """Обработчик команды /start."""
    chat_id = message.chat.id
    logging.info(f"Handling /start command for chat_id: {chat_id}")
    # Добавляем приветственное сообщение
    bot.send_message(chat_id, "Привет! Я помогу тебе подобрать стильный образ. Давай начнем!")
    set_occasion_buttons(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("occasion"))
def handle_occasion_inline(call: types.CallbackQuery):
    """Обработчик выбора ситуации (InlineKeyboard)."""
    chat_id = call.message.chat.id
    occasion = call.data.split(":")[1]
    user_states[chat_id]["data"]["occasion"] = occasion
    set_category_buttons(chat_id, occasion)
    bot.answer_callback_query(call.id)
    logging.info(f"User {chat_id} selected occasion: {occasion}")

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_OCCASION)
def handle_occasion(message: types.Message):
    """Обработчик ввода с клавиатуры (Другое или Назад)."""
    chat_id = message.chat.id
    occasion_text = message.text
    if occasion_text == "Другое":
        bot.send_message(chat_id, "Пожалуйста, введите свой вариант ситуации:",
                         reply_markup=types.ForceReply(selective=True))
    elif occasion_text == "Назад":
        handle_back(chat_id)
    else:
        user_states[chat_id]["data"]["occasion"] = occasion_text
        categories = load_categories_from_csv(situation=occasion_text)

        if not categories:
            bot.send_message(chat_id,
                             "К сожалению, для введенной вами ситуации не найдено подходящих категорий. Пожалуйста, выберите другую ситуацию или категорию.")
            set_occasion_buttons(chat_id)
            return

        set_category_buttons(chat_id, occasion_text)

@bot.callback_query_handler(func=lambda call: call.data.startswith("category"))
def handle_category_inline(call: types.CallbackQuery):
    """Обработчик выбора категории одежды (InlineKeyboard)."""
    chat_id = call.message.chat.id
    category_id = call.data.split(":")[1]
    user_states[chat_id]["data"]["category_id"] = category_id
    set_style_preferences_options(chat_id)
    bot.answer_callback_query(call.id)
    logging.info(f"User {chat_id} selected category: {category_id}")

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_STYLE_PREFERENCES)
def handle_style_preferences(message: types.Message):
    """Обработчик ввода с клавиатуры (Другое или Назад)."""
    chat_id = message.chat.id
    style_text = message.text
    if style_text == "Другое":
        bot.send_message(chat_id, "Пожалуйста, введите свой вариант стиля:", reply_markup=types.ForceReply(selective=True))
    elif style_text == "Назад":
        handle_back(chat_id)
    else:
        user_states[chat_id]["data"]["style_preferences"] = [style_text]
        set_budget_options(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("style"))
def handle_style_inline(call: types.CallbackQuery):
    """Обработчик выбора стиля (InlineKeyboard)."""
    chat_id = call.message.chat.id
    style = call.data.split(":")[1]
    if call.data == "style:back":
        handle_back(chat_id)
        return
    if "style_preferences" not in user_states[chat_id]["data"]:
        user_states[chat_id]["data"]["style_preferences"] = [style]
    else:
        user_states[chat_id]["data"]["style_preferences"].append(style)
    set_budget_options(chat_id)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_BUDGET)
async def handle_budget(message: types.Message):
    chat_id = message.chat.id
    budget = message.text
    try:
        budget = int(budget)
        user_states[chat_id]["data"]["budget"] = budget
        set_size_options(chat_id)  #
    except ValueError:
        bot.send_message(chat_id, "Пожалуйста, введите бюджет числом.")

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_SIZE)
async def handle_size(message: types.Message):
    chat_id = message.chat.id
    size = message.text
    user_states[chat_id]["data"]["size"] = size
    set_color_options(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("color"))
def handle_color_inline(call: types.CallbackQuery):
    """Обработчик выбора цвета (InlineKeyboard)."""
    chat_id = call.message.chat.id
    color = call.data.split(":")[1]
    if call.data == "color:back":
        handle_back(chat_id)
        return

    # Проверяем, есть ли вариант "Другое" и если да, то просим ввести цвет
    if color == "Другой":
        bot.send_message(chat_id, "Пожалуйста, введите предпочитаемый цвет")
    else:
        user_states[chat_id]["data"]["color"] = color
        set_composition_options(chat_id)
        bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_COLOR)
async def handle_color(message: types.Message):
    chat_id = message.chat.id
    color = message.text
    user_states[chat_id]["data"]["color"] = color
    set_composition_options(chat_id)

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_COMPOSITION)
async def handle_composition(message: types.Message):
    chat_id = message.chat.id
    composition = message.text
    user_states[chat_id]["data"]["composition"] = composition
    set_original_options(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("original"))
def handle_original_inline(call: types.CallbackQuery):
    """Обработчик выбора оригинальности товара (InlineKeyboard)."""
    chat_id = call.message.chat.id
    original = call.data.split(":")[1]
    if call.data == "original:back":
        handle_back(chat_id)
        return
    user_states[chat_id]["data"]["original"] = original
    set_season_options(chat_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("color"))
def handle_color_inline(call: types.CallbackQuery):
    """Обработчик выбора цвета (InlineKeyboard)."""
    chat_id = call.message.chat.id
    color = call.data.split(":")[1]
    if call.data == "color:back":
        handle_back(chat_id)
        return

    # Проверяем, есть ли вариант "Другое" и если да, то просим ввести цвет
    if color == "Другой":
        bot.send_message(chat_id, "Пожалуйста, введите предпочитаемый цвет")
    else:
        user_states[chat_id]["data"]["color"] = color
        set_composition_options(chat_id)
        bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_COLOR)
async def handle_color(message: types.Message):
    chat_id = message.chat.id
    color = message.text
    user_states[chat_id]["data"]["color"] = color
    set_composition_options(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("composition"))
def handle_composition_inline(call: types.CallbackQuery):
    """Обработчик выбора состава (InlineKeyboard)."""
    chat_id = call.message.chat.id
    composition = call.data.split(":")[1]
    if call.data == "composition:back":
        handle_back(chat_id)
        return

    # Проверяем, есть ли вариант "Другое" и если да, то просим ввести цвет
    if composition == "Другой":
        bot.send_message(chat_id, "Пожалуйста, введите предпочитаемый состав ткани")
    else:
        user_states[chat_id]["data"]["composition"] = composition
        set_original_options(chat_id)
        bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_COMPOSITION)
async def handle_composition(message: types.Message):
    chat_id = message.chat.id
    composition = message.text
    user_states[chat_id]["data"]["composition"] = composition
    set_original_options(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("original"))
def handle_original_inline(call: types.CallbackQuery):
    """Обработчик выбора оригинальности товара (InlineKeyboard)."""
    chat_id = call.message.chat.id
    original = call.data.split(":")[1]
    if call.data == "original:back":
        handle_back(chat_id)
        return
    user_states[chat_id]["data"]["original"] = original
    set_season_options(chat_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("season"))
async def handle_season_inline(call: types.CallbackQuery):
    """Обработчик выбора сезона (InlineKeyboard)."""
    chat_id = call.message.chat.id
    season = call.data.split(":")[1]

    # Получаем параметры для API
    occasion = user_states[chat_id]["data"].get("occasion")
    category_id = user_states[chat_id]["data"].get("category_id")
    style_preferences = user_states[chat_id]["data"].get("style_preferences", [])
    budget = user_states[chat_id]["data"].get("budget")
    size = user_states[chat_id]["data"].get("size")
    color = user_states[chat_id]["data"].get("color")
    composition = user_states[chat_id]["data"].get("composition")
    original = user_states[chat_id]["data"].get("original")
    season = season

    # Запрашиваем образы с API
    clothing_items = await get_clothing_items_from_api(category_id, style_preferences, budget, size, color, composition, original, season)

    cache_clothing_items(clothing_items)

    # Генерируем описание образа
    outfit_description = generate_outfit_description(clothing_items, occasion, style_preferences, size, color, composition, original, season)

    # Форматируем и отправляем результат
    outfit_result = format_outfit_result(clothing_items, outfit_description)
    send_outfit_result(chat_id, outfit_result)
    bot.answer_callback_query(call.id)

#13. Обработчики ввода сообщений
def handle_back(chat_id: int):
    """Обработчик для кнопки "Назад"."""
    if chat_id not in user_states:
        bot.send_message(chat_id, "Вы в самом начале диалога. Некуда возвращаться.")
        return

    if len(user_states[chat_id]["history"]) > 1:
        user_states[chat_id]["history"].pop()
        previous_state = user_states[chat_id]["history"][-1]["state"]
        if previous_state == STATE_OCCASION:
            set_occasion_buttons(chat_id)
        elif previous_state == STATE_CATEGORY:
            set_category_buttons(chat_id, user_states[chat_id]["data"].get("occasion"))
        elif previous_state == STATE_STYLE_PREFERENCES:
            set_style_preferences_options(chat_id)
        elif previous_state == STATE_BUDGET:
            set_budget_options(chat_id)
        elif previous_state == STATE_SIZE:
            set_size_options(chat_id)
        elif previous_state == STATE_COLOR:
            set_color_options(chat_id)
        elif previous_state == STATE_COMPOSITION:
            set_composition_options(chat_id)
        elif previous_state == STATE_ORIGINAL:
            set_original_options(chat_id)
        elif previous_state == STATE_SEASON:
            set_season_options(chat_id)
        else:
            bot.send_message(chat_id, "Неизвестное предыдущее состояние.")
    else:
        bot.send_message(chat_id, "Вы в самом начале диалога.")

# 14. Запуск бота
if __name__ == "__main__":
    logging.info("Starting Telegram bot...")
    asyncio.run(bot.polling(none_stop=True))