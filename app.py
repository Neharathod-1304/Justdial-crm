from flask import Flask, render_template, jsonify, redirect, url_for, request, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from datetime import datetime, timedelta
from sqlalchemy import func
import pandas as pd
import io
import os
import random

app = Flask(__name__)

# Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///justdial_leads.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'teztecch_professional_crm_key'

db = SQLAlchemy(app)

# Login Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ================= MODELS =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    service_query = db.Column(db.String(200))
    lead_source = db.Column(db.String(50), default="Justdial")
    status = db.Column(db.String(20), default="New")
    notes = db.Column(db.Text, default="")
    timestamp = db.Column(db.DateTime, default=datetime.now)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ================= PRE-FILLED DATA SEEDING =================
# Isse teacher ke kholte hi data hamesha taiyaar milega

def seed_default_data():
    if Lead.query.count() == 0:
        first_names = ["Amit", "Pooja", "Sameer", "Kavita", "Rohan", "Anjali", "Vikram", "Suresh", "Rahul", "Sneha"]
        last_names = ["Sharma", "Verma", "Khan", "Iyer", "Deshmukh", "Gupta", "Rathore", "Kumar", "Mehta", "Joshi"]
        queries = ["UI/UX Audit", "Web Design", "App Development", "SEO Services", "Social Media Marketing"]
        statuses = ["New", "Contacted", "Converted", "Lost"]

        # Pichle 4 dino ka background data automatic generate karega
        for day in range(4, -1, -1):
            leads_per_day = random.randint(2, 4)  # Har din ke liye 2 se 4 leads
            for _ in range(leads_per_day):
                name = f"{random.choice(first_names)} {random.choice(last_names)}"
                phone = f"{random.randint(7000000000, 9999999999)}"
                lead_time = datetime.now() - timedelta(days=day, hours=random.randint(1, 12))
                
                lead = Lead(
                    customer_name=name,
                    phone=phone,
                    service_query=random.choice(queries),
                    status=random.choice(statuses),
                    timestamp=lead_time
                )
                db.session.add(lead)
        db.session.commit()

# DB Tables creation aur Initialization
with app.app_context():
    db.create_all()
    # Create default Admin
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='123')
        db.session.add(admin)
        db.session.commit()
    # Automatically seed data taaki blank na dikhe
    seed_default_data()

# ================= ROUTES =================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username'), password=request.form.get('password')).first()
        if user:
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid Username or Password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    query = Lead.query

    if search_query:
        query = query.filter((Lead.customer_name.like(f'%{search_query}%')) | (Lead.phone.like(f'%{search_query}%')))
    if status_filter:
        query = query.filter_by(status=status_filter)

    leads = query.order_by(Lead.id.desc()).all()

    # Metrics Counters
    total = Lead.query.count()
    pending = Lead.query.filter_by(status='New').count()
    won = Lead.query.filter_by(status='Converted').count()
    conv_rate = round((won / total * 100), 1) if total > 0 else 0

    # Grouping logic for dynamic frontend charts
    daily_stats = db.session.query(
        func.date(Lead.timestamp).label('date'),
        func.count(Lead.id).label('count')
    ).group_by(func.date(Lead.timestamp)).order_by(func.date(Lead.timestamp)).all()

    chart_labels = []
    chart_values = []
    for row in daily_stats:
        if row.date:
            date_obj = datetime.strptime(str(row.date), '%Y-%m-%d')
            chart_labels.append(date_obj.strftime('%d %b'))
            chart_values.append(int(row.count))

    return render_template('dashboard.html',
        leads=leads, total=total, pending=pending, won=won,
        conv_rate=conv_rate, chart_labels=chart_labels, chart_values=chart_values
    )

@app.route('/update-status/<int:id>/<string:new_status>')
@login_required
def update_status(id, new_status):
    lead = db.session.get(Lead, id)
    if lead:
        lead.status = new_status
        db.session.commit()
        flash(f'Status updated to {new_status}', 'success')
    return redirect(url_for('index'))

@app.route('/update-note/<int:id>', methods=['POST'])
@login_required
def update_note(id):
    data = request.get_json() or {}
    lead = db.session.get(Lead, id)
    if lead:
        lead.notes = data.get('notes', '')
        db.session.commit()
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 404

@app.route('/delete-lead/<int:id>')
@login_required
def delete_lead(id):
    lead = db.session.get(Lead, id)
    if lead:
        db.session.delete(lead)
        db.session.commit()
        flash('Lead deleted successfully', 'warning')
    return redirect(url_for('index'))

@app.route('/api/sync-justdial')
@login_required
def sync():
    first_names = ["Amit", "Pooja", "Sameer", "Kavita", "Rohan", "Anjali", "Vikram", "Suresh"]
    last_names = ["Sharma", "Verma", "Khan", "Iyer", "Deshmukh", "Gupta", "Rathore", "Kumar"]
    queries = ["Web Design", "App Development", "SEO Services", "Social Media Marketing", "Graphic Design"]
    
    how_many = random.randint(2, 4)
    new_leads = []

    for _ in range(how_many):
        random_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        random_phone = f"{random.randint(7000000000, 9999999999)}"
        
        lead = Lead(
            customer_name=random_name,
            phone=random_phone,
            service_query=random.choice(queries),
            status="New",  # Sync par humesha fresh 'New' lead aayegi
            timestamp=datetime.now()
        )
        new_leads.append(lead)

    db.session.add_all(new_leads)
    db.session.commit()

    flash(f"Justdial API: {how_many} Live Leads Synced!", "success")
    return redirect(url_for('index'))

@app.route('/export-leads')
@login_required
def export_leads():
    leads = Lead.query.all()
    data = [{"Name": l.customer_name, "Phone": l.phone, "Service": l.service_query, "Status": l.status, "Notes": l.notes} for l in leads]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name="Leads.xlsx", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
