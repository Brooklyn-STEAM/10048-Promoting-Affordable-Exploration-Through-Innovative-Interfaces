from flask import Flask, render_template, request, redirect, flash, abort, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from flask_socketio import SocketIO, join_room, leave_room, emit
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
socketio = SocketIO(app, cors_allowed_origins="*")

# Track users per room
room_users = {}  # { room: set(usernames) }

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

login_manager = LoginManager(app)
login_manager.login_view = "/login"


class User(UserMixin):
    def __init__(self, result):
        self.name            = result["Username"]
        self.email           = result["Email"]
        self.address         = result["Address"]
        self.id              = result["ID"]
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
    {"name": "manhattan",     "color": "#1a3a5c", "accent": "#2e6da4"},
    {"name": "brooklyn",      "color": "#5c3a1a", "accent": "#a4642e"},
    {"name": "queens",        "color": "#1a5c3a", "accent": "#2ea464"},
    {"name": "bronx",         "color": "#2a2a2a", "accent": "#555555"},
    {"name": "staten island", "color": "#3a3328", "accent": "#7a6a50"},
]


ACHIEVEMENTS = [
    { "type": "first_post",   "image": "achievements/first_post.png",   "name": "First Gem",        "desc": "Posted your first location" },
    { "type": "post_50",      "image": "achievements/post_50.png",      "name": "Gem Appreciator",  "desc": "Posted 50 locations" },
    { "type": "post_100",     "image": "achievements/post_100.png",     "name": "Hidden Gem Master","desc": "Posted 100 locations" },
    { "type": "first_like",   "image": "achievements/first_like.png",   "name": "Show Some Love",   "desc": "Liked your first location" },
    { "type": "like_50",      "image": "achievements/like_50.png",      "name": "Super Fan",        "desc": "Liked 50 locations" },
    { "type": "like_100",     "image": "achievements/like_100.png",     "name": "Obsessed",         "desc": "Liked 100 locations" },
    { "type": "received_100", "image": "achievements/received_100.png", "name": "Trending",         "desc": "Received 100 likes on a location" },
    { "type": "all_boroughs", "image": "achievements/all_boroughs.png", "name": "True New Yorker",  "desc": "Posted in all 5 boroughs" },
]

def check_and_award(user_id, cursor):
    """Check which achievements the user has earned and award new ones."""
    cursor.execute("SELECT Type FROM `Achievement` WHERE UserID = %s", (user_id,))
    earned = {r["Type"] for r in cursor.fetchall()}

    new_achievements = []

    # Post counts
    cursor.execute("SELECT COUNT(*) as cnt FROM `Location` WHERE UserID = %s", (user_id,))
    post_count = cursor.fetchone()["cnt"]

    if post_count >= 1   and "first_post" not in earned: new_achievements.append("first_post")
    if post_count >= 50  and "post_50"    not in earned: new_achievements.append("post_50")
    if post_count >= 100 and "post_100"   not in earned: new_achievements.append("post_100")

    # Likes given
    cursor.execute("SELECT COUNT(*) as cnt FROM `Like` WHERE UserID = %s", (user_id,))
    like_count = cursor.fetchone()["cnt"]

    if like_count >= 1   and "first_like" not in earned: new_achievements.append("first_like")
    if like_count >= 50  and "like_50"    not in earned: new_achievements.append("like_50")
    if like_count >= 100 and "like_100"   not in earned: new_achievements.append("like_100")

    # Likes received on any single location
    cursor.execute("SELECT MAX(LikeCount) as max_likes FROM `Location` WHERE UserID = %s", (user_id,))
    row = cursor.fetchone()
    max_likes = row["max_likes"] or 0

    if max_likes >= 100 and "received_100" not in earned: new_achievements.append("received_100")

    # All 5 boroughs posted in
    cursor.execute("SELECT COUNT(DISTINCT Borough) as cnt FROM `Location` WHERE UserID = %s", (user_id,))
    borough_count = cursor.fetchone()["cnt"]

    if borough_count >= 5 and "all_boroughs" not in earned: new_achievements.append("all_boroughs")

    for ach_type in new_achievements:
        cursor.execute(
            "INSERT IGNORE INTO `Achievement` (UserID, Type) VALUES (%s, %s)",
            (user_id, ach_type)
        )

    return new_achievements


@app.route("/")
def index():
    return render_template("homepage.html.jinja")


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
        SELECT l.*, u.Username,
               COALESCE(l.LikeCount, 0) as LikeCount
        FROM `Location` l
        JOIN `User` u ON l.UserID = u.ID
        WHERE l.Borough = %s
        ORDER BY l.LikeCount DESC, l.DatePosted DESC
    """, (name,))
    locations = cursor.fetchall()

    loc_ids = [l["ID"] for l in locations]
    liked_ids = set()
    if loc_ids:
        fmt = ",".join(["%s"] * len(loc_ids))
        cursor.execute(
            f"SELECT LocationID FROM `Like` WHERE UserID = %s AND LocationID IN ({fmt})",
            (current_user.id, *loc_ids)
        )
        liked_ids = {row["LocationID"] for row in cursor.fetchall()}

    connection.close()

    featured = locations[:3]

    locations_json = json.dumps([{
        "ID":          l["ID"],
        "UserID":      l["UserID"],
        "Name":        l["Name"],
        "Borough":     l["Borough"],
        "Address":     l.get("Address") or "",
        "Description": l.get("Description") or "",
        "DatePosted":  (
            l["DatePosted"].strftime("%b %d, %Y")
            if isinstance(l["DatePosted"], datetime)
            else str(l["DatePosted"])
        ),
        "Image":       l.get("Image") or "",
        "LikeCount":   l.get("LikeCount") or 0,
        "Liked":       l["ID"] in liked_ids,
        "IsOwner":     l["UserID"] == current_user.id,
        "Hours":       (json.loads(l["Hours"]) if l.get("Hours") else []),
    } for l in locations])

    return render_template(
        "borough.html.jinja",
        borough=borough,
        locations=locations,
        featured=featured,
        liked_ids=liked_ids,
        locations_json=locations_json,
    )


@app.route("/borough/<path:n>/like/<int:loc_id>", methods=["POST"])
@login_required
def toggle_like(n, loc_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT ID FROM `Like` WHERE UserID = %s AND LocationID = %s",
        (current_user.id, loc_id)
    )
    existing = cursor.fetchone()

    if existing:
        cursor.execute(
            "DELETE FROM `Like` WHERE UserID = %s AND LocationID = %s",
            (current_user.id, loc_id)
        )
        cursor.execute(
            "UPDATE `Location` SET LikeCount = GREATEST(0, LikeCount - 1) WHERE ID = %s",
            (loc_id,)
        )
        liked = False
    else:
        cursor.execute(
            "INSERT INTO `Like` (UserID, LocationID) VALUES (%s, %s)",
            (current_user.id, loc_id)
        )
        cursor.execute(
            "UPDATE `Location` SET LikeCount = LikeCount + 1 WHERE ID = %s",
            (loc_id,)
        )
        liked = True

    cursor.execute("SELECT LikeCount FROM `Location` WHERE ID = %s", (loc_id,))
    row = cursor.fetchone()
    check_and_award(current_user.id, cursor)
    connection.close()

    return jsonify({"liked": liked, "count": row["LikeCount"] if row else 0})


@app.route("/borough/<path:n>/delete/<int:loc_id>", methods=["POST"])
@login_required
def delete_location(n, loc_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM `Location` WHERE ID = %s AND UserID = %s", (loc_id, current_user.id))
    loc = cursor.fetchone()

    if not loc:
        connection.close()
        return jsonify({"success": False, "error": "Not found or not allowed"})

    cursor.execute("DELETE FROM `Like` WHERE LocationID = %s", (loc_id,))
    cursor.execute("DELETE FROM `Location` WHERE ID = %s", (loc_id,))

    if loc.get("Image"):
        img_path = os.path.join(app.config["UPLOAD_FOLDER"], loc["Image"])
        if os.path.exists(img_path):
            os.remove(img_path)

    connection.close()
    return jsonify({"success": True})


@app.route("/borough/<path:n>/add", methods=["POST"])
@login_required
def add_location(n):
    borough_name = n.replace("-", " ")
    borough = next((b for b in BOROUGHS if b["name"] == borough_name), None)
    if not borough:
        abort(404)

    loc_name    = request.form.get("name", "").strip()
    address     = request.form.get("address", "").strip()
    description = request.form.get("description", "").strip()
    latitude    = request.form.get("latitude", "").strip() or None
    longitude   = request.form.get("longitude", "").strip() or None
    place_id    = request.form.get("place_id", "").strip() or None


    if not loc_name or not address:
        flash("Please fill in the name and address")
        return redirect(f"/borough/{n}")

    image = request.files.get("image")
    filename = None
    if image and image.filename and allowed_file(image.filename):
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        filename = str(uuid.uuid4()) + "_" + secure_filename(image.filename)
        image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    # Hours
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hours_list = []
    for d in days:
        open_t  = request.form.get(f"hours_{d}_open", "").strip()
        close_t = request.form.get(f"hours_{d}_close", "").strip()
        hours_str = f"{open_t} – {close_t}" if open_t and close_t else "Closed"
        hours_list.append({"name": d, "hours": hours_str})
    hours_json = json.dumps(hours_list)

    connection = connect_db()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO `Location` (UserID, Name, Address, Description, Borough, Image, Hours)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (current_user.id, loc_name, address, description, borough_name, filename, hours_json))

    check_and_award(current_user.id, cursor)
    connection.close()

    flash(f'"{loc_name}" added!')
    return redirect(f"/borough/{n}")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name             = request.form["name"]
        email            = request.form["email"]
        password         = request.form["password"]
        confirm_password = request.form["confirm_password"]
        address          = request.form["address"]

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
        email    = request.form.get("email")
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
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT Type, EarnedAt FROM `Achievement` WHERE UserID = %s", (current_user.id,))
    earned_rows = cursor.fetchall()
    earned_map = {r["Type"]: r["EarnedAt"] for r in earned_rows}

    achievements = []
    for a in ACHIEVEMENTS:
        achievements.append({
            **a,
            "earned":    a["type"] in earned_map,
            "earned_at": earned_map.get(a["type"])
        })

    connection.close()
    return render_template("profile.html.jinja", achievements=achievements)


@app.route("/profile/update-username", methods=["POST"])
@login_required
def update_username():
    username = request.form.get("username", "").strip()
    if not username:
        flash("Username cannot be empty")
        return redirect("/profile")
    connection = connect_db()
    cursor = connection.cursor()
    cursor.execute("UPDATE `User` SET `Username` = %s WHERE `ID` = %s", (username, current_user.id))
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
    cursor.execute("UPDATE `User` SET `Password` = %s WHERE `ID` = %s", (password, current_user.id))
    connection.close()
    flash("Password updated!")
    return redirect("/profile")


@app.route("/profile/update-picture", methods=["POST"])
@login_required
def update_picture():
    picture_url = request.form.get("picture_url", "").strip()
    connection = connect_db()
    cursor = connection.cursor()
    cursor.execute("UPDATE `User` SET `ProfilePicture` = %s WHERE `ID` = %s", (picture_url or None, current_user.id))
    connection.close()
    current_user.profile_picture = picture_url or None
    flash("Profile picture updated!")
    return redirect("/profile")


@app.route("/liked")
@login_required
def liked_page():
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT l.*, u.Username,
               COALESCE(l.LikeCount, 0) as LikeCount
        FROM `Location` l
        JOIN `Like` lk ON lk.LocationID = l.ID
        JOIN `User` u ON l.UserID = u.ID
        WHERE lk.UserID = %s
        ORDER BY lk.ID DESC
    """, (current_user.id,))
    locations = cursor.fetchall()
    connection.close()

    locations_json = json.dumps([{
        "ID":          l["ID"],
        "UserID":      l["UserID"],
        "Name":        l["Name"],
        "Borough":     l["Borough"],
        "Address":     l.get("Address") or "",
        "Description": l.get("Description") or "",
        "DatePosted":  (
            l["DatePosted"].strftime("%b %d, %Y")
            if isinstance(l["DatePosted"], datetime)
            else str(l["DatePosted"])
        ),
        "Image":       l.get("Image") or "",
        "LikeCount":   l.get("LikeCount") or 0,
        "Liked":       True,
        "IsOwner":     l["UserID"] == current_user.id,
        "Hours":       (json.loads(l["Hours"]) if l.get("Hours") else []),
    } for l in locations])

    return render_template("liked.html.jinja", locations=locations, locations_json=locations_json)


@app.route("/chat/<room>/history")
@login_required
def chat_history(room):
    connection = connect_db()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT Username, Message, SentAt
        FROM `ChatMessage`
        WHERE Room = %s
        ORDER BY SentAt ASC
        LIMIT 50
    """, (room,))
    messages = cursor.fetchall()
    connection.close()
    return jsonify([{
        "user": m["Username"],
        "text": m["Message"],
        "time": m["SentAt"].strftime("%I:%M %p") if m["SentAt"] else ""
    } for m in messages])


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")


# ── CHAT SOCKET EVENTS ──────────────────────────────────────
@socketio.on("join")
def on_join(data):
    room     = data.get("room")
    username = data.get("username", "Anonymous")
    join_room(room)
    if room not in room_users:
        room_users[room] = set()
    room_users[room].add(username)
    emit("message", {
        "user": "system",
        "text": f"{username} joined the chat",
        "time": ""
    }, to=room)
    emit("online_count", {"count": len(room_users[room]), "users": list(room_users[room])}, to=room)


@socketio.on("leave")
def on_leave(data):
    room     = data.get("room")
    username = data.get("username", "Anonymous")
    leave_room(room)
    if room in room_users:
        room_users[room].discard(username)
    emit("message", {
        "user": "system",
        "text": f"{username} left the chat",
        "time": ""
    }, to=room)
    emit("online_count", {"count": len(room_users.get(room, set())), "users": list(room_users.get(room, set()))}, to=room)


@socketio.on("send_message")
def on_message(data):
    room     = data.get("room")
    username = data.get("username", "Anonymous")
    text     = data.get("text", "").strip()
    if not text:
        return

    # Save to DB
    try:
        connection = connect_db()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT ID FROM `User` WHERE Username = %s", (username,)
        )
        user_row = cursor.fetchone()
        if user_row:
            cursor.execute(
                "INSERT INTO `ChatMessage` (Room, UserID, Username, Message) VALUES (%s, %s, %s, %s)",
                (room, user_row["ID"], username, text)
            )
        connection.close()
    except Exception:
        pass

    emit("message", {
        "user": username,
        "text": text,
        "time": "",
        "room": room
    }, to=room)


if __name__ == "__main__":
    socketio.run(app, debug=True)
