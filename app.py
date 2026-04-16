from flask import Flask, render_template, request, redirect, session, url_for, send_file
import sqlite3
import os
import io
import json
from fpdf import FPDF
from werkzeug.utils import secure_filename
from datetime import datetime
# --- GOOGLE LOGIN IMPORTS ---
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
app.secret_key = 'amit_project_key'

# --- LOCAL TESTING FIX ---
# Google Login ko bina HTTPS ke local machine par chalane ke liye
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# ------------------ GOOGLE OAUTH CONFIG ------------------
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id='YOUR_GOOGLE_CLIENT_ID', # Apne Google Console se yahan dalo
    client_secret='YOUR_GOOGLE_CLIENT_SECRET', # Apne Google Console se yahan dalo
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
    client_kwargs={'scope': 'openid email profile'},
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
)

# ------------------ PATH CONFIG ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ------------------ DB CONNECTION ------------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ------------------ INIT DB ------------------
def init_db():
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      username TEXT, 
                      password TEXT, 
                      points INTEGER DEFAULT 0)''')

        c.execute('''CREATE TABLE IF NOT EXISTS requests 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      item_name TEXT, 
                      quantity INTEGER, 
                      address TEXT, 
                      status TEXT,
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        conn.close()
        print("Database Ready!")

init_db()

def ai_smart_detect(filename):
    filename = filename.lower()
    if 'laptop' in filename: return "Laptop (Detected via AI)"
    elif 'phone' in filename or 'mobile' in filename: return "Mobile Phone (Detected via AI)"
    elif 'keyboard' in filename: return "Keyboard (Detected via AI)"
    elif 'mouse' in filename: return "Mouse (Detected via AI)"
    else: return "Electronic Gadget (Unknown Type)"

# ================= GOOGLE LOGIN ROUTES =================

@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login/callback')
def google_callback():
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()
    email = user_info['email']
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (email,)).fetchone()
    
    if not user:
        conn.execute('INSERT INTO users (username, password, points) VALUES (?, ?, 0)', (email, 'google_auth_user'))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (email,)).fetchone()
    conn.close()

    session.clear()
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = 'student'
    return redirect(url_for('dashboard'))

# ================= STANDARD ROUTES =================

@app.route('/')
def home():
    if session.get('role') == 'admin': return redirect(url_for('admin_panel'))
    elif session.get('role') == 'student': return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        username = request.form['username']
        password = request.form['password']

        if role == "admin" and username == "admin" and password == "admin123":
            session.clear()
            session['role'] = 'admin'
            session['username'] = 'Admin'
            return redirect(url_for('admin_panel'))

        if role == "student":
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
            conn.close()
            if user:
                session.clear()
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = 'student'
                return redirect(url_for('dashboard'))
        return "Invalid Credentials! <a href='/login'>Try Again</a>"
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        conn.execute('INSERT INTO users (username, password, points) VALUES (?, ?, 0)', (username, password))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if session.get('role') != 'student': return redirect(url_for('login'))
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    reqs = conn.execute('SELECT * FROM requests WHERE user_id = ? ORDER BY id DESC', (session['user_id'],)).fetchall()
    leaderboard = conn.execute('SELECT username, points FROM users ORDER BY points DESC LIMIT 3').fetchall()
    conn.close()
    return render_template('dashboard.html', requests=reqs, name=session['username'], points=user['points'], leaderboard=leaderboard)

@app.route('/add_request', methods=['GET', 'POST'])
def add_request():
    if session.get('role') != 'student': return redirect(url_for('login'))
    if request.method == 'POST':
        file = request.files['file']
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        detected_item_name = ai_smart_detect(filename)
        qty = request.form.get('quantity')
        addr = request.form.get('address')
        conn = get_db_connection()
        conn.execute('INSERT INTO requests (user_id, item_name, quantity, address, status) VALUES (?, ?, ?, ?, ?)',
                     (session['user_id'], detected_item_name, qty, addr, 'Pending'))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    return render_template('add_request.html')

@app.route('/admin')
def admin_panel():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    all_requests = conn.execute('SELECT requests.*, users.username FROM requests JOIN users ON requests.user_id = users.id ORDER BY requests.id DESC').fetchall()
    laptops = conn.execute("SELECT COUNT(*) FROM requests WHERE item_name LIKE '%Laptop%'").fetchone()[0]
    mobiles = conn.execute("SELECT COUNT(*) FROM requests WHERE item_name LIKE '%Mobile%'").fetchone()[0]
    keyboards = conn.execute("SELECT COUNT(*) FROM requests WHERE item_name LIKE '%Keyboard%'").fetchone()[0]
    others = conn.execute("SELECT COUNT(*) FROM requests WHERE item_name NOT LIKE '%Laptop%' AND item_name NOT LIKE '%Mobile%' AND item_name NOT LIKE '%Keyboard%'").fetchone()[0]
    
    pie_labels = ["Laptops", "Mobiles", "Keyboards", "Others"]
    pie_values = [laptops, mobiles, keyboards, others]
    
    total_recycled = conn.execute("SELECT COUNT(*) FROM requests WHERE status = 'Recycled'").fetchone()[0]
    total_pending = conn.execute("SELECT COUNT(*) FROM requests WHERE status = 'Pending'").fetchone()[0]
    line_labels = ["Total Requests", "Recycled", "Pending"]
    line_values = [len(all_requests), total_recycled, total_pending]
    conn.close()

    return render_template('admin.html', requests=all_requests, pie_labels=json.dumps(pie_labels), pie_values=json.dumps(pie_values), line_labels=json.dumps(line_labels), line_values=json.dumps(line_values))

@app.route('/update_status/<int:req_id>/<string:new_status>')
def update_status(req_id, new_status):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection()
    req = conn.execute('SELECT * FROM requests WHERE id = ?', (req_id,)).fetchone()
    if new_status == 'Recycled' and req['status'] != 'Recycled':
        item_name = req['item_name'].lower()
        points_to_add = 10
        if 'laptop' in item_name: points_to_add = 50
        elif 'phone' in item_name: points_to_add = 30
        conn.execute('UPDATE users SET points = points + ? WHERE id = ?', (points_to_add, req['user_id']))
    conn.execute('UPDATE requests SET status = ? WHERE id = ?', (new_status, req_id))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/download_certificate/<int:req_id>')
def download_certificate(req_id):
    if session.get('role') != 'student': return redirect(url_for('login'))
    conn = get_db_connection()
    data = conn.execute('SELECT requests.*, users.username FROM requests JOIN users ON requests.user_id = users.id WHERE requests.id = ? AND requests.user_id = ?', (req_id, session['user_id'])).fetchone()
    conn.close()
    if not data or data['status'] != 'Recycled': return "Not available"

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_draw_color(46, 125, 50)
    pdf.set_line_width(2)
    pdf.rect(10, 10, 277, 190) 
    pdf.set_line_width(0.5)
    pdf.rect(13, 13, 271, 184)
    pdf.ln(20)
    pdf.set_font("Arial", 'B', 35)
    pdf.set_text_color(46, 125, 50)
    pdf.cell(0, 20, "CERTIFICATE OF RECYCLING", ln=True, align='C')
    pdf.set_font("Arial", 'I', 15)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "This is to certify that", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 28)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 15, data['username'].upper(), ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", size=14)
    pdf.set_text_color(50, 50, 50)
    pdf.multi_cell(0, 10, f"has successfully contributed to environmental sustainability by\nresponsibly recycling {data['item_name']}.", align='C')
    
    # Impact Badge Fix
    pdf.ln(10)
    pdf.set_fill_color(232, 245, 233)
    pdf.set_text_color(27, 94, 32)
    pdf.set_font("Arial", 'B', 12)
    pdf.set_x(98.5) 
    pdf.cell(100, 12, "OFFICIAL ECO-WARRIOR STATUS", ln=True, align='C', fill=True)

    pdf.set_y(160)
    pdf.set_font("Arial", 'B', 12)
    pdf.set_x(30)
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%d-%m-%Y')}", ln=0)
    pdf.set_x(200)
    pdf.cell(0, 10, "Authorized by e-Cycle AI", ln=1)

    pdf_output = pdf.output(dest='S').encode('latin-1')
    return send_file(io.BytesIO(pdf_output), mimetype='application/pdf', as_attachment=True, download_name='eCycle_Certificate.pdf')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)