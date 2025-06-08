import os
import logging
import pymongo
import requests
from telebot import TeleBot, types
from transformers import pipeline
from time import time
from typing import List, Dict, Any
import asyncio

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
STATE_STYLE_PREFERENCES = "style_preferences"
STATE_BUDGET = "budget"
STATE_SHOW_OUTFIT = "show_outfit"
STATE_BODY_TYPE = "body_type"
STATE_AGE_GROUP = "age_group"

proxies = {
    'http': 'http://proxy:8080',
    'https': 'https://proxy:8080',
}

categories_by_situation = {
        "Прогулка": ["Джинсы", "Футболки", "Кеды", "Куртки"],
        "Работа": ["Блузки", "Брюки", "Юбки", "Пиджаки"],
        "Свидание": ["Платья", "Туфли", "Аксессуары"]
}

# 6. Функции для работы с API Wildberries
async def get_clothing_items_from_api(occasion: str, category: str, style_preferences: List[str], budget: int, body_type: str, age_group: str) -> List[Dict[str, Any]]:
    """Получает готовые образы с API Wildberries."""
    query_params = {
        'appType': '1',
        'curr': 'rub',
        'dest': '-1185367',
        'sort': 'popular',
        'spp': '30',
        'cat': category
    }

    if style_preferences:
        query_params["subject"] = ",".join(style_preferences)

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
        'sec-ch-ua': '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    }

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, requests.get, WILDBERRIES_API_URL, headers=headers, params=query_params, proxies=proxies)
        response.raise_for_status()
        data = response.json()

        # Адаптация структуры данных API Wildberries
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

# 7. Функции для работы с базой данных (MongoDB)
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
    """Получает закэшированные образы из MongoDB (TODO: добавить фильтрацию)."""
    return list(clothing_items_collection.find({}))

# 8. Функции для работы с LLM
def generate_outfit_description(clothing_items: List[Dict[str, Any]], occasion: str, style_preferences: List[str], body_type: str, age_group: str) -> str:
    """Генерирует описание образа с использованием LLM, учитывая тип фигуры и возраст."""
    items_str = ", ".join([item['name'] for item in clothing_items])
    prompt = f"Опиши образ '{items_str}', подходящий для {occasion}. Учитывай, что предпочитаемый стиль: {', '.join(style_preferences)}. Также учти, что тип фигуры: {body_type}, возраст: {age_group}. Объясни, почему этот образ подходит для этого типа фигуры и возраста, и дай советы по аксессуарам. "

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

# 9. Функции управления интерфейсом
def set_occasion_buttons(chat_id: int):
    """Предлагает выбор ситуации (InlineKeyboard)."""
    markup = types.InlineKeyboardMarkup()
    occasions = ["Прогулка", "Работа", "Свидание", "Встреча с друзьями", "Особый случай", "Любая"]
    for occasion in occasions:
        item = types.InlineKeyboardButton(occasion, callback_data=f"occasion:{occasion}")
        markup.add(item)

    # ReplyKeyboard для "Другое" и "Назад"
    markup_reply = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    item_other = types.KeyboardButton("Другое")
    item_back = types.KeyboardButton("Назад")
    markup_reply.add(item_other, item_back)

    bot.send_message(chat_id, "Выберите один из вариантов:", reply_markup=markup)

    user_states[chat_id] = {"history": [], "data": {}}  # Инициализация
    user_states[chat_id]["history"].append({"state": STATE_OCCASION, "data": {}})

def set_style_preferences_options(chat_id: int):
    """Запрашивает стилевые предпочтения (InlineKeyboard)."""
    markup = types.InlineKeyboardMarkup()
    styles = ["Классический", "Повседневный", "Элегантный", "Спортивный", "Бохо", "Минимализм"]
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

def set_body_type_options(chat_id: int):
    """Предлагает пользователю выбрать тип фигуры (InlineKeyboard)."""
    markup = types.InlineKeyboardMarkup()
    body_types = ["Песочные часы", "Прямоугольник", "Яблоко", "Груша"]
    for body_type in body_types:
        item = types.InlineKeyboardButton(body_type, callback_data=f"body_type:{body_type}")
        markup.add(item)

    # ReplyKeyboard для "Другое" и "Назад"
    markup_reply = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    item_other = types.KeyboardButton("Другое")
    item_back = types.KeyboardButton("Назад")
    markup_reply.add(item_other, item_back)
    bot.send_message(chat_id, "Какой у вас тип фигуры?", reply_markup=markup_reply, reply_to_message_id=None)
    bot.send_message(chat_id, "Выберите один из вариантов:", reply_markup=markup)

    user_states[chat_id]["history"].append({"state": STATE_BODY_TYPE, "data": {}})

def set_age_group_options(chat_id: int):
    """Предлагает пользователю выбрать возрастную группу(InlineKeyboard)."""
    markup = types.InlineKeyboardMarkup()
    age_groups = ["18-25", "26-35", "36-45", "46+"]
    for age_group in age_groups:
        item = types.InlineKeyboardButton(age_group, callback_data=f"age_group:{age_group}")
        markup.add(item)
    back_button = types.InlineKeyboardButton("Назад", callback_data="age_group:back")
    markup.add(back_button)

    # ReplyKeyboard для "Другое" и "Назад"
    markup_reply = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    item_other = types.KeyboardButton("Другое")
    item_back = types.KeyboardButton("Назад")
    markup_reply.add(item_other, item_back)

    bot.send_message(chat_id, "К какой возрастной группе вы относитесь?", reply_markup=markup_reply, reply_to_message_id=None)
    bot.send_message(chat_id, "Выберите один из вариантов:", reply_markup=markup)
    user_states[chat_id]["history"].append({"state": STATE_AGE_GROUP, "data": {}})

# 10. Проверка состояния пользователя
def check_occasion_state(message: types.Message) -> bool:
    """Проверяет, находится ли пользователь в состоянии выбора ситуации."""
    chat_id = message.chat.id
    if not user_states.get(chat_id) or not user_states[chat_id].get("history"):
        return False
    return user_states[chat_id]["history"][-1]["state"] == STATE_OCCASION

# 11. Обработчики сообщений и callback-запросов
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
    set_style_preferences_options(chat_id)
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
        set_style_preferences_options(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("style"))
def handle_style_preferences_inline(call: types.CallbackQuery):
    """Обработчик выбора категории одежды (InlineKeyboard)."""
    chat_id = call.message.chat.id
    category = call.data.split(":")[1]
    if call.data == "style:back":
      handle_back(chat_id)
      return
    user_states[chat_id]["data"]["category"] = category
    set_body_type_options(chat_id)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_STYLE_PREFERENCES)
def handle_style_preferences(message: types.Message):
    """Обработчик ввода с клавиатуры (Другое или Назад)."""
    chat_id = message.chat.id
    style_text = message.text
    if style_text == "Другое":
        bot.send_message(chat_id, "Пожалуйста, введите свой вариант стиля:",
                         reply_markup=types.ForceReply(selective=True))
    elif style_text == "Назад":
        handle_back(chat_id)
    else:
        user_states[chat_id]["data"]["style_preferences"] = [style_text]
        set_budget_options(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("age_group"))
def handle_age_group_inline(call: types.CallbackQuery):
    """Обработчик выбора возрастной группы (InlineKeyboard)."""
    chat_id = call.message.chat.id
    age_group = call.data.split(":")[1]
    if age_group == "back":
        handle_back(chat_id)
        return
    user_states[chat_id]["data"]["age_group"] = age_group
    set_style_preferences_options(chat_id)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_AGE_GROUP)
def handle_age_group(message: types.Message):
    """Обработчик ввода с клавиатуры (Другое или Назад)."""
    chat_id = message.chat.id
    age_group_text = message.text
    if age_group_text == "Другое":
        bot.send_message(chat_id, "Пожалуйста, введите свой вариант возрастной группы:",
                         reply_markup=types.ForceReply(selective=True))
    elif age_group_text == "Назад":
        handle_back(chat_id)
    else:
        user_states[chat_id]["data"]["age_group"] = age_group_text
        set_style_preferences_options(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("body_type"))
def handle_body_type_inline(call: types.CallbackQuery):
    """Обработчик выбора типа фигуры (InlineKeyboard)."""
    chat_id = call.message.chat.id
    body_type = call.data.split(":")[1]
    if body_type == "back":
        handle_back(chat_id)
        return
    user_states[chat_id]["data"]["body_type"] = body_type
    set_age_group_options(chat_id)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_BODY_TYPE)
def handle_body_type(message: types.Message):
    """Обработчик ввода с клавиатуры (Другое или Назад)."""
    chat_id = message.chat.id
    body_type_text = message.text
    if body_type_text == "Другое":
        bot.send_message(chat_id, "Пожалуйста, введите свой вариант типа фигуры:",
                         reply_markup=types.ForceReply(selective=True))
    elif body_type_text == "Назад":
        handle_back(chat_id)
    else:
        user_states[chat_id]["data"]["body_type"] = body_type_text
        set_age_group_options(chat_id)

@bot.message_handler(func=lambda message: message.text and user_states.get(message.chat.id) and user_states[message.chat.id]["history"][-1]["state"] == STATE_BUDGET)
async def handle_budget(message: types.Message):
    chat_id = message.chat.id
    budget = message.text
    try:
        budget = int(budget)
        user_states[chat_id]["data"]["budget"] = budget

        # Получаем параметры для API
        occasion = user_states[chat_id]["data"].get("occasion")
        category = user_states[chat_id]["data"].get("category")
        style_preferences = user_states[chat_id]["data"].get("style_preferences", [])
        body_type = user_states[chat_id]["data"].get("body_type")
        age_group = user_states[chat_id]["data"].get("age_group")

        # Запрашиваем образы с API
        clothing_items = await get_clothing_items_from_api(occasion, category, style_preferences, budget, body_type, age_group)

        # Кэшируем полученные образы
        cache_clothing_items(clothing_items)

        # Генерируем описание образа
        outfit_description = generate_outfit_description(clothing_items, occasion, category, style_preferences, body_type, age_group)

        # Форматируем и отправляем результат
        outfit_result = format_outfit_result(clothing_items, outfit_description)
        send_outfit_result(chat_id, outfit_result)


    except ValueError:
        bot.send_message(chat_id, "Пожалуйста, введите бюджет числом.")

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
        elif previous_state == STATE_STYLE_PREFERENCES:
            set_style_preferences_options(chat_id)
        elif previous_state == STATE_BUDGET:
            set_budget_options(chat_id)
        elif previous_state == STATE_BODY_TYPE:
            set_body_type_options(chat_id)
        elif previous_state == STATE_AGE_GROUP:
            set_age_group_options(chat_id)
        else:
            bot.send_message(chat_id, "Неизвестное предыдущее состояние.")
    else:
        bot.send_message(chat_id, "Вы в самом начале диалога.")

# 12. Запуск бота
if __name__ == "__main__":
    logging.info("Starting Telegram bot...")
    asyncio.run(bot.polling(none_stop=True))