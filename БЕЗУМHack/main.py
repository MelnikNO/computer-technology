from flask import Flask, render_template, request, redirect, url_for
import datetime
import random

# Импортируем модули с предсказаниями
import aries

app = Flask(__name__)

zodiac_signs = [
    ("Овен", "19 апреля - 13 мая", "aries"),
    ("Телец", "14 мая - 19 июня", "taurus"),
    ("Близнецы", "20 июня - 20 июля", "gemini"),
    ("Рак", "21 июля - 9 августа", "cancer"),
    ("Лев", "10 августа - 15 сентября", "leo"),
    ("Дева", "16 сентяря - 30 октября", "virgo"),
    ("Весы", "31 октября - 22 ноября", "libra"),
    ("Скорпион", "23 ноября - 29 ноября", "scorpio"),
    ("Змееносец", "30 ноября - 17 декабря", "ophiuchus"),
    ("Стрелец", "18 декабря - 18 января", "sagittarius"),
    ("Козерог", "19 января - 16 февраля", "capricorn"),
    ("Водолей", "17 февраля - 11 марта", "aquarius"),
    ("Рыбы", "12 марта - 18 апреля", "pisces"),
    ("Выберите знак зодиака", "", "index")  # Пустой элемент для подсказки
]

# Словарь с предсказаниями для каждого знака
predictions = {
    "aries": aries.predictions,
}

@app.route('/', methods=['GET', 'POST'])
def index():
    username = None
    selected_sign = None  # Теперь None, если не выбран
    selected_date = datetime.date.today().strftime("%d.%m.%Y")

    if request.method == 'POST':
        username = request.form.get('username')
        selected_sign = request.form.get('zodiac_sign')
        selected_date = request.form.get('selected_date')

        if selected_sign and selected_sign != "index":
            return redirect(url_for(selected_sign, selected_date=selected_date)) # Редирект на страницу знака
        else:
            return "Пожалуйста, выберите знак зодиака."
    today_date = datetime.date.today().strftime("%d.%m.%Y")

    return render_template('index.html',
                           zodiac_signs=zodiac_signs,
                           username=username,
                           selected_sign=selected_sign,
                           today_date=today_date,
                           )

@app.route('/aries')
def aries():
    prediction = random.choice(predictions["aries"])
    return render_template('html_aries.html', prediction=prediction)

if __name__ == '__main__':
    app.run(debug=True)