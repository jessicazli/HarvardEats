import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///project.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Collect data from the user (username, password, confirmation)
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Render apology if username, password, confirmation are blank
        if not username:
            return apology("Username Not Entered", 400)
        elif not password:
            return apology("Password Not Entered", 400)
        elif not confirmation:
            return apology("Confirmed Password Not Entered", 400)

        # Password requirements (1 capital letter, 1 number, 1 exclamation or question mark)
        uppercase_counter = 0
        number_counter = 0
        char_counter = 0

        for char in password:
            if char.isupper():
                uppercase_counter += 1
            elif not char.isdigit():
                number_counter += 1
            elif char == "!" or "?":
                char_counter += 1

        if uppercase_counter == 0 or number_counter == 0 or char_counter == 0:
            return apology("Check password requirements", 400)

        # Render apology in password is not same as confirmed password
        if password != confirmation:
            return apology("Password and Confirmation Do Not Match", 400)

        # Insert new user into users and store the password_hash if not exists
        else:
            if len(db.execute("SELECT * FROM users WHERE username = ?", username)) == 0:

                # Use generate_password_hash to hash the user's password
                password_hash = generate_password_hash(password)

                # Add new user to database
                new_user = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, password_hash)

                # Remember users who have logged in
                session["user_id"] = new_user

                # Redirect user to home page
                return redirect("/")

            elif len(db.execute("SELECT * FROM users WHERE username = ?", username)) != 0:
                return apology("Username Taken", 400)

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Render register page
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Render login page
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/")
@login_required
def home():
    """Show user dashboard"""

    cash = db.execute("SELECT cash FROM users WHERE id = ?", session['user_id'])

    # Ensure user exists
    if not cash:
        return redirect("/logout")

    # Set balance equal to cash
    balance = cash[0]["cash"]

    sum_cost = db.execute("SELECT SUM(cost) FROM meals WHERE user_id = ?", session['user_id'])

    # Set spent equal to sum of costs unless user has not spent anything yet
    if sum_cost[0]["SUM(cost)"] == None:
        spent = 0
    else:
        spent = sum_cost[0]["SUM(cost)"]

    # Update users table with amount spent
    db.execute("UPDATE users SET spent = ? WHERE id = ?", spent, session["user_id"])

    # Favorite Restaurants
    tmp = db.execute("SELECT COUNT(DISTINCT restaurant) FROM meals WHERE user_id = ?", session['user_id'])
    length = tmp[0]["COUNT(DISTINCT restaurant)"]
    faves = db.execute("SELECT restaurant FROM meals WHERE user_id=? GROUP BY restaurant ORDER BY COUNT(restaurant) DESC LIMIT 3", session['user_id'])

    # Find percentile of current user
    percentile = db.execute("SELECT rank.percentile_rank FROM users JOIN (SELECT id, PERCENT_RANK() OVER (ORDER BY spent) percentile_rank FROM users) rank ON rank.id = users.id WHERE users.id = ?", session["user_id"])
    percent = round(100 * percentile[0]["percentile_rank"], 2)

    # Pie chart
    datacount = db.execute("SELECT restaurant, COUNT(restaurant) AS no FROM meals GROUP BY restaurant ORDER BY COUNT(restaurant) DESC LIMIT 5")
    enough = len(datacount)
    othercount = db.execute("SELECT COUNT(restaurant) AS no FROM meals WHERE restaurant NOT IN (SELECT restaurant FROM meals GROUP BY restaurant ORDER BY COUNT(restaurant) DESC LIMIT 5)")

    # Live feed
    feed = db.execute(
        "SELECT restaurant, cost, time FROM meals WHERE NOT user_id = ? ORDER BY time DESC LIMIT 5", session["user_id"])

    return render_template("home.html", balance=balance, spent=spent, length=length, enough=enough, datacount=datacount, percent=percent, feed=feed, faves=faves, othercount=othercount)


@app.route("/about")
@login_required
def aboutharvardeats():
    """Go to about page"""

    # Render about page
    return render_template("about.html")


@app.route("/logmeal", methods=["GET", "POST"])
@login_required
def logmeal():
    """Place for users to log their meals"""

    # When form is submitted via POST, log the meal
    if request.method == "POST":

        # Check for valid input
        if not request.form.get("restaurant"):
            return apology("Must provide restaurant name", 400)

        # Make sure cost is valid (positive and has 2 places past the decimal point)
        if float(request.form.get("cost")) <= 0:
            return apology("Cost must be positive", 400)

        cost = round(float(request.form.get("cost")), 2)
        cash = db.execute(
            "SELECT cash FROM users WHERE id = ?", session['user_id'])

        # Ensure user exists
        if not cash:
            return redirect("/logout")
        balance = cash[0]["cash"]
        restaurant = request.form.get('restaurant')

        # Insert into meals table new purchase
        db.execute(
            "INSERT INTO meals (user_id, restaurant, cost) VALUES (?, ?, ?)", session['user_id'], restaurant, cost)

        # Subtract cash from user's account
        db.execute(
            "UPDATE users SET cash = ? - ? WHERE id = ?", balance, cost, session['user_id'])

        # Display webpage
        return render_template("logged.html", restaurant=restaurant, cost=cost, cash=(balance - cost))

    # When submitted via GET, display form to log a meal
    else:
        return render_template("logmeal.html")

@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    """Allow users to add money to their account."""

    # When form is submitted via POST, add the amount of cash the user specificed to their account.
    if request.method == "POST":
        if not str.isdigit(request.form.get("amount")) or int(request.form.get("amount")) < 0:
            return apology("Amount to add must be non-negative integer", 400)

        # Update the amount of cash in the user's account
        else:
            amount = int(request.form.get('amount'))
            cash = db.execute(
                "SELECT cash FROM users WHERE id = ?", session['user_id'])

            # Ensure user exists
            if not cash:
                return redirect("/logout")

            balance = cash[0]["cash"]
            db.execute(
                "UPDATE users SET cash = (? + ?) WHERE id = ?", balance, amount, session['user_id'])

            return render_template("added.html", amount=amount)

    # When requested via GET, display form to add cash
    else:

        # Render add page
        return render_template("add.html")

@app.route("/pastmeals")
@login_required
def pastmeals():
    """Show past meals"""

    # Obtain the restaurant, cost, and time of a meal
    meals = db.execute("SELECT restaurant, cost, time FROM meals WHERE user_id = ? ORDER BY time DESC",  session["user_id"])

    # Render past meals page
    return render_template("pastmeals.html", meals=meals, usd=usd)

@app.route("/schedule")
@login_required
def schedule():
    """Go to schedule page"""

    # Render schedule page
    return render_template("schedule.html")