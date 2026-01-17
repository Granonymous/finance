import os

from datetime import datetime
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev")

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    holdings = db.execute("SELECT symbol, SUM(CASE WHEN type = 'buy' THEN shares WHEN type = 'sell' THEN -shares END) AS shares FROM purchases WHERE user_id = ? GROUP BY symbol HAVING shares > 0", session["user_id"])
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])[0]

    stocks = []
    value = 0

    for holding in holdings:
        data = lookup(holding["symbol"])
        stock_value = data["price"] * holding["shares"]
        value += stock_value

        stocks.append({
            "symbol": holding["symbol"],
            "shares": holding["shares"],
            "price": data["price"],
            "total": stock_value
        })

    value += user["cash"]

    return render_template("index.html", stocks=stocks, value=value, cash=user["cash"])

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        if lookup(request.form.get("symbol")) is None:
            return apology("stock not found", 400)

        shares = request.form.get("shares")

        if not shares or not shares.isdigit():
            return apology("invalid number of shares", 400)

        if int(shares) <= 0:
            return apology("invalid number of shares", 400)

        symbol = lookup(request.form.get("symbol"))

        rows = db.execute(
            "SELECT * FROM users WHERE id = ?", session["user_id"])[0]


        cash = rows["cash"] - (symbol["price"] * int(request.form.get("shares")))

        if cash < 0:
            return apology("insufficient funds", 400)

        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])

        db.execute("INSERT INTO purchases (symbol, price, shares, time, user_id, type) VALUES(?, ?, ?, ?, ?, ?)", symbol["symbol"], symbol["price"], request.form.get("shares"), datetime.now(), session["user_id"], 'buy')

        return redirect("/")

    elif request.method == "GET":
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT * FROM purchases WHERE user_id = ?", session["user_id"])

    return render_template("history.html", transactions=transactions)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        symbol = request.form.get("symbol")

        if not symbol:
            return apology("must provide symbol", 400)

        quote = lookup(symbol)

        if quote is None:
            return apology("stock symbol does not exist", 400)

        return render_template("quoted.html", quote=quote)

    elif request.method == "GET":
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Forget any user_id
    session.clear()

    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("passwords must match", 400)

        # Add user and hash to database
        try:
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password")))
        except ValueError:
            return apology("username already taken", 400)

        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        session["user_id"] = rows[0]["id"]

        return render_template("login.html")

    elif request.method == "GET":
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    holdings = db.execute("SELECT symbol, SUM(CASE WHEN type = 'buy' THEN shares WHEN type = 'sell' THEN -shares END) AS shares FROM purchases WHERE user_id = ? GROUP BY symbol HAVING shares > 0", session["user_id"])
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])[0]

    stocks = {}
    value = 0

    for holding in holdings:
        data = lookup(holding["symbol"])
        stock_value = data["price"] * holding["shares"]
        value += stock_value

    for holding in holdings:
        stocks[holding["symbol"]] = holding["shares"]

    if request.method == "POST":

        if request.form.get("symbol") not in stocks:
            return apology("stock not owned", 400)

        shares_str = request.form.get("shares", "").strip()

        try:
            shares_float = float(shares_str)
        except ValueError:
            return apology("invalid number of shares", 400)

        if not shares_float.is_integer():
            return apology("invalid number of shares", 400)

        shares = int(shares_float)

        if shares <= 0 or shares > stocks[request.form.get("symbol")]:
            return apology("invalid amount", 400)

        symbol = lookup(request.form.get("symbol"))

        purchases = db.execute("INSERT INTO purchases (symbol, price, shares, time, user_id, type) VALUES(?, ?, ?, ?, ?, ?)", symbol["symbol"], symbol["price"], shares, datetime.now(), session["user_id"], 'sell')

        proceeds = int(shares) * symbol["price"]

        db.execute( "UPDATE users SET cash = cash + ? WHERE id = ?", proceeds, session["user_id"])

        return redirect("/")

    elif request.method == "GET":
        return render_template("sell.html", stocks=stocks)

@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        money_str = request.form.get("money", "").strip()

        money_str = money_str.replace(",", "")

        try:
            money = float(money_str)
        except ValueError:
            return apology("invalid amount", 400)

        # Must be positive
        if money <= 0:
            return apology("invalid amount", 400)

        current = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        total = int(money) + current

        db.execute("UPDATE users SET cash = ? WHERE id = ?", total, session["user_id"])

        return redirect("/")
    elif request.method == "GET":
        return redirect("/")
