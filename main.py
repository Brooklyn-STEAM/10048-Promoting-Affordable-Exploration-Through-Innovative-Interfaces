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



FRUITS = [
    {"name": "strawberry", "emoji": "🍓", "color": "#c0392b", "accent": "#e74c3c"},
    {"name": "lemon",      "emoji": "🍋", "color": "#d4ac0d", "accent": "#f1c40f"},
    {"name": "blueberry",  "emoji": "🫐", "color": "#1a237e", "accent": "#3949ab"},
    {"name": "raspberry",  "emoji": "🫐", "color": "#880e4f", "accent": "#ad1457"},
    {"name": "blackberry", "emoji": "🍇", "color": "#4a148c", "accent": "#6a1b9a"},
    {"name": "peach",      "emoji": "🍑", "color": "#bf360c", "accent": "#e64a19"},
]

SIZES = ["S", "M", "L"]
PRICES = {"S": "7.99", "M": "9.99", "L": "12.99"}

@app.route("/browse", methods=["GET", "POST"])
def browse():
    selected_fruit = request.form.get("fruit", "strawberry")
    selected_size  = request.form.get("size", "M")
    fruit_obj = next((f for f in FRUITS if f["name"] == selected_fruit), FRUITS[0])
    price = PRICES.get(selected_size, "9.99")

    return render_template(
        "browse.html.jinja",
        fruits=FRUITS,
        selected=fruit_obj,
        sizes=SIZES,
        selected_size=selected_size,
        price=price,
    )


@app.route("/brooklyn")
def brooklyn():
    return render_template("brooklyn.html.jinja")
    
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
