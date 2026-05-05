from flask import Flask, render_template, jsonify, redirect, url_for, request, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from datetime import datetime, timedelta
from sqlalchemy import func
import pandas as pd
import io
import os

app = Flask(__name__)

# 🔧 Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///justdial_leads.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret123')

db = SQLAlchemy(app)

# 🔐 Login Setup
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
    product_query = db.Column(db.String(200))
    lead_source = db.Column(db.String(50), default="Justdial")
    status = db.Column(db.String(20), default="New")
    notes = db.Column(db.Text, default="")
    timestamp = db.Column(db.DateTime, default=datetime.now)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ================= INITIAL SETUP =================

with app.app_context():
    db.create_all()

    # Default admin user
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='123')
        db.session.add(admin)
        db.session.commit()


# ================= ROUTES =================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(
            username=request.form.get('username'),
            password=request.form.get('password')
        ).first()

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


# ================= DASHBOARD =================

@app.route('/')
@login_required
def index():

    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')

    query = Lead.query

    # 🔍 Search
    if search_query:
        query = query.filter(
            (Lead.customer_name.like(f'%{search_query}%')) |
            (Lead.phone.like(f'%{search_query}%')) |
            (Lead.product_query.like(f'%{search_query}%'))
        )

    # 🎯 Filter
    if status_filter:
        query = query.filter_by(status=status_filter)

    leads = query.order_by(Lead.id.desc()).all()

    # 📊 Stats
    total = Lead.query.count()
    pending = Lead.query.filter_by(status='New').count()
    won = Lead.query.filter_by(status='Converted').count()
    contacted = Lead.query.filter_by(status='Contacted').count()

    follow_up_needed = Lead.query.filter(
        Lead.status == 'New',
        Lead.timestamp < datetime.now() - timedelta(hours=24)
    ).count()

    conv_rate = round((won / total * 100), 1) if total > 0 else 0

    # 📊 REAL CHART DATA
    daily_counts = db.session.query(
        func.date(Lead.timestamp),
        func.count(Lead.id)
    ).group_by(func.date(Lead.timestamp)).all()

    daily_chart_data = []

    for i, row in enumerate(daily_counts):
        date = str(row[0])
        count = row[1]
        prev = daily_counts[i-1][1] if i > 0 else count

        daily_chart_data.append({
            "x": date,
            "o": prev,
            "h": max(prev, count) + 2,
            "l": min(prev, count) - 2,
            "c": count
        })

    return render_template('dashboard.html',
        leads=leads,
        total=total,
        pending=pending,
        won=won,
        contacted=contacted,
        conv_rate=conv_rate,
        follow_up_needed=follow_up_needed,
        daily_chart_data=daily_chart_data
    )


# ================= UPDATE STATUS =================

@app.route('/update-status/<int:id>/<string:new_status>')
@login_required
def update_status(id, new_status):
    lead = db.session.get(Lead, id)

    if lead:
        lead.status = new_status
        db.session.commit()
        flash(f'Status updated to {new_status}', 'success')

    return redirect(url_for('index'))


# ================= DELETE =================

@app.route('/delete-lead/<int:id>')
@login_required
def delete_lead(id):
    lead = db.session.get(Lead, id)

    if lead:
        db.session.delete(lead)
        db.session.commit()
        flash('Lead deleted', 'warning')

    return redirect(url_for('index'))


# ================= UPDATE NOTE =================

@app.route('/update-note/<int:id>', methods=['POST'])
@login_required
def update_note(id):
    data = request.get_json()
    lead = db.session.get(Lead, id)

    if lead:
        lead.notes = data.get('notes', '')
        db.session.commit()
        return jsonify({"status": "success"})

    return jsonify({"status": "error"}), 404


# ================= EXPORT =================

@app.route('/export-leads')
@login_required
def export_leads():
    leads = Lead.query.all()

    data = []
    for lead in leads:
        data.append({
            "Name": lead.customer_name,
            "Phone": lead.phone,
            "Service": lead.product_query,
            "Status": lead.status,
            "Notes": lead.notes,
            "Date": lead.timestamp.strftime('%d %b %Y')
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

    output.seek(0)

    return send_file(output,
        download_name="Leads.xlsx",
        as_attachment=True)


# ================= SYNC (DUMMY API) =================

@app.route('/api/sync-justdial')
@login_required
def sync():
    dummy_data = [
        {"name": "Rahul", "mobile": "9876543210", "query": "SEO"},
        {"name": "Priya", "mobile": "9123456789", "query": "Web Design"}
    ]

    for item in dummy_data:
        exists = Lead.query.filter_by(phone=item['mobile']).first()

        if not exists:
            new = Lead(
                customer_name=item['name'],
                phone=item['mobile'],
                product_query=item['query']
            )
            db.session.add(new)

    db.session.commit()
    flash("Leads Synced!", "success")

    return redirect('/')


# ================= RUN =================

if __name__ == '__main__':
    app.run(debug=True)