from flask import Flask, render_template, request, redirect, session, url_for, send_file
import sqlite3
import os
import io
import json
from fpdf import FPDF
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'amit_project_key'

# ---------------- PATH CONFIG ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ---------------- DB CONNECTION ----------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- INIT DB ----------------
def init_db():
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute('''CREATE TABLE users 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      username TEXT, 
                      password TEXT, 
                      points INTEGER DEFAULT 0)''')

        c.execute('''CREATE TABLE requests 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      item_name TEXT, 
                      quantity INTEGER, 
                      address TEXT, 
                      status TEXT,
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        conn.commit()
        conn.close()

init_db()

# ---------------- IMPROVED AI LOGIC ----------------
def ai_smart_detect(filename):
    name = filename.lower()

    # better keyword matching
    keywords = {
        "Laptop": ["laptop", "notebook", "macbook"],
        "Mobile Phone": ["phone", "mobile", "iphone", "android"],
        "Keyboard": ["keyboard"],
        "Mouse": ["mouse"],
        "Monitor": ["monitor", "screen", "display"],
        "TV": ["tv", "television"],
        "Charger": ["charger", "adapter"],
        "Headphones": ["headphone", "earphone", "earbuds"]
    }

    for item, words in keywords.items():
        for w in words:
            if w in name:
                return f"{item} (AI Detected)"

    return "E-Waste Item (General)"

# ================= ROUTES =================

@app.route('/')
def home():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_panel'))
    elif session.get('role') == 'student':
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        username = request.form['username']
        password = request.form['password']

        # ADMIN LOGIN
        if role == "admin" and username == "admin" and password == "admin123":
            session.clear()
            session['role'] = 'admin'
            session['username'] = 'Admin'
            return redirect(url_for('admin_panel'))

        # STUDENT LOGIN
        if role == "student":
            conn = get_db_connection()
            user = conn.execute(
                'SELECT * FROM users WHERE username = ? AND password = ?',
                (username, password)
            ).fetchone()
            conn.close()

            if user:
                session.clear()
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = 'student'
                return redirect(url_for('dashboard'))

        return "Invalid Credentials!"

    return render_template('login.html')

# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO users (username, password) VALUES (?, ?)',
            (request.form['username'], request.form['password'])
        )
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

# ---------------- DASHBOARD ----------------
@app.route('/dashboard')
def dashboard():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE id = ?',
        (session['user_id'],)
    ).fetchone()

    reqs = conn.execute(
        'SELECT * FROM requests WHERE user_id = ? ORDER BY id DESC',
        (session['user_id'],)
    ).fetchall()

    leaderboard = conn.execute(
        'SELECT username, points FROM users ORDER BY points DESC LIMIT 3'
    ).fetchall()

    conn.close()

    return render_template(
        'dashboard.html',
        requests=reqs,
        name=session['username'],
        points=user['points'],
        leaderboard=leaderboard
    )

# ---------------- ADD REQUEST ----------------
@app.route('/add_request', methods=['GET', 'POST'])
def add_request():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files['file']
        filename = secure_filename(file.filename)

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        detected_item = ai_smart_detect(filename)

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO requests (user_id, item_name, quantity, address, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            session['user_id'],
            detected_item,
            request.form['quantity'],
            request.form['address'],
            'Pending'
        ))
        conn.commit()
        conn.close()

        return redirect(url_for('dashboard'))

    return render_template('add_request.html')

# ---------------- ADMIN PANEL ----------------
@app.route('/admin')
def admin_panel():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()

    all_requests = conn.execute('''
        SELECT requests.*, users.username 
        FROM requests 
        JOIN users ON requests.user_id = users.id
        ORDER BY requests.id DESC
    ''').fetchall()

    laptops = conn.execute("SELECT COUNT(*) FROM requests WHERE item_name LIKE '%Laptop%'").fetchone()[0]
    mobiles = conn.execute("SELECT COUNT(*) FROM requests WHERE item_name LIKE '%Mobile%'").fetchone()[0]
    others = len(all_requests) - laptops - mobiles

    conn.close()

    return render_template(
        'admin.html',
        requests=all_requests,
        pie_labels=json.dumps(["Laptop", "Mobile", "Others"]),
        pie_values=json.dumps([laptops, mobiles, others])
    )

# ---------------- STATUS UPDATE ----------------
@app.route('/update_status/<int:req_id>/<string:new_status>')
def update_status(req_id, new_status):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    req = conn.execute('SELECT * FROM requests WHERE id=?', (req_id,)).fetchone()

    if new_status == 'Recycled' and req['status'] != 'Recycled':
        points = 20
        if 'laptop' in req['item_name'].lower():
            points = 50
        elif 'mobile' in req['item_name'].lower():
            points = 30

        conn.execute('UPDATE users SET points = points + ? WHERE id=?',
                     (points, req['user_id']))

    conn.execute('UPDATE requests SET status=? WHERE id=?',
                 (new_status, req_id))

    conn.commit()
    conn.close()

    return redirect(url_for('admin_panel'))

# ---------------- CERTIFICATE (IMPROVED 🔥) ----------------
@app.route('/download_certificate/<int:req_id>')
def download_certificate(req_id):
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    conn = get_db_connection()
    data = conn.execute('''
        SELECT requests.*, users.username 
        FROM requests 
        JOIN users ON requests.user_id = users.id 
        WHERE requests.id = ?
    ''', (req_id,)).fetchone()
    conn.close()

    if not data or data['status'] != 'Recycled':
        return "Not Available"

    pdf = FPDF('L', 'mm', 'A4')
    pdf.add_page()

    # BORDER
    pdf.set_line_width(2)
    pdf.rect(10, 10, 277, 190)

    # TITLE
    pdf.set_font("Arial", 'B', 32)
    pdf.cell(0, 30, "E-WASTE RECYCLING CERTIFICATE", ln=True, align='C')

    # NAME
    pdf.set_font("Arial", 'B', 26)
    pdf.cell(0, 20, data['username'].upper(), ln=True, align='C')

    # BODY
    pdf.set_font("Arial", '', 16)
    pdf.multi_cell(0, 10,
        f"Successfully recycled {data['item_name']}.\n"
        f"Your contribution helps save the environment",
        align='C'
    )

    # DATE
    pdf.ln(10)
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%d %B %Y')}", align='C')

    output = pdf.output(dest='S').encode('latin-1')

    return send_file(
        io.BytesIO(output),
        mimetype='application/pdf',
        as_attachment=True,
        download_name='certificate.pdf'
    )

# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------------- RUN ----------------
if __name__ == '__main__':
    app.run(debug=True)