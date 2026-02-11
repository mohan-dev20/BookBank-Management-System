from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import sqlite3, os
from datetime import date, timedelta
from werkzeug.utils import secure_filename
from PIL import Image
from flask import flash
app = Flask(__name__)
app.secret_key = "smart_book_bank"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join("static", "images")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

UPLOAD_FOLDER = 'static/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- HELPERS ----------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def resize_image(path):
    img = Image.open(path)
    img = img.resize((200, 300))
    img.save(path)

@app.route("/")
def home():
    return redirect(url_for("login"))

# ---------------- INIT DB ----------------
@app.route("/initdb")
def initdb():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        password TEXT,
        role TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS books(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        author TEXT,
        image TEXT,
        quantity INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS issued_books(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER,
        user_id INTEGER,
        issued_date TEXT,
        due_date TEXT,
        returned INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS cart(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        book_id INTEGER
    )
    """)

    conn.commit()
    conn.close()
    return "Database Initialized"

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            flash("All fields are required")
            return redirect(url_for("login"))

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email, password)
        ).fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("student_dashboard"))

        flash("Invalid credentials")
        return redirect(url_for("login"))

    return render_template("login.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()
    total_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    total_students = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role='student'"
    ).fetchone()[0]
    issued = conn.execute(
        "SELECT COUNT(*) FROM issued_books WHERE returned=0"
    ).fetchone()[0]
    conn.close()

    return render_template(
        "admin_dashboard.html",
        total_books=total_books,
        total_students=total_students,
        issued=issued
    )

# ---------------- ISSUED BOOKS (ADMIN) ----------------
@app.route("/issued_books")
def issued_books():
    if session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()
    issued = conn.execute("""
        SELECT issued_books.id,
               books.title,
               users.name,
               issued_books.issued_date,
               issued_books.due_date,
               issued_books.returned
        FROM issued_books
        JOIN books ON issued_books.book_id = books.id
        JOIN users ON issued_books.user_id = users.id
    """).fetchall()
    conn.close()

    return render_template("issued_books.html", issued=issued)

# ---------------- ADD BOOK ----------------
@app.route("/admin/add_book", methods=["GET", "POST"])
def add_book():
    if session.get("role") != "admin":
        return redirect("/login")

    if request.method == "POST":
        title = request.form["title"]
        author = request.form["author"]
        quantity = request.form["quantity"]
        image_file = request.files["image"]
        image_name = "default.png"

        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            image_file.save(path)
            resize_image(path)
            image_name = filename

        conn = get_db()
        conn.execute(
            "INSERT INTO books(title,author,image,quantity) VALUES(?,?,?,?)",
            (title, author, image_name, quantity)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("admin"))

    return render_template("add_book.html")

# ---------------- STUDENT DASHBOARD ----------------
@app.route('/student')
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))

    conn = get_db()

    borrowed_books = conn.execute("""
        SELECT issued_books.id AS issue_id,
               books.title,
               books.author,
               issued_books.due_date
        FROM issued_books
        JOIN books ON books.id = issued_books.book_id
        WHERE issued_books.user_id = ? AND issued_books.returned = 0
    """, (session['user_id'],)).fetchall()

    available_books = conn.execute("""
        SELECT * FROM books WHERE quantity > 0
    """).fetchall()

    conn.close()

    return render_template(
        'student_dashboard.html',
        borrowed_books=borrowed_books,
        available_books=available_books
    )


# ---------------- AVAILABLE BOOKS ----------------
@app.route("/books")
def books():
    conn = get_db()
    books = conn.execute("SELECT * FROM books").fetchall()
    conn.close()
    return render_template("available_books.html", books=books)

# ---------------- ISSUE BOOK ----------------
@app.route("/issue/<int:book_id>")
def issue(book_id):
    user_id = session["user_id"]
    issued_date = date.today()
    due_date = issued_date + timedelta(days=14)

    conn = get_db()
    conn.execute("""
        INSERT INTO issued_books(book_id,user_id,issued_date,due_date)
        VALUES(?,?,?,?)
    """, (book_id, user_id, issued_date, due_date))

    conn.execute(
        "UPDATE books SET quantity=quantity-1 WHERE id=?",
        (book_id,)
    )
    conn.commit()
    conn.close()
    return redirect("/my_books")

# ---------------- MY BOOKS ----------------
@app.route("/my_books")
def my_books():
    if session.get("role") != "student":
        return redirect("/login")

    user_id = session["user_id"]
    today = date.today()

    conn = get_db()
    rows = conn.execute("""
        SELECT issued_books.id,
               books.title,
               issued_books.due_date,
               issued_books.fine_paid
        FROM issued_books
        JOIN books ON issued_books.book_id = books.id
        WHERE issued_books.user_id=? AND returned=0
    """, (user_id,)).fetchall()

    books = []

    for r in rows:
        due = date.fromisoformat(r["due_date"])
        days_late = (today - due).days
        fine = days_late * 2 if days_late > 0 else 0

        # update fine in DB
        conn.execute(
            "UPDATE issued_books SET fine_amount=? WHERE id=?",
            (fine, r["id"])
        )

        books.append({
            "id": r["id"],
            "title": r["title"],
            "due_date": r["due_date"],
            "fine": fine,
            "paid": r["fine_paid"]
        })

    conn.commit()
    conn.close()

    return render_template("my_books.html", books=books)

# ---------------- RETURN BOOK ----------------
@app.route("/return/<int:issue_id>")
def return_book(issue_id):
    if session.get("role") != "student":
        return redirect("/login")

    conn = get_db()
    row = conn.execute("""
        SELECT fine_amount, fine_paid, book_id
        FROM issued_books
        WHERE id=?
    """, (issue_id,)).fetchone()

    if row["fine_amount"] > 0 and row["fine_paid"] == 0:
        conn.close()
        return "❌ Pay fine before returning book"

    conn.execute(
        "UPDATE issued_books SET returned=1 WHERE id=?",
        (issue_id,)
    )
    conn.execute(
        "UPDATE books SET quantity=quantity+1 WHERE id=?",
        (row["book_id"],)
    )

    conn.commit()
    conn.close()
    return redirect("/my_books")

#------------FINE----------------
@app.route("/pay_fine/<int:issue_id>")
def pay_fine(issue_id):
    if session.get("role") != "student":
        return redirect("/login")

    conn = get_db()
    conn.execute(
        "UPDATE issued_books SET fine_paid=1 WHERE id=?",
        (issue_id,)
    )
    conn.commit()
    conn.close()

    return redirect("/my_books")


#------BORRED BOOKS----------------------------------
@app.route("/borrow/<int:book_id>")
def borrow_book(book_id):
    if session.get("role") != "student":
        return redirect(url_for("login"))

    user_id = session["user_id"]
    issued_date = date.today()
    due_date = issued_date + timedelta(days=14)

    conn = get_db()
    conn.execute("""
        INSERT INTO issued_books (book_id, user_id, issued_date, due_date)
        VALUES (?, ?, ?, ?)
    """, (book_id, user_id, issued_date, due_date))

    conn.execute("""
        UPDATE books SET quantity = quantity - 1 WHERE id = ?
    """, (book_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("student_dashboard"))


# ---------------- AI HELP ----------------
@app.route("/ai", methods=["GET", "POST"])
def ai_help():
    if request.method == "POST":
        q = request.form["question"].lower()
        if "fine" in q:
            a = "₹2 per day after due date."
        elif "days" in q:
            a = "Books can be kept for 14 days."
        else:
            a = "Please contact the librarian."
        return jsonify({"answer": a})

    return render_template("ai_help.html")

#----------ADD TO CART----------------------------
@app.route('/add_to_cart/<int:book_id>')
def add_to_cart(book_id):
    if session.get("role") != "student":
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute(
        "INSERT INTO cart (user_id, book_id) VALUES (?, ?)",
        (session["user_id"], book_id)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("student_dashboard"))

# ---------------- DELETE BOOK (ADMIN) ----------------
@app.route("/admin/delete_book/<int:book_id>")
def delete_book(book_id):
    conn = get_db()

    book = conn.execute(
        "SELECT image FROM books WHERE id=?",
        (book_id,)
    ).fetchone()

    if book:
        image_name = book["image"]

        # Delete image only if valid and not default
        if image_name and image_name != "default.png":
            image_path = os.path.join("static", "images", image_name)

            if os.path.exists(image_path):
                os.remove(image_path)

        # Delete book from database
        conn.execute("DELETE FROM books WHERE id=?", (book_id,))
        conn.commit()

    conn.close()

    flash("Book deleted successfully")
    return redirect(url_for("issued_books"))


# ---------------- VIEW CART ----------------
@app.route("/cart")
def view_cart():
    if session.get("role") != "student":
        return redirect(url_for("login"))

    conn = get_db()

    cart_items = conn.execute("""
        SELECT cart.id, books.title, books.author, books.image
        FROM cart
        JOIN books ON cart.book_id = books.id
        WHERE cart.user_id = ?
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template("cart.html", cart_items=cart_items)

# ---------------- REMOVE FROM CART ----------------
@app.route("/remove_from_cart/<int:cart_id>")
def remove_from_cart(cart_id):
    if session.get("role") != "student":
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM cart WHERE id=?", (cart_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("view_cart"))


if __name__ == "__main__":
    app.run(debug=True)
