from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp
import math
import os
import psycopg2

from helpers import *

# Warning: Content might not be pythonic
# Warning: Content is not efficient. If you are naturally allergic to inefficient code, this 
#   may cause mild trauma
# Warning: You hear that?? It's the sound of bugs singing

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL(os.environ.get("DATABASE_URL") or "sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    purchases = db.execute("SELECT * FROM purchases WHERE userid = :id ORDER BY symbol", id = session["user_id"])
    sum = 0
    for purchase in purchases:
        result = lookup(purchase["symbol"])
        purchase["name"] = result["name"]
        purchase["price"] = usd(result["price"])
        purchase["sum"] = usd(result["price"] * purchase["shares"])
        sum += result["price"] * purchase["shares"]
    search = db.execute("SELECT * FROM users WHERE id = :id", id = session["user_id"])
    return render_template("index.html", 
        purchases = purchases, 
        balance = usd(search[0]["cash"]), 
        sum = usd(search[0]["cash"] + sum)
    )

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    else:
        if not request.form["symbol"] or not request.form["shares"]:
            return apology("Missing Symbol OR SHARES")
        if not isNum(request.form["shares"]):
            return apology("Shares is not a number")
        # Good morning life. This is defense against shady friend
        if int(request.form["shares"]) < 0:
            return apology("Why you do this to me")
        result = lookup(request.form["symbol"])
        if not result:
            return apology("Invalid Symbol")
        if float(request.form["shares"]) % 1 != 0:
            return apology("Invalid Stock Number")
        totalPrice = result["price"] * int(request.form["shares"])
        balance = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
        if totalPrice > balance[0]["cash"]:
            return apology("CAN'T AFFORD")
        purchase = db.execute("SELECT id, shares FROM purchases WHERE userid = :id AND symbol = :symbol", 
            id = session["user_id"], symbol = result["symbol"])
        if not purchase:
            db.execute("INSERT INTO purchases (userid, symbol, shares) VALUES (:id, :symbol, :shares)",
                id = session["user_id"], 
                symbol = result["symbol"], 
                shares = int(request.form["shares"])
            )
        else:
            db.execute("UPDATE purchases SET shares = :shares WHERE id = :id",
                shares = purchase[0]["shares"] + int(request.form["shares"]),
                id = purchase[0]["id"]
            )
        db.execute("INSERT INTO history (userid, symbol, shares, price) VALUES (:userid, :symbol, :shares, :price)",
            userid = session["user_id"],
            symbol = result["symbol"],
            shares = int(request.form["shares"]),
            price = totalPrice,
        )
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", 
            cash = balance[0]["cash"] - totalPrice, 
            id = session["user_id"]
        )
        return redirect(url_for("index"))
        

@app.route("/change", methods = ["GET", "POST"])
@login_required
def change():
    if request.method == "GET":
        return render_template("change.html")
    if request.form["passwordnew"] != request.form["passwordver"]:
        return apology("New password doesn't match with retyped version")
    user = db.execute("SELECT * FROM users WHERE id = :id", 
        id = session["user_id"]
    )
    
    if not user:
        return apology("User not found: Session ended")
    if not pwd_context.verify(request.form.get("password"), user[0]["hash"]):
        return apology("Invalid password input")
    if not db.execute("UPDATE users SET hash = :hash WHERE id = :id", 
        id = session["user_id"], hash = pwd_context.hash(request.form["passwordnew"])):
            return apology("Server error")
    return redirect(url_for("index"))

@app.route("/history")
@login_required
def history():
    # why can't everything be this elegant <3
    transactions = db.execute("SELECT * FROM history WHERE userid = :id ORDER BY time DESC", id = session["user_id"])
    for transaction in transactions:
        transaction["price"] = usd(transaction["price"])
    return render_template("history.html", transactions = transactions)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")
    else:
        if not request.form["symbol"]:
            return apology("Missing Symbol")
        result = lookup(request.form["symbol"])
        if not result:
            return apology("Invalid Symbol")
        return render_template("quoted.html", name = result["name"], price = result["price"], symbol = result["symbol"])
        
        
@app.route("/rankings")
@login_required
def rankings():
    # TBH 10 is just bc 20 will cause bad performance
    size = 10
    players = db.execute("SELECT * FROM users")
    hasPlayer = False
    for player in players:
        player["shares"] = db.execute("SELECT SUM(shares) AS sum FROM purchases WHERE userid = :id", 
            id = player["id"])[0]["sum"]
        sum = 0
        for stock in db.execute("SELECT * FROM purchases WHERE userid = :id", id = player["id"]):
            result = lookup(stock["symbol"])
            sum += result["price"] * stock["shares"]
        player["total"] = sum + player["cash"]
        player["cash"] = usd(player["cash"])
    # :D stackoverflow exist
    players = sorted(players, key = lambda k: k["total"], reverse=True)
    if len(players) > size:
        players = players[:size]
    for r in range(len(players)):
        player = players[r]
        player["ranking"] = r + 1
        player["total"] = usd(player["total"])
        if player["id"] == session["user_id"]:
            hasPlayer = True
            player["isPlayer"] = True
    # Ugly code, please scroll down
    if hasPlayer:
        return render_template("rankings.html", users = players);
    self = db.execute("SELECT * FROM users WHERE id = :id", id = session["user_id"])[0]
    self["ranking"] = db.execute("SELECT * FROM users GROUP BY cash").index(self) + 1
    self["shares"] = db.execute("SELECT SUM(shares) AS sum FROM purchases WHERE userid = :id", 
            id = self["id"])[0]["sum"]
    return render_template("rankings.html", 
        users = players, 
        ranking = self["ranking"], 
        name = self["username"],
        shares = self["shares"],
        cash = usd(self["cash"])
    )

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    else:
        if request.form["password"] != request.form["passwordver"]:
            return apology("Passwords doesn't match")
        if not db.execute("INSERT INTO users (username, hash) VALUES (:name, :hash)", name = request.form["username"], 
            hash = pwd_context.hash(request.form["password"])):
                return apology("Username already exist! SAD")
        return redirect(url_for("index"))
    

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":
        return render_template("sell.html")
    else:
        if not request.form["symbol"] or not request.form["shares"]:
            return apology("Missing Symbol or Shares")
        if not isNum(request.form["shares"]):
            return apology("Shares is not a valid number")
        # Good morning life. This is defense against shady friend
        if int(request.form["shares"]) < 0:
            return apology("HMMM shady")
        result = lookup(request.form["symbol"])
        if not result:
            return apology("Invalid Symbol")
        purchase = db.execute("SELECT * FROM purchases WHERE symbol = :symbol AND userid = :id", 
            symbol = result["symbol"],
            id = session["user_id"]
        )
        if not purchase or purchase[0]["shares"] < int(request.form["shares"]):
            return apology("Too many shares")
        if purchase[0]["shares"] > int(request.form["shares"]):
            db.execute("UPDATE purchases SET shares = :shares WHERE id = :id",
                shares = purchase[0]["shares"] - int(request.form["shares"]),
                id = purchase[0]["id"]
            )
        else:
            db.execute("DELETE FROM purchases WHERE id = :id", id = purchase[0]["id"])
        price = int(request.form["shares"]) * result["price"]
        db.execute("UPDATE users SET cash = :cash WHERE id = :id",
            id = purchase[0]["userid"],
            cash = db.execute("SELECT cash FROM users WHERE id = :id", id = purchase[0]["userid"])[0]["cash"] + price
        )
        db.execute("INSERT INTO history (userid, symbol, shares, price) VALUES (:id, :symbol, :shares, :price)",
            id = session["user_id"],
            symbol = result["symbol"],
            shares = -int(request.form["shares"]),
            price = price,
        )
        return redirect(url_for("index"))
        
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port = port)