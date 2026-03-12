from flask import Flask, render_template, request, redirect, flash, abort
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
import pymysql
import json
from datetime import datetime
from dynaconf import Dynaconf
from werkzeug.utils import secure_filename
import os
import uuid

app = Flask(__name__)

config = Dynaconf(settings_file=["settings.toml"])
app.secret_key = config.secret_key

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

login_manager = LoginManager(app)
login_manager.login_view = "/login"


class User(UserMixin):

    def __init__(self, result):
        self.name = result["Username"]
        self.email = result["Email"]
        self.address = result["Address"]
        self.id = result["ID"]
        self.profile_picture = result.get("ProfilePicture")

    def get_id(self):
        return str(self.id)


def connect_db():
    return pymysql.connect(
        host="db.steamcenter.tech",
        user="djean2",
        password=config.password,
        database="hidden_gems",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor
    )


@login_manager.user_loader
def load_user(user_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM `User` WHERE `ID` = %s", (user_id,))
    result = cursor.fetchone()

    connection.close()

    if result is None:
        return None

    return User(result)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html.jinja"), 404


BOROUGHS = [
    {"name": "manhattan", "color": "#1a3a5c", "accent": "#2e6da4"},
    {"name": "brooklyn", "color": "#5c3a1a", "accent": "#a4642e"},
    {"name": "queens", "color": "#1a5c3a", "accent": "#2ea464"},
    {"name": "bronx", "color": "#2a2a2a", "accent": "#555555"},
    {"name": "staten island", "color": "#3a3328", "accent": "#7a6a50"},
]


@app.route("/browse", methods=["GET", "POST"])
@login_required
def browse():
    selected_borough = request.form.get("borough", "manhattan")
    borough_obj = next((b for b in BOROUGHS if b["name"] == selected_borough), BOROUGHS[0])
    return render_template("browse.html.jinja", boroughs=BOROUGHS, selected=borough_obj)


@app.route("/borough/<path:n>")
@login_required
def borough_page(n):

    name = n.replace("-", " ")
    borough = next((b for b in BOROUGHS if b["name"] == name), None)

    if not borough:
        abort(404)

    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT l.*, u.Username
        FROM `Location` l
        JOIN `User` u ON l.UserID = u.ID
        WHERE l.Borough = %s
        ORDER BY l.DatePosted DESC
    """, (name,))

    locations = cursor.fetchall()
    connection.close()

    locations_json = json.dumps([{
        "Name": l["Name"],
        "Borough": l["Borough"],
        "Description": l.get("Description", ""),
        "DatePosted": l["DatePosted"].strftime("%b %d, %Y") if isinstance(l["DatePosted"], datetime) else str(l["DatePosted"]),
    } for l in locations])

    return render_template(
        "borough.html.jinja",
        borough=borough,
        locations=locations,
        locations_json=locations_json
    )


@app.route("/borough/<borough>/add", methods=["POST"])
@login_required
def add_location(borough):

    name = request.form["name"]
    address = request.form["address"]
    description = request.form["description"]

    image = request.files.get("image")
    filename = None

    if image and allowed_file(image.filename):

        unique_name = str(uuid.uuid4())
        filename = unique_name + "_" + secure_filename(image.filename)

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image.save(filepath)

    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO Location
        (UserID, Name, Address, Description, Borough, Image)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        current_user.id,
        name,
        address,
        description,
        borough,
        filename
    ))

    connection.close()

    flash("Location added!")
    return redirect(f"/borough/{borough}")


@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        address = request.form["address"]

        if password != confirm_password:
            flash("Passwords do not match")
            return redirect("/signup")

        if len(password) < 8:
            flash("Password must be at least 8 characters")
            return redirect("/signup")

        connection = connect_db()
        cursor = connection.cursor()

        try:
            cursor.execute(
                "INSERT INTO `User` (Username, Password, Email, Address) VALUES (%s, %s, %s, %s)",
                (name, password, email, address)
            )

        except pymysql.err.IntegrityError:
            flash("An account with that email already exists")
            connection.close()
            return redirect("/signup")

        connection.close()

        flash("Account created! Please log in.")
        return redirect("/login")

    return render_template("signup.html.jinja")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            flash("Please enter both email and password")
            return redirect("/login")

        connection = connect_db()
        cursor = connection.cursor()

        cursor.execute("SELECT * FROM `User` WHERE `Email` = %s", (email,))
        result = cursor.fetchone()

        connection.close()

        if result is None:
            flash("No account found with that email")
            return redirect("/login")

        if password != result["Password"]:
            flash("Incorrect password")
            return redirect("/login")

        login_user(User(result))
        flash(f"Welcome back, {result['Username']}!")

        return redirect("/browse")

    return render_template("login.html.jinja")


@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html.jinja")


@app.route("/profile/update-username", methods=["POST"])
@login_required
def update_username():

    username = request.form.get("username", "").strip()

    if not username:
        flash("Username cannot be empty")
        return redirect("/profile")

    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE `User` SET `Username` = %s WHERE `ID` = %s",
        (username, current_user.id)
    )

    connection.close()

    current_user.name = username

    flash("Username updated!")
    return redirect("/profile")


@app.route("/profile/update-password", methods=["POST"])
@login_required
def update_password():

    password = request.form.get("password", "")

    if len(password) < 8:
        flash("Password must be at least 8 characters")
        return redirect("/profile")

    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE `User` SET `Password` = %s WHERE `ID` = %s",
        (password, current_user.id)
    )

    connection.close()

    flash("Password updated!")
    return redirect("/profile")


@app.route("/profile/update-picture", methods=["POST"])
@login_required
def update_picture():

    picture_url = request.form.get("picture_url", "").strip()

    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE `User` SET `ProfilePicture` = %s WHERE `ID` = %s",
        (picture_url or None, current_user.id)
    )

    connection.close()

    current_user.profile_picture = picture_url or None

    flash("Profile picture updated!")
    return redirect("/profile")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")


if __name__ == "__main__":
    app.run(debug=True)