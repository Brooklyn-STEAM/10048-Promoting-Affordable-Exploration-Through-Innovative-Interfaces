from flask import Flask,render_template,request,redirect,url_for, flash,abort
from flask_login import LoginManager, login_user, login_required, UserMixin, logout_user, current_user

import pymysql

from dynaconf import Dynaconf

app = Flask(__name__)



config = Dynaconf(settings_file=["settings.toml"])

app.secret_key = config.secret_key

login_manager = LoginManager( app )

login_manager.login_view = '/login'

class User: 
    is_authenticated = True
    is_active = True
    is_anoonymous = False

    def __init__(self, result):
        self.name = result['Username']
        self.email = result['Email']
        self.address = result['Address']
        self.id = result['ID']
    
    def get_id(self):
        return str(self.id)
    
@login_manager.user_loader
def load_user(user_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute(" SELECT * FROM `User` WHERE `ID` = %s ", ( user_id ))

    result = cursor.fetchone()

    connection.close()

    if result is None:
        return None
    
    return User(result)

@app.errorhandler(404)
def page_not_found(e):
        return render_template("404.html.jinja"), 404



def connect_db():
    conn = pymysql.connect(
        host="db.steamcenter.tech",
        user="djean2",
        password=config.password,
        database="hidden_gems",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor
    )
    
    return conn 

BOROUGHS = [
    {"name": "manhattan",     "color": "#1a3a5c", "accent": "#2e6da4"},
    {"name": "brooklyn",      "color": "#5c3a1a", "accent": "#a4642e"},
    {"name": "queens",        "color": "#1a5c3a", "accent": "#2ea464"},
    {"name": "bronx",         "color": "#2a2a2a", "accent": "#555555"},
    {"name": "staten island", "color": "#3a3328", "accent": "#7a6a50"},
]

@app.route("/browse", methods=["GET", "POST"])
def browse():
    selected_borough = request.form.get("borough", "manhattan")
    borough_obj = next((b for b in BOROUGHS if b["name"] == selected_borough), BOROUGHS[0])

    return render_template(
        "browse.html.jinja",
        boroughs=BOROUGHS,
        selected=borough_obj,
    )

@app.route("/borough/<name>")
def borough_page(name):
    name = name.replace("-", " ")
    borough = next((b for b in BOROUGHS if b["name"] == name), None)
    if not borough:
        return "Borough not found", 404
    return render_template("borough.html.jinja", borough=borough)

if __name__ == "__main__":
    app.run(debug=True)