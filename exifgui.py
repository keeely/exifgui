#!/usr/bin/env python3

from PySide2.QtWebEngineWidgets import *
from PySide2.QtWidgets import *
from PySide2.QtCore import *
from pathlib import Path
from io import BytesIO
import base64
import sys
import os
from PIL import Image
from subprocess import Popen, PIPE
import json
from html import escape
import re
from datetime import datetime
import urllib


g_globals = {}
g_globals["current_path"] = Path.home()


def valid_image_or_none(path):
    try:
        return Image.open(path)
    except IOError:
        return None


def image_to_html(im, name):
    stream = BytesIO()
    try:
        im.save(stream, format='JPEG')
        im_type = "jpeg"
    except OSError:
        im.save(stream, format='PNG')
        im_type = "png"

    data = stream.getvalue()
    enc = base64.b64encode(data).decode("utf-8")
    return '<img src="data:image/%s;base64,%s" alt="%s"/>' % (im_type, enc, name)


def get_exif_data(path):
    p = Popen(["exiftool", "-json", path], stdout=PIPE)
    out, err = p.communicate("")
    meta = json.loads(out)
    return meta[0]


class ExifDateTime(object):
    def __init__(self, id, exif_value):
        self.rex = re.compile(r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})")
        self.id = id
        m = self.rex.match(exif_value)
        if m:
            self.value = datetime(*[int(_) for _ in m.groups()])
        else:
            self.value = None
        self.exif = exif_value

    @staticmethod
    def from_update(values):
        """Construct from the 'update' button."""
        try:
            text = values[1] + " " + values[2]
            date_time = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            new_object = ExifDateTime(values[0], date_time.strftime("%Y:%m:%d %H:%M:%S"))
            return new_object
        except ValueError:
            return None


    def render_date(self, date_time):
        out = ""
        pic_date = date_time.strftime("%Y-%m-%d")
        pic_time = date_time.strftime("%H:%M:%S")
        out += f'<input type="date" id="{self.id}_0" value="{pic_date}"/>'
        out += '&nbsp;' * 3
        out += f'<input type="text" id="{self.id}_1" value="{pic_time}"/>'
        return out

    def render(self):
        out = ""
        if self.value is None:
            if self.exif == '':
                out += f"--- MISSING VALUE ---&nbsp;&nbsp;"
            else:
                read_value = escape(self.exif)
                out += f"!!! CORRUPT VALUE: &quot;{read_value}&quot; !!!&nbsp;&nbsp;"
            out += self.render_date(datetime.now())
        else:
            out += self.render_date(self.value)
        return out

    def exiftool(self):
        return ['exiftool', f"-AllDates={self.exif}"]


EXIF_HANDLERS = {"DateTimeOriginal": ExifDateTime}


g_script = """
<head>
<script>
function onUpdate(key) {
  let items = [key];
  let count = 0;
  while (true) {
    let query = key + "_" + count.toString();
    let node = document.getElementById(query);
    if (node === null) {
        break;
    }
    let value = node.value;
    items.push(value);
    count += 1;
  }
  let url = "update:" + encodeURI(JSON.stringify(items));
  window.location.replace(url);
}
</script>
</head>
"""


def picture_page():
    path = g_globals["current_path"]
    html = '<html>'
    html += g_script
    html += "<body>\n"
    html += f'<b>{path}</b><br>'

    meta = get_exif_data(path)
    required = list(EXIF_HANDLERS.keys())
    required.sort()

    html += '<table>\n'
    for key in required:
        handler_class = EXIF_HANDLERS[key]
        obj = handler_class(key, meta.get(key, ''))
        rendered = obj.render()
        button = f'<button onclick="onUpdate(\'{key}\')">Update</button>'
        html += f'<tr><td>{key}</td><td id="{key}">{rendered}</td><td>{button}</td></tr>\n'

    html += '</table>'

    im = valid_image_or_none(path)
    if not im:
        html += '<a href="up:">Back up</a><br>'
        html += f'{path}<br>'
        html += '========== UNRECOGNISED IMAGE =========='
        return html
    # Create a page with all the details on.
    im.thumbnail((800, 800))
    html += '<a href="up:">%s</a>' % image_to_html(im, path.name)
    html += "</body></html>"

    return html


def directory_page():
    html = ""
    if str(g_globals["current_path"]) != "/":
        html += '<a href="up:">Back up</a><br>'
    directories = []
    pictures = []
    for path in g_globals["current_path"].iterdir():
        if path.is_file():
            im = valid_image_or_none(path)
            if im:
                im.thumbnail((200, 200))
                txt = image_to_html(im, path.name)
                entry = '<td><a style="border-width: 30px;" href="load:%s" ><div style="border-width: 30px;">%s</div></a></td>' % (str(path), txt)
                meta = get_exif_data(path)
                date_time = "##############"
                if "DateTimeOriginal" in meta:
                    date_time = meta['DateTimeOriginal']

                pictures.append('<tr>' + entry + f"<td>{date_time}</td></tr>\n")
        elif path.is_dir():
            entry = '<a href="dir:%s">%s</a>' % (str(path), path.name)
            directories.append(entry)

    html += "\n<br>\n".join(directories)
    html += "<br><br>\n"
    html += "<table>\n"

    for entry in pictures:
        html += entry

    html += "</table>\n"

    return html


def execute_with_html_output(cmnd):
    p = Popen(cmnd, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate("")
    ok = p.returncode == 0

    out_html = escape(out.decode("utf-8"))
    err_html = escape(err.decode("utf-8"))
    html = f'<html><h1>STDOUT</h1><pre>{out_html}</pre><h1>STDERR</h1><pre>{err_html}</pre></html>'
    return html, ok


class MyQWebEnginePage(QWebEnginePage):
    def __init__(self, parent=None):
        super(MyQWebEnginePage,self).__init__(parent)

    def acceptNavigationRequest(self, url, type, _isMainFrame):

        if url.scheme() == "data":
            return True

        if url.scheme() == "load":
            g_globals["current_path"] = Path(url.path())
            print(g_globals["current_path"])
            self.setHtml(picture_page())
            return False

        if url.scheme() == "dir":
            g_globals["current_path"] = Path(url.path())
            self.setHtml(directory_page())
            return False

        if url.scheme() == "up":
            g_globals["current_path"] = g_globals["current_path"].parent
            self.setHtml(directory_page())
            return False

        if url.scheme() == "update":
            path = urllib.parse.unquote(url.path())
            path = json.loads(path)
            key = path[0]
            values = path[1:]
            if key not in EXIF_HANDLERS:
                self.setHtml("<h1>ERROR, fix this!!!!</h1>")
                return False
            handler_class = EXIF_HANDLERS[key]
            obj = handler_class.from_update(path)
            if obj is None:
                self.setHtml(f"<h1>ERROR in parameters {path} </h1>")
            cmnd = obj.exiftool() + [str(g_globals["current_path"])]
            html, ok = execute_with_html_output(cmnd)
            if ok:
                self.setHtml(picture_page())
            else:
                self.setHtml(html)
            return False

        return False


def navigate_to_current_path():
    path = g_globals["current_path"]
    browser = g_globals["browser"]
    if path.is_dir():
        browser.setHtml(directory_page())
    elif path.is_file():
        browser.setHtml(picture_page())
    else:
        return


def get_path_from_index(index):
    out = []
    while index.isValid():
        data = index.data()
        out.insert(0, data)
        index = index.parent()
    return Path("/" + "/".join(out[1:]))


def tree_view_clicked(index):
    path = get_path_from_index(index)
    g_globals["current_path"] = path
    navigate_to_current_path()


if __name__ == "__main__":

    app = QApplication(sys.argv)
    page = MyQWebEnginePage()
    browser = QWebEngineView()
    browser.setPage(page)
    browser.setHtml(directory_page())
    browser.show()
    g_globals["browser"] = browser

    fs_model = QFileSystemModel()
    fs_model.setRootPath(str(g_globals["current_path"]))

    tree_view = QTreeView()
    tree_view.setModel(fs_model)
    tree_view.setRootIndex(fs_model.index(str(g_globals["current_path"])))
    tree_view.setColumnHidden(1, True)
    tree_view.setColumnHidden(2, True)
    tree_view.setColumnHidden(3, True)
    tree_view.setHeaderHidden(True)
    tree_view.clicked.connect(tree_view_clicked)

    splitter_horiz = QSplitter()
    splitter_horiz.addWidget(tree_view)
    splitter_horiz.addWidget(browser)

    splitter_horiz.setSizes((400, 1200))
    splitter_horiz.resize(1000, 768)

    splitter_horiz.show()
    sys.exit(app.exec_())
