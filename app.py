from flask import Flask, templating
from flask_htmlmin import HTMLMIN
import datetime

app = Flask(__name__)
app.config['MINIFY_PAGE'] = True
HTMLMIN(app)


def get_year():
    return datetime.datetime.now().year;


app.jinja_env.globals.update(get_year=get_year)


@app.route('/')
def hello_world(name=None):
    return templating.render_template("layout.html", name="Connor")


@app.route('/<value>')
def value_endpoint(value):
    return templating.render_template("layout.html", name=value)


if __name__ == '__main__':
    app.run()
