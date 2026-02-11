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



@app.route("/")
def index():
    return render_template("homepage.html.jinja")


@app.route("/browse")
def browse():
    return render_template("browse.html.jinja")


    
