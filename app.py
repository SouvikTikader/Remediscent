import os
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
from flask import (Flask, render_template, redirect, url_for, request,
                   flash, jsonify, abort)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)

from models import (db, User, FamilyMember, Medicine, Consumption,
                    Notification, Prediction, DrugInteraction,
                    Allergy, AdherenceSnapshot)
from ml_predictor import predict_reorder
from safety_engine import check_member_interactions, check_allergies
from analytics_engine import detect_anomalies, compute_adherence, optimize_refills
from seed_interactions import seed_interactions

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-change-me')

    db_url = os.environ.get('DATABASE_URL', 'sqlite:///remediscent.db')
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager = LoginManager()
    login_manager.login_view = 'login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    with app.app_context():
        db.create_all()
        seed_interactions()

    register_routes(app)
    register_cli(app)
    return app


def register_routes(app):

    # ---------- AUTH ----------
    @app.route('/')
    def index():
        return redirect(url_for('dashboard' if current_user.is_authenticated else 'login'))

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            pw = request.form.get('password', '')
            if not (name and email and pw):
                flash('All fields required', 'error')
                return render_template('register.html')
            if User.query.filter_by(email=email).first():
                flash('Email already registered', 'error')
                return render_template('register.html')
            u = User(name=name, email=email)
            u.set_password(pw)
            db.session.add(u)
            db.session.flush()
            db.session.add(FamilyMember(user_id=u.id, name=name, relationship='Self'))
            db.session.commit()
            flash('Account created. Please log in.', 'success')
            return redirect(url_for('login'))
        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            pw = request.form.get('password', '')
            u = User.query.filter_by(email=email).first()
            if u and u.check_password(pw):
                login_user(u)
                return redirect(url_for('dashboard'))
            flash('Invalid credentials', 'error')
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    # ---------- DASHBOARD ----------
    @app.route('/dashboard')
    @login_required
    def dashboard():
        members = FamilyMember.query.filter_by(user_id=current_user.id).all()
        member_ids = [m.id for m in members]
        meds = Medicine.query.filter(Medicine.member_id.in_(member_ids)).all() if member_ids else []

        stats = {
            'total': len(meds),
            'expiring_soon': sum(1 for m in meds if m.expiry_status == 'EXPIRING SOON'),
            'expired': sum(1 for m in meds if m.expiry_status == 'EXPIRED'),
            'low_stock': sum(1 for m in meds if m.stock_status in ('LOW STOCK', 'OUT OF STOCK')),
        }

        # Safety findings across all members
        safety_findings = []
        for m in members:
            findings = check_member_interactions(m.id)
            for f in findings:
                f['member'] = m.name
                safety_findings.append(f)

        # Refill plan
        refill = optimize_refills(meds)

        # Adherence summary (top 5 worst)
        adherence_rows = []
        for med in meds:
            records = Consumption.query.filter_by(medicine_id=med.id).all()
            a = compute_adherence(med, records)
            if a['rate'] is not None:
                adherence_rows.append({
                    'medicine': med.name,
                    'member': med.member.name,
                    'rate': a['rate'],
                    'label': a['label'],
                })
        adherence_rows.sort(key=lambda x: x['rate'])
        adherence_rows = adherence_rows[:5]

        notes = (Notification.query
                 .filter_by(user_id=current_user.id, status='unread')
                 .order_by(Notification.created_at.desc()).limit(8).all())

        return render_template('dashboard.html',
                               medicines=meds, stats=stats, notifications=notes,
                               safety_findings=safety_findings[:5],
                               refill=refill,
                               adherence_rows=adherence_rows)

    # ---------- MEMBERS ----------
    @app.route('/members', methods=['GET', 'POST'])
    @login_required
    def members():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if name:
                db.session.add(FamilyMember(
                    user_id=current_user.id, name=name,
                    relationship=request.form.get('relationship', '').strip(),
                    age=request.form.get('age', type=int)))
                db.session.commit()
                flash('Member added', 'success')
            return redirect(url_for('members'))
        return render_template('members.html',
                               members=FamilyMember.query.filter_by(user_id=current_user.id).all())

    @app.route('/members/<int:mid>/delete', methods=['POST'])
    @login_required
    def delete_member(mid):
        m = FamilyMember.query.get_or_404(mid)
        if m.user_id != current_user.id:
            abort(403)
        db.session.delete(m)
        db.session.commit()
        return redirect(url_for('members'))

    # ---------- ALLERGIES ----------
    @app.route('/members/<int:mid>/allergies', methods=['GET', 'POST'])
    @login_required
    def member_allergies(mid):
        m = FamilyMember.query.get_or_404(mid)
        if m.user_id != current_user.id:
            abort(403)
        if request.method == 'POST':
            allergen = request.form.get('allergen', '').strip().lower()
            if allergen:
                db.session.add(Allergy(
                    member_id=m.id, allergen=allergen,
                    severity=request.form.get('severity', 'MODERATE'),
                    notes=request.form.get('notes', '').strip()))
                db.session.commit()
                flash('Allergy recorded', 'success')
            return redirect(url_for('member_allergies', mid=m.id))
        return render_template('allergies.html', member=m, allergies=m.allergies)

    @app.route('/allergies/<int:aid>/delete', methods=['POST'])
    @login_required
    def delete_allergy(aid):
        a = Allergy.query.get_or_404(aid)
        if a.member.user_id != current_user.id:
            abort(403)
        mid = a.member_id
        db.session.delete(a)
        db.session.commit()
        return redirect(url_for('member_allergies', mid=mid))

    # ---------- MEDICINES ----------
    @app.route('/medicines')
    @login_required
    def medicines():
        ids = [m.id for m in FamilyMember.query.filter_by(user_id=current_user.id).all()]
        meds = []
        if ids:
            meds = (Medicine.query.filter(Medicine.member_id.in_(ids))
                    .order_by(Medicine.expiry_date.is_(None),
                              Medicine.expiry_date.asc()).all())
        return render_template('medicines.html', medicines=meds)

    @app.route('/medicines/add', methods=['GET', 'POST'])
    @login_required
    def add_medicine():
        members = FamilyMember.query.filter_by(user_id=current_user.id).all()
        if request.method == 'POST':
            try:
                expiry = datetime.strptime(request.form['expiry_date'], '%Y-%m-%d').date() \
                    if request.form.get('expiry_date') else None
            except ValueError:
                expiry = None

            member_id = request.form.get('member_id', type=int)
            if not member_id:
                flash('Select a family member', 'error')
                return render_template('add_medicine.html', members=members)

            med = Medicine(
                member_id=member_id,
                name=request.form.get('name', '').strip(),
                generic_name=request.form.get('generic_name', '').strip(),
                category=request.form.get('category', '').strip(),
                dosage=request.form.get('dosage', '').strip(),
                quantity=request.form.get('quantity', type=int) or 0,
                unit=request.form.get('unit', 'tablets'),
                expiry_date=expiry,
                batch_number=request.form.get('batch_number', '').strip(),
                manufacturer=request.form.get('manufacturer', '').strip(),
                daily_usage=request.form.get('daily_usage', type=float) or 1.0,
                minimum_stock=request.form.get('minimum_stock', type=int) or 5,
            )
            db.session.add(med)
            db.session.flush()

            # Immediate allergy check
            hits = check_allergies(member_id, med)
            if hits:
                db.session.add(Notification(
                    user_id=current_user.id, medicine_id=med.id,
                    type='ALLERGY',
                    message=f"⚠ {med.name} may trigger allergy: "
                            f"{', '.join(h['allergen'] for h in hits)}"))

            db.session.commit()
            flash(f'{med.name} added', 'success')
            return redirect(url_for('medicine_detail', mid=med.id))
        return render_template('add_medicine.html', members=members)

    @app.route('/medicines/<int:mid>')
    @login_required
    def medicine_detail(mid):
        med = Medicine.query.get_or_404(mid)
        if med.member.user_id != current_user.id:
            abort(403)
        records = Consumption.query.filter_by(medicine_id=med.id).all()
        adherence = compute_adherence(med, records)
        anomalies = detect_anomalies(records)
        allergies = check_allergies(med.member_id, med)
        interactions = check_member_interactions(med.member_id)
        # Filter interactions that involve this medicine
        relevant = [i for i in interactions
                    if med.name.lower() in (i['a'].lower(), i['b'].lower())]
        return render_template('medicine_detail.html',
                               med=med, adherence=adherence,
                               anomalies=anomalies, allergies=allergies,
                               interactions=relevant)

    @app.route('/medicines/<int:mid>/delete', methods=['POST'])
    @login_required
    def delete_medicine(mid):
        med = Medicine.query.get_or_404(mid)
        if med.member.user_id != current_user.id:
            abort(403)
        db.session.delete(med)
        db.session.commit()
        flash('Medicine deleted', 'success')
        return redirect(url_for('medicines'))

    @app.route('/medicines/<int:mid>/consume', methods=['POST'])
    @login_required
    def consume_medicine(mid):
        med = Medicine.query.get_or_404(mid)
        if med.member.user_id != current_user.id:
            abort(403)
        qty = request.form.get('quantity', type=int) or 1
        db.session.add(Consumption(medicine_id=med.id, date=date.today(),
                                   quantity_used=qty))
        med.quantity = max(0, med.quantity - qty)
        db.session.commit()
        flash(f'Recorded {qty} {med.unit} of {med.name}', 'success')
        return redirect(request.referrer or url_for('medicines'))

    # ---------- PREDICTION ----------
    @app.route('/medicines/<int:mid>/predict', methods=['POST'])
    @login_required
    def predict(mid):
        med = Medicine.query.get_or_404(mid)
        if med.member.user_id != current_user.id:
            abort(403)
        records = Consumption.query.filter_by(medicine_id=med.id).all()
        r = predict_reorder(records, med.quantity, med.minimum_stock)

        db.session.add(Prediction(
            medicine_id=med.id,
            predicted_runout_date=r['runout_date'],
            recommended_reorder_date=r['reorder_date'],
            predicted_daily_usage=r['avg_daily_usage'],
            model_name=r['model'], mae=r['mae'], r2=r['r2']))

        if r['reorder_date'] and r['reorder_date'] <= date.today() + timedelta(days=7):
            db.session.add(Notification(
                user_id=current_user.id, medicine_id=med.id, type='REORDER',
                message=f"{med.name}: reorder recommended by {r['reorder_date']}"))
        db.session.commit()

        if r['runout_date']:
            flash(f"[{r['model']}] Avg {r['avg_daily_usage']}/day · "
                  f"Run-out {r['runout_date']} · Reorder {r['reorder_date']}", 'success')
        else:
            flash('Not enough consumption history.', 'error')
        return redirect(request.referrer or url_for('medicines'))

    # ---------- VOICE ENTRY ----------
    @app.route('/voice-add')
    @login_required
    def voice_add():
        members = FamilyMember.query.filter_by(user_id=current_user.id).all()
        return render_template('voice_add.html', members=members)

    # ---------- NOTIFICATIONS ----------
    @app.route('/notifications')
    @login_required
    def notifications():
        notes = (Notification.query.filter_by(user_id=current_user.id)
                 .order_by(Notification.created_at.desc()).all())
        return render_template('notifications.html', notifications=notes)

    @app.route('/notifications/<int:nid>/read', methods=['POST'])
    @login_required
    def mark_read(nid):
        n = Notification.query.get_or_404(nid)
        if n.user_id != current_user.id:
            abort(403)
        n.status = 'read'
        db.session.commit()
        return redirect(url_for('notifications'))

    # ---------- API ----------
    @app.route('/api/predict/<int:mid>')
    @login_required
    def api_predict(mid):
        med = Medicine.query.get_or_404(mid)
        if med.member.user_id != current_user.id:
            return jsonify({'error': 'forbidden'}), 403
        records = Consumption.query.filter_by(medicine_id=med.id).all()
        r = predict_reorder(records, med.quantity, med.minimum_stock)
        for k in ('runout_date', 'reorder_date'):
            if r.get(k):
                r[k] = r[k].isoformat()
        return jsonify(r)

    @app.route('/api/interactions/<int:mid>')
    @login_required
    def api_interactions(mid):
        m = FamilyMember.query.get_or_404(mid)
        if m.user_id != current_user.id:
            return jsonify({'error': 'forbidden'}), 403
        return jsonify(check_member_interactions(mid))

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'})


def register_cli(app):
    @app.cli.command('seed-demo')
    def seed_demo():
        """Create demo@remediscent.app / demo1234 with sample data."""
        import random
        if User.query.filter_by(email='demo@remediscent.app').first():
            print('Demo user exists.')
            return
        u = User(name='Demo User', email='demo@remediscent.app')
        u.set_password('demo1234')
        db.session.add(u)
        db.session.flush()

        me = FamilyMember(user_id=u.id, name='Demo User', relationship='Self', age=30)
        dad = FamilyMember(user_id=u.id, name='Father', relationship='Father', age=62)
        db.session.add_all([me, dad])
        db.session.flush()

        # Allergies
        db.session.add(Allergy(member_id=dad.id, allergen='aspirin',
                               severity='HIGH', notes='GI bleeding history'))

        # Medicines designed to trigger interactions
        m1 = Medicine(member_id=dad.id, name='Warfarin', generic_name='warfarin',
                      category='Anticoagulant', dosage='5mg', quantity=20,
                      unit='tablets', expiry_date=date.today() + timedelta(days=12),
                      daily_usage=1.0, minimum_stock=5)
        m2 = Medicine(member_id=dad.id, name='Aspirin', generic_name='aspirin',
                      category='Pain Relief', dosage='75mg', quantity=30,
                      unit='tablets', expiry_date=date.today() + timedelta(days=200),
                      daily_usage=1.0, minimum_stock=10)
        m3 = Medicine(member_id=me.id, name='Paracetamol', generic_name='paracetamol',
                      category='Pain Relief', dosage='500mg', quantity=3,
                      unit='tablets', expiry_date=date.today() - timedelta(days=2),
                      daily_usage=2.0, minimum_stock=10)
        db.session.add_all([m1, m2, m3])
        db.session.flush()

        # 30 days of consumption with a deliberate anomaly spike
        for med, base in [(m1, 1.0), (m2, 1.0), (m3, 0.5)]:
            for i in range(30, 0, -1):
                if random.random() < 0.85:
                    qty = max(1, int(round(base + random.uniform(-0.3, 0.4))))
                    if med.id == m3.id and i == 5:  # anomaly
                        qty = 8
                    db.session.add(Consumption(
                        medicine_id=med.id,
                        date=date.today() - timedelta(days=i),
                        quantity_used=qty))
        db.session.commit()
        print(' Demo data created. Login: demo@remediscent.app / demo1234')


app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port,
            debug=os.environ.get('FLASK_DEBUG', '0') == '1')