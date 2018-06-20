from flask import Flask, templating, abort
from flask_htmlmin import HTMLMIN
import datetime
from math import ceil
import psycopg2.extensions
import util


app = Flask(__name__)
app.config['MINIFY_PAGE'] = True
HTMLMIN(app)


def get_year():
    return datetime.datetime.now().year


app.jinja_env.globals.update(get_year=get_year)


@app.errorhandler(403)
def handle_403(e):
    return templating.render_template("errors/403.html")


@app.errorhandler(404)
def handle_404(e):
    return templating.render_template("errors/404.html")


@app.errorhandler(500)
def handle_500(e):
    return templating.render_template("errors/500.html")


@app.route('/')
def hello_world(name=None):
    # thumbnail, title, description, youtube_url, vimeo_url, download_url

    cursor = util.connection.cursor()  # type: psycopg2.extensions.cursor
    cursor.execute("SELECT thumbnail_url, title, plaintext_short_description, youtube_url, vimeo_url, static_download "
                   "FROM videos "
                   "ORDER BY release_date DESC "
                   "LIMIT 1")

    video_list = cursor.fetchall()

    return templating.render_template("homepage.html", video_list=video_list)


def render_video_paginated_list(page=1, number=2):
    # thumbnail, title, description, youtube_url, vimeo_url, download_url

    cursor = util.connection.cursor()  # type: psycopg2.extensions.cursor
    cursor.execute("SELECT COUNT(*) FROM videos")
    number_of_videos = cursor.fetchone()[0]

    if ((page - 1) * number + 1 > number_of_videos):
        abort(404)

    cursor.execute("SELECT thumbnail_url, title, plaintext_short_description, youtube_url, vimeo_url, static_download "
                   "FROM videos "
                   "ORDER BY release_date DESC "
                   "LIMIT %s "
                   "OFFSET %s",
                   (number, (page - 1) * number))

    video_list = cursor.fetchall()

    return templating.render_template("videos.html", video_list=video_list, video_count=number_of_videos, page_num=page, page_count=int(ceil(number_of_videos / number)), videos_per_page=number)


@app.route('/videos/<int:page>', strict_slashes=False)
@app.route('/videos', strict_slashes=False)
def video_list(page=1):
    return render_video_paginated_list(page)


@app.route('/<value>')
def value_endpoint(value):
    return templating.render_template("layout.html", name=value)


if __name__ == '__main__':
    app.run(host='0.0.0.0')

