from bleach_whitelist import bleach_whitelist
from datetime import datetime
from flask import Flask, templating, abort, request, jsonify, send_from_directory
from htmlmin.minify import html_minify
from math import ceil
import bleach
import datetime
import json
import markdown
import markdown.extensions
import markdown.extensions.tables
import markdown.inlinepatterns
import markdown.treeprocessors
import markdown.util
import os
import psycopg2.extensions
import secrets
import thumbnails
import util
import werkzeug.datastructures
import werkzeug.utils

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 * 1024

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
app.jinja_env.globals.update(DEVELOPMENT=util.development_mode())


# noinspection PyUnusedLocal
@app.errorhandler(403)
def handle_403(e):
    return templating.render_template("errors/403.html")


# noinspection PyUnusedLocal
@app.errorhandler(404)
def handle_404(e):
    return templating.render_template("errors/404.html")


# noinspection PyUnusedLocal
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
            if node.tag in ['table']:
                node.set('class', 'text-center table table-sm w-auto')
                node.set('style', 'display: inline-block;')
            if node.tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                node.set('class', "font-weight-bold")
                node.tag = "h5"
            self.run(node)


def render_markdown(string):
    rendered = markdown.markdown(string,
                                 output_format='html5',
                                 lazy_ol=False,
                                 extensions=[SetListStyleExt(), markdown.extensions.tables.TableExtension()])
    attrib = bleach_whitelist.markdown_attrs
    attrib.update({'ol': ['style', 'class', 'start']})
    attrib.update({'ul': ['style', 'class']})
    attrib.update({'*': ['style', 'class']})
    styles = ['display']

    tags = bleach_whitelist.markdown_tags

    tags.append('table')
    tags.append('thead')
    tags.append('tbody')
    tags.append('th')
    tags.append('tr')
    tags.append('td')

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
                           "vimeo_url, static_download, webpage_url, release_date "
                           "FROM videos "
                           "ORDER BY release_date DESC "
                           "LIMIT 1")

            list_of_videos = cursor.fetchall()

    util.connection.commit()

    return templating.render_template("homepage.html",
                                      video_list=list_of_videos)


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
                           "youtube_url, vimeo_url, static_download, webpage_url, release_date "
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

            ident, title, release_date, description, description_rendered, youtube_url,\
                vimeo_url, static_download, thumbnail_url = cursor.fetchone()

            if description_rendered is None:
                description_rendered = render_markdown(description)

                cursor.execute("UPDATE videos "
                               "SET description_rendered = %s "
                               "WHERE id = %s",
                               (description_rendered, ident))

    return templating.render_template("single_video.html",
                                      title=title,
                                      release_date=release_date,
                                      description=description_rendered,
                                      youtube_url=youtube_url,
                                      vimeo_url=vimeo_url,
                                      static_download=static_download,
                                      thumbnail=thumbnail_url)


@app.route("/s/<path:url>")
def ret_hosted_file(url):
    return send_from_directory("s/", url)


@app.route("/api/fdel/<path:url>", methods=['POST'])
def delete_file(url):
    form_data = request.form

    filename = os.path.abspath(os.path.join("s/", url))

    if 'pin' not in form_data or form_data['pin'] != os.getenv('CWF_UPLOAD_PIN'):
        return app.response_class(
            response=json.dumps({"error":"invalid pin"}),
            status=403,
            mimetype='application/json'
        )

    storage = os.path.abspath("s")
    file = os.path.abspath(filename)
    common = os.path.commonpath([storage, file])

    if common != storage:
        return app.response_class(
            response=json.dumps({"error" : "invalid path"}),
            status=403,
            mimetype='application/json'
        )

    if os.path.exists(filename):
        os.remove(filename)

    return app.response_class(
            response='',
            status=204
        )


@app.route("/api/fhost", methods=['POST'])
def file_host():
    if 'file' not in request.files:
        return app.response_class(
            response=json.dumps(error="File 'file' not found"),
            status=400,
            mimetype='application/json'
        )

    file = request.files['file']  # type: werkzeug.datastructures.FileStorage

    if file.filename == '':
        return app.response_class(
            response=json.dumps(error="Empty Filename"),
            status=400,
            mimetype='application/json'
        )

    form_data = request.form

    preserve_filename = 'preserve_filename' in form_data

    if 'pin' not in form_data or form_data['pin'] != os.getenv('CWF_UPLOAD_PIN'):
        return app.response_class(
            response=json.dumps({"error":"invalid pin"}),
            status=403,
            mimetype='application/json'
        )

    if preserve_filename:
        prefix = datetime.datetime.now().strftime('%y%j-%H%M%S-')
        filename = werkzeug.utils.secure_filename(file.filename)
        filename = prefix + filename
    else:
        ext = os.path.splitext(file.filename)[-1]

        filename = secrets.token_urlsafe(4) + ext
        while os.path.exists(filename):
            filename = secrets.token_urlsafe(4) + ext

    filepath = os.path.join("s/", filename)

    if not os.path.exists("s/"):
        os.mkdir("s/")

    file.save(filepath)

    return jsonify(url="https://cwfitz.com/s/{}".format(filename),
                   deleter="https://cwfitz.com/api/fdel/{}".format(filename))


if __name__ == '__main__':
    app.run(host='0.0.0.0')
