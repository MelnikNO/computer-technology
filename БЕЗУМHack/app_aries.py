from flask import Flask, render_template
import random
import aries  # Import the aries module

app = Flask(__name__)

@app.route('/aries')
def aries_horoscope():
    prediction = random.choice(aries.predictions)  # Get a random prediction
    return render_template('html_aries.html', prediction=prediction)  # Render the template

if __name__ == '__main__':
    app.run(debug=True)