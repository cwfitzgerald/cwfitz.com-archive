from bleach_whitelist import bleach_whitelist
from flask import Flask, templating, abort
from htmlmin.minify import html_minify
from math import ceil
import bleach
import datetime
import markdown
import markdown.extensions
import markdown.inlinepatterns
import markdown.treeprocessors
import markdown.util
import os
import psycopg2.extensions
import thumbnails
import util

app = Flask(__name__)


@app.after_request
def minify_request(response):
    if response.content_type == u'text/html; charset=utf-8':
        response.set_data(
            html_minify(response.get_data(as_text=True))
        )

        return response
    return response


def get_year():
    return datetime.datetime.now().year


app.jinja_env.globals.update(get_year=get_year)
app.jinja_env.globals.update(get_thumbnail_url=thumbnails.get_thumbnail_url)
app.jinja_env.globals.update(DEVELOPMENT=os.getenv('FLASK_DEBUG', '0') == '1')


@app.errorhandler(403)
def handle_403(e):
    return templating.render_template("errors/403.html")


@app.errorhandler(404)
def handle_404(e):
    return templating.render_template("errors/404.html")


@app.errorhandler(500)
def handle_500(e):
    return templating.render_template("errors/500.html")


@app.errorhandler(psycopg2.DatabaseError)
def handle_db_err(e):
    util.connection.rollback()
    return handle_500(e)


class SetListStyleExt(markdown.extensions.Extension):
    def extendMarkdown(self, md: "markdown.Markdown", md_globals):
        md.treeprocessors.add("CustomStyle", SetListStyle(md), "_end")


class SetListStyle(markdown.treeprocessors.Treeprocessor):
    def run(self, root: "markdown.util.etree.Element"):
        for node in root:  # type: markdown.util.etree.Element
            if node.tag in ["ol", "ul"]:
                node.set('class', 'text-left pl-4')
                node.set('style', 'display: inline-block;')
            if node.tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                node.set('class', "font-weight-bold")
                node.tag = "h5"
            self.run(node)


def render_markdown(string):
    rendered = markdown.markdown(string,
                                 output_format='html5',
                                 lazy_ol=False,
                                 extensions=[SetListStyleExt()])
    attrib = bleach_whitelist.markdown_attrs
    attrib.update({'ol': ['style', 'class', 'start']})
    attrib.update({'ul': ['style', 'class']})
    attrib.update({'*': ['style', 'class']})
    styles = ['display']
    print(rendered)
    safe = bleach.clean(rendered,
                        tags=bleach_whitelist.markdown_tags,
                        attributes=bleach_whitelist.markdown_attrs,
                        styles=styles)
    return safe


@app.route('/')
def homepage():
    # thumbnail, title, description, youtube_url, vimeo_url, download_url

    with util.connection:
        with util.connection.cursor() as cursor:  # type: psycopg2.extensions.cursor
            cursor.execute("SELECT thumbnail_url, title, plaintext_short_description, youtube_url, "
                           "vimeo_url, static_download, webpage_url "
                           "FROM videos "
                           "ORDER BY release_date DESC "
                           "LIMIT 1")

            video_list = cursor.fetchall()

    util.connection.commit()

    return templating.render_template("homepage.html",
                                      video_list=video_list)


def render_video_paginated_list(page=1, number=10):
    if page <= 0:
        abort(404)

    with util.connection:
        with util.connection.cursor() as cursor:  # type: psycopg2.extensions.cursor
            cursor.execute("SELECT COUNT(*) FROM videos")
            number_of_videos = cursor.fetchone()[0]

            if (page - 1) * number + 1 > number_of_videos:
                abort(404)

            cursor.execute("SELECT thumbnail_url, title, plaintext_short_description, "
                           "youtube_url, vimeo_url, static_download, webpage_url "
                           "FROM videos "
                           "ORDER BY release_date DESC, title ASC "
                           "LIMIT %s "
                           "OFFSET %s",
                           (number, (page - 1) * number))

            videos = cursor.fetchall()

    return templating.render_template("videos.html",
                                      video_list=videos,
                                      video_count=number_of_videos,
                                      page_num=page,
                                      page_count=int(ceil(number_of_videos / number)),
                                      videos_per_page=number)


@app.route('/videos/<int:page>', strict_slashes=False)
@app.route('/videos', strict_slashes=False)
def video_list(page=1):
    return render_video_paginated_list(page)


@app.route('/videos/<string:page_name>')
def video_info(page_name):
    with util.connection:
        with util.connection.cursor() as cursor:  # type: psycopg2.extensions.cursor
            cursor.execute("SELECT id, title, release_date, description, description_rendered, youtube_url, "
                           "vimeo_url, static_download, thumbnail_url "
                           "FROM videos "
                           "WHERE webpage_url = %s",
                           (page_name,)
                           )

            if cursor.rowcount == 0:
                abort(404)

            id, title, release_date, description, description_rendered, \
            youtube_url, vimeo_url, static_download, thumbnail_url = cursor.fetchone()

            if description_rendered is None:
                description_rendered = render_markdown(description)

                cursor.execute("UPDATE videos "
                               "SET description_rendered = %s "
                               "WHERE id = %s",
                               (description_rendered, id))

    return templating.render_template("single_video.html",
                                      title=title,
                                      release_date=release_date,
                                      description=description_rendered,
                                      youtube_url=youtube_url,
                                      vimeo_url=vimeo_url,
                                      static_download=static_download,
                                      thumbnail_url=thumbnail_url)


if __name__ == '__main__':
    app.run(host='0.0.0.0')
