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
    {"name": "staten-island", "color": "#3a3328", "accent": "#7a6a50"},
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
    # Normalize
    name = name.lower()

    # Redirect each borough to its own page
    if name == "manhattan":
        return redirect("/manhattan")
    if name == "brooklyn":
        return redirect("/brooklyn")
    if name == "queens":
        return redirect("/queens")
    if name == "bronx":
        return redirect("/bronx")
    if name == "staten-island":
        return redirect("/staten-island")

    return "Borough not found", 404



@app.route("/staten-island")
def staten_is():
    return render_template("staten_is.html.jinja")
    
@app.route('/sign_up', methods=["POST" , "GET"])
def register():
    if request.method == "POST" :
        name = request.form["name"]

        email = request.form["email"]
        address = request.form["address"]

        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password!= confirm_password:
            flash("Passwords do not match")
        elif len(password) < 8:
            flash("Password is too short")
        else:
            connection = connect_db()

            cursor = connection.cursor()

            try:
                cursor.execute("""
                INSERT INTO `User` (`Name`, `Password`, `Email`, `Address`)
                VALUES(%s, %s, %s, %s)
                """, (name ,password, email, address )) 
                connection.close()   
            except pymysql.err.IntegrityError:
                flash("User with that email already exists.")
                connection.close()
            else:
                return redirect('/login')

    return render_template("sign_up.html.jinja")

@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        connection = connect_db()

        cursor = connection.cursor()

        cursor.execute("SELECT * FROM `User` WHERE `Email` = %s " , (email) )
        result = cursor.fetchone()
        connection.close()


        if result is None:
            flash("No user found.")
        elif password != result["Password"]:
            flash("Incorrect password")
        else:
            login_user(User(result))

            return redirect('/browse')
        


    return render_template("login.html.jinja")

@app.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect("/login")
if __name__ == "__main__":
    app.run(debug=True)

@app.route("/")
def index():
    return render_template("homepage.html.jinja")