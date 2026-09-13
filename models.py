from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    members = db.relationship('FamilyMember', backref='user',
                              cascade='all, delete-orphan')

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class FamilyMember(db.Model):
    __tablename__ = 'family_members'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    relationship = db.Column(db.String(50))
    age = db.Column(db.Integer)

    medicines = db.relationship('Medicine', backref='member',
                                cascade='all, delete-orphan')


class Medicine(db.Model):
    __tablename__ = 'medicines'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('family_members.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    generic_name = db.Column(db.String(120))
    category = db.Column(db.String(80))
    dosage = db.Column(db.String(80))
    quantity = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(20), default='tablets')
    expiry_date = db.Column(db.Date)
    batch_number = db.Column(db.String(80))
    manufacturer = db.Column(db.String(120))
    daily_usage = db.Column(db.Float, default=1.0)
    minimum_stock = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    consumption = db.relationship('Consumption', backref='medicine',
                                  cascade='all, delete-orphan')
    predictions = db.relationship('Prediction', backref='medicine',
                                  cascade='all, delete-orphan')

    @property
    def days_to_expiry(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days

    @property
    def expiry_status(self):
        d = self.days_to_expiry
        if d is None:
            return 'UNKNOWN'
        if d < 0:
            return 'EXPIRED'
        if d <= 30:
            return 'EXPIRING SOON'
        return 'NORMAL'

    @property
    def stock_status(self):
        if self.quantity <= 0:
            return 'OUT OF STOCK'
        if self.quantity <= self.minimum_stock:
            return 'LOW STOCK'
        return 'NORMAL'


class Consumption(db.Model):
    __tablename__ = 'consumption'
    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicines.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    quantity_used = db.Column(db.Integer, nullable=False)


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicines.id'))
    type = db.Column(db.String(40))
    message = db.Column(db.String(255))
    status = db.Column(db.String(20), default='unread')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Prediction(db.Model):
    __tablename__ = 'predictions'
    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicines.id'), nullable=False)
    predicted_runout_date = db.Column(db.Date)
    recommended_reorder_date = db.Column(db.Date)
    predicted_daily_usage = db.Column(db.Float)
    model_name = db.Column(db.String(50))
    mae = db.Column(db.Float)
    r2 = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)