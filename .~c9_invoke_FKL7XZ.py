import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import numbers

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    current_user_id = session["user_id"]

    user_shares_dict = db.execute("SELECT symbol, name, SUM(amount) FROM shares WHERE user_id = ? GROUP BY symbol", current_user_id)

    user_cash = db.execute("SELECT cash FROM users WHERE id = ?", current_user_id)

    user_total_cash = 0
    for counter in range(len(user_shares_dict)):
        quotation_dict = lookup(user_shares_dict[counter]["symbol"])

        user_shares_dict[counter]["price"] = quotation_dict["price"]
        user_shares_dict[counter]["total"] = user_shares_dict[counter]["price"] * user_shares_dict[counter]["SUM(amount)"]

        user_shares_dict[counter]["price_USD"] = usd(quotation_dict["price"])
        user_shares_dict[counter]["total_USD"] = usd(user_shares_dict[counter]["total"])
        user_total_cash += user_shares_dict[counter]["total"]


    new_list = [invalid for invalid in user_shares_dict if invalid["SUM(amount)"] > 0]

    user_total_cash += user_cash[0]["cash"]
    user_current_cash = user_cash[0]["cash"]

    return render_template("index.html",
                            user_shares = new_list,
                            user_total_cash = usd(user_total_cash),
                            user_current_cash = usd(user_current_cash))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")

    else:
        #Check if the form was submited correct
        if not request.form.get("buy_symbol"):
            return apology("Symbol field is empty")

        if not request.form.get("buy_shares"):
            return apology("Shares field is empty")

        #Check if the symbol provided exists
        quotation_dict = lookup(request.form.get("buy_symbol"))

        if quotation_dict == None:
            return apology("Symbol not found")

        #Get what user is logged in
        current_user_id = session["user_id"]
        row = db.execute("SELECT * FROM users WHERE id = ?", current_user_id)

        #store user information about the sale and amount of cash
        quotation_price = float(quotation_dict["price"])
        quotation_company_name = quotation_dict["name"]
        user_total_shares = int(request.form.get("buy_shares"))
        user_total_cash = float(row[0]["cash"])

        user_total_expense = quotation_price * user_total_shares

        #calculate if the user has suficient cash
        if user_total_expense > user_total_cash:
            return apology("can't afford")

        user_remaining_cash = user_total_cash - user_total_expense

        table_exists = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shares'")

        if len(table_exists) == 0:
            db.execute("CREATE TABLE shares(user_id INT NOT NULL, symbol TEXT, name TEXT, amount INT, price FLOAT, transacted TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id))")

        symbol = request.form.get("buy_symbol")
        transacted = datetime.now()

        db.execute("INSERT INTO shares(user_id, symbol, name, amount, price, transacted) VALUES(?,?,?,?,?,?)",
                    current_user_id, symbol, quotation_company_name, user_total_shares, quotation_price, transacted)

        print(db.execute("SELECT * FROM shares"))

        db.execute("UPDATE users SET cash = ? WHERE id = ?", user_remaining_cash, current_user_id)

        flash("Bought!")
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    current_user_id = session["user_id"]

    user_shares = db.execute("SELECT * FROM shares WHERE user_id = ?", current_user_id)

    for row in range(len(user_shares)):
        user_shares[row]["price_USD"] = usd(user_shares[row]["price"])

    return render_template("history.html", user_shares=user_shares)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
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
    quotation_sent = False
    if request.method == "GET":
        return render_template("quote.html", quotation_sent = quotation_sent)

    else:
        quotation_dict = lookup(request.form.get("quote_symbol"))

        if quotation_dict != None:
            quotation_name = quotation_dict["name"]
            quotation_price = usd(quotation_dict["price"])
            quotation_symbol = quotation_dict["symbol"]
            quotation_sent = True

            return render_template("quote.html",
                                    quotation_name = quotation_name,
                                    quotation_price = quotation_price,
                                    quotation_symbol = quotation_symbol,
                                    quotation_sent = quotation_sent)

        else:
            return apology("Symbol not found")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    else:
        #verify if the user filled every field
        if not request.form.get("username"):
            return apology("Must provide a username", 403)

        if not request.form.get("password"):
            return apology("Must provide a password", 403)

        if not request.form.get("confirm_password"):
            return apology("Must confirm password", 403)

        #save user typed informations
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        #check match passwords
        if password != confirm_password:
            return apology("Password doesn't match", 403)

        #check user already exists
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        #if not exists, then create one
        if len(rows) == 0:
            password_hash = generate_password_hash(password)
            db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", username, password_hash)

        #else show an error message
        else:
            return apology("Username already exists", 403)

        new_row = db.execute("SELECT * FROM users WHERE username = ?", username)

        session["user_id"] = new_row[0]["id"]
        flash("You were successfully Registered")
        return redirect("/")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    current_user_id = session["user_id"]

    if request.method == "GET":
        user_symbols = db.execute("SELECT symbol, SUM(amount) FROM shares WHERE user_id = ? GROUP BY symbol", current_user_id)

        available_symbols = [empty for empty in user_symbols if empty["SUM(amount)"] > 0]

        return render_template("sell.html", user_symbols=available_symbols)

    else:
        user_symbol = request.form.get("selected_symbol")
        user_sell_shares = int(request.form.get("sell_shares"))
        user_total_shares = db.execute("SELECT SUM(amount) FROM shares WHERE user_id = ? AND symbol = ? GROUP BY symbol", current_user_id, user_symbol)
        user_total_cash = db.execute("SELECT cash FROM users WHERE id = ?", current_user_id)

        if not user_symbol:
            return apology("Provide a symbol to sell")

        if int(user_total_shares[0]["SUM(amount)"]) < user_sell_shares:
            return apology("Insuficient Shares")


        quotation_dict = lookup(user_symbol)

        quotation_company_name = quotation_dict["name"]
        quotation_price = float(quotation_dict["price"])
        user_remaining_cash = user_total_cash[0]["cash"] + (user_sell_shares * quotation_price)

        user_sell_shares = -user_sell_shares
        transacted = datetime.now()

        db.execute("INSERT INTO shares(user_id, symbol, name, amount, price, transacted) VALUES(?,?,?,?,?,?)",
                    current_user_id, user_symbol, quotation_company_name, user_sell_shares, quotation_price, transacted)


        db.execute("UPDATE users SET cash = ? WHERE id = ?", user_remaining_cash, current_user_id)

        flash("Sold!")
        return redirect("/")

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():

    if request.method == "GET":
        return render_template("deposit.html")

    elif request.method == "POST":
        current_user_id = session["user_id"]
        user_deposit_cash = request.form.get("deposit_cash")
        user_current_cash = db.execute("SELECT cash FROM users WHERE id = ?", current_user_id)

        if not user_deposit_cash.isnumeric():
            return apology("Digit only numbers")

        if int(user_deposit_cash) > 1000000:
            return apology("Cash limit is 1.000.000")

        if int(user_deposit_cash) < 0:
            return apology("Cash cannot be negative")


        user_new_amount = int(user_deposit_cash) + user_current_cash[0]["cash"]

        db.execute("UPDATE users SET cash = ? WHERE id = ?", user_new_amount, current_user_id)

        flash("Your cash has been deposited")
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
