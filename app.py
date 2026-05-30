import os
import json
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, session, jsonify)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
# Fix CLOUDINARY_URL before importing the library — it auto-reads the env var
# at import time and crashes if the value is invalid
_raw_cld = os.environ.get('CLOUDINARY_URL', '')
if _raw_cld and not _raw_cld.startswith('cloudinary://'):
    # User may have pasted the full line "CLOUDINARY_URL=cloudinary://..."
    if '=' in _raw_cld:
        _raw_cld = _raw_cld.split('=', 1)[1].strip()
    if _raw_cld.startswith('cloudinary://'):
        os.environ['CLOUDINARY_URL'] = _raw_cld   # fixed
    else:
        del os.environ['CLOUDINARY_URL']           # remove bad value entirely
import cloudinary
import cloudinary.uploader
import cloudinary.api

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'autopow3r-s3cr3t-k3y-2024-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dealership.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

BUSINESS = {
    'name': 'AutoPower Dealership',
    'tagline': 'Drive Excellence. Power the Future.',
    'phone': '+233 50 356 9130',
    'email': 'kofi@chinacarsinghana.com',
    'address': 'Accra, Ghana',
    'republic_bank_url': '#',
    'whatsapp': '233503569130',
    'facebook': '#',
    'instagram': '#',
}

ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_VIDEOS = {'mp4', 'mov', 'avi', 'mkv', 'webm'}
ALLOWED_ALL = ALLOWED_IMAGES | ALLOWED_VIDEOS

# ── Email configuration ───────────────────────────────────────────────────── #
# Recipients who receive loan application notifications
LOAN_NOTIFY_EMAILS = [
    'sbonsu@republicghana.com',
    'kyeikofi@gmail.com',
]
# SMTP settings
SMTP_HOST     = 'smtp.gmail.com'
SMTP_PORT     = 587
SMTP_USER     = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')

# Cloudinary — persistent cloud storage for uploaded images/videos
USE_CLOUDINARY = False
try:
    _cld_url = os.environ.get('CLOUDINARY_URL', '').strip()
    # Strip the variable name if user accidentally pasted "CLOUDINARY_URL=cloudinary://..."
    if '=' in _cld_url and _cld_url.startswith('CLOUDINARY_URL'):
        _cld_url = _cld_url.split('=', 1)[1].strip()
    if _cld_url.startswith('cloudinary://'):
        cloudinary.config(cloudinary_url=_cld_url)
        USE_CLOUDINARY = True
    elif os.environ.get('CLOUDINARY_CLOUD_NAME'):
        cloudinary.config(
            cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', ''),
            api_key    = os.environ.get('CLOUDINARY_API_KEY', ''),
            api_secret = os.environ.get('CLOUDINARY_API_SECRET', ''),
        )
        USE_CLOUDINARY = True
    else:
        print('[CLOUDINARY] Not configured — using local file storage.')
except Exception as e:
    print(f'[CLOUDINARY] Config error: {e} — falling back to local storage.')


def send_loan_notification(app_obj):
    """Email loan application details to LOAN_NOTIFY_EMAILS."""
    if not SMTP_USER or not SMTP_PASSWORD:
        return
    try:
        rate         = get_ghs_rate()
        ptype        = (app_obj.product_type or '').title()
        pname        = app_obj.product_name or 'Not specified'
        p_usd        = f"${app_obj.product_price:,.2f}"  if app_obj.product_price else 'N/A'
        p_ghs        = f"GH₵ {app_obj.product_price * rate:,.2f}" if app_obj.product_price else 'N/A'
        l_usd        = f"${app_obj.loan_amount:,.2f}"    if app_obj.loan_amount    else 'N/A'
        l_ghs        = f"GH₵ {app_obj.loan_amount * rate:,.2f}"   if app_obj.loan_amount    else 'N/A'
        d_usd        = f"${app_obj.deposit_amount:,.2f}" if app_obj.deposit_amount else 'N/A'
        d_ghs        = f"GH₵ {app_obj.deposit_amount * rate:,.2f}" if app_obj.deposit_amount else 'N/A'
        income_str   = f"${app_obj.annual_income:,.2f} (GH₵ {app_obj.annual_income * rate:,.2f})" if app_obj.annual_income else 'N/A'

        body = f"""\
NEW LOAN APPLICATION — #{app_obj.id}
{'=' * 54}

  PRODUCT REQUESTED
  -----------------
  Type   : {ptype}
  Name   : {pname}
  Price  : {p_usd}  |  {p_ghs}

  LOAN DETAILS
  ------------
  Loan Amount : {l_usd}  |  {l_ghs}
  Deposit     : {d_usd}  |  {d_ghs}
  Loan Term   : {app_obj.loan_term or 'N/A'} months

  APPLICANT DETAILS
  -----------------
  Full Name     : {app_obj.first_name} {app_obj.last_name}
  Email         : {app_obj.email}
  Phone         : {app_obj.phone}
  Date of Birth : {app_obj.date_of_birth or 'N/A'}
  ID / Passport : {app_obj.id_number or 'N/A'}
  Address       : {app_obj.address or 'N/A'}

  EMPLOYMENT & INCOME
  -------------------
  Employment  : {app_obj.employment_status or 'N/A'}
  Employer    : {app_obj.employer or 'N/A'}
  Ann. Income : {income_str}

  ADDITIONAL NOTES
  ----------------
  {app_obj.message or 'None'}

{'=' * 54}
Submitted : {app_obj.created_at.strftime('%d %B %Y at %H:%M UTC')}
"""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[Loan #{app_obj.id}] {ptype}: {pname} — {app_obj.first_name} {app_obj.last_name}"
        msg['From']    = SMTP_USER
        msg['To']      = ', '.join(LOAN_NOTIFY_EMAILS)
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, LOAN_NOTIFY_EMAILS, msg.as_string())
    except Exception as e:
        print(f'[EMAIL] Failed to send loan notification: {e}')


db = SQLAlchemy(app)


# ─────────────────────────────── MODELS ─────────────────────────────────── #

class Vehicle(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    tagline       = db.Column(db.String(200))
    description   = db.Column(db.Text)
    price         = db.Column(db.Float, nullable=False, default=0)
    category      = db.Column(db.String(50))   # SUV, Sedan, Truck, Van, Pickup
    year          = db.Column(db.Integer)
    mileage       = db.Column(db.Integer)
    transmission  = db.Column(db.String(50))   # Automatic, Manual
    fuel_type     = db.Column(db.String(50))   # Petrol, Diesel, Electric, Hybrid
    engine        = db.Column(db.String(100))
    color         = db.Column(db.String(50))
    seats         = db.Column(db.Integer)
    features      = db.Column(db.Text, default='[]')
    images        = db.Column(db.Text, default='[]')
    videos        = db.Column(db.Text, default='[]')
    featured      = db.Column(db.Boolean, default=False)
    available     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def get_images(self):
        try: return json.loads(self.images or '[]')
        except: return []

    def get_videos(self):
        try: return json.loads(self.videos or '[]')
        except: return []

    def get_features(self):
        try: return json.loads(self.features or '[]')
        except: return []

    @property
    def cover(self):
        imgs = self.get_images()
        return imgs[0] if imgs else None


class SolarSystem(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(100), nullable=False)
    tagline          = db.Column(db.String(200))
    description      = db.Column(db.Text)
    price            = db.Column(db.Float, nullable=False, default=0)
    category         = db.Column(db.String(50))   # Residential, Commercial, Industrial
    power_output     = db.Column(db.String(50))
    panel_count      = db.Column(db.Integer)
    battery_capacity = db.Column(db.String(50))
    warranty         = db.Column(db.String(50))
    efficiency       = db.Column(db.String(50))
    features         = db.Column(db.Text, default='[]')
    images           = db.Column(db.Text, default='[]')
    videos           = db.Column(db.Text, default='[]')
    featured         = db.Column(db.Boolean, default=False)
    available        = db.Column(db.Boolean, default=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def get_images(self):
        try: return json.loads(self.images or '[]')
        except: return []

    def get_videos(self):
        try: return json.loads(self.videos or '[]')
        except: return []

    def get_features(self):
        try: return json.loads(self.features or '[]')
        except: return []

    @property
    def cover(self):
        imgs = self.get_images()
        return imgs[0] if imgs else None


class LoanApplication(db.Model):
    id                = db.Column(db.Integer, primary_key=True)
    first_name        = db.Column(db.String(50),  nullable=False)
    last_name         = db.Column(db.String(50),  nullable=False)
    email             = db.Column(db.String(100), nullable=False)
    phone             = db.Column(db.String(20),  nullable=False)
    date_of_birth     = db.Column(db.String(20))
    id_number         = db.Column(db.String(50))
    address           = db.Column(db.Text)
    product_type      = db.Column(db.String(20))   # vehicle | solar
    product_id        = db.Column(db.Integer)
    product_name      = db.Column(db.String(100))
    product_price     = db.Column(db.Float)
    loan_amount       = db.Column(db.Float)
    deposit_amount    = db.Column(db.Float)
    loan_term         = db.Column(db.Integer)       # months
    employment_status = db.Column(db.String(50))
    employer          = db.Column(db.String(100))
    annual_income     = db.Column(db.Float)
    message           = db.Column(db.Text)
    status            = db.Column(db.String(20), default='pending')
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)


class Contact(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(100), nullable=False)
    phone      = db.Column(db.String(20))
    subject    = db.Column(db.String(200))
    message    = db.Column(db.Text, nullable=False)
    status     = db.Column(db.String(20), default='unread')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CarOrder(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    order_type     = db.Column(db.String(20), nullable=False)  # 'order' | 'test_drive'
    vehicle_id     = db.Column(db.Integer, db.ForeignKey('vehicle.id'), nullable=True)
    vehicle        = db.relationship('Vehicle', backref='orders')
    name           = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(100), nullable=False)
    phone          = db.Column(db.String(20),  nullable=False)
    location       = db.Column(db.String(200))   # user's location / address
    latitude       = db.Column(db.Float)
    longitude      = db.Column(db.Float)
    preferred_date = db.Column(db.String(20))
    preferred_time = db.Column(db.String(20))
    notes          = db.Column(db.Text)
    status         = db.Column(db.String(20), default='pending')
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)


class AdminUser(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email         = db.Column(db.String(100))
    full_name     = db.Column(db.String(100))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Salesperson(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    full_name    = db.Column(db.String(100), nullable=False)
    email        = db.Column(db.String(100))
    phone        = db.Column(db.String(20))
    code         = db.Column(db.String(20), unique=True, nullable=False)  # unique referral/access code
    password_hash = db.Column(db.String(200), nullable=False)
    active       = db.Column(db.Boolean, default=True)
    commission_pct = db.Column(db.Float, default=2.0)  # commission percentage
    notes        = db.Column(db.Text)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    # stats (computed from linked applications/sales)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def total_sales(self):
        return SalespersonSale.query.filter_by(salesperson_id=self.id).count()

    def total_revenue(self):
        sales = SalespersonSale.query.filter_by(salesperson_id=self.id).all()
        return sum(s.sale_amount or 0 for s in sales)

    def commission_earned(self):
        return self.total_revenue() * (self.commission_pct / 100)


class SalespersonSale(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    salesperson_id   = db.Column(db.Integer, db.ForeignKey('salesperson.id'), nullable=False)
    salesperson      = db.relationship('Salesperson', backref='sales')
    product_type     = db.Column(db.String(20))   # vehicle | solar
    product_id       = db.Column(db.Integer)
    product_name     = db.Column(db.String(100))
    sale_amount      = db.Column(db.Float)
    customer_name    = db.Column(db.String(100))
    customer_email   = db.Column(db.String(100))
    customer_phone   = db.Column(db.String(20))
    loan_application_id = db.Column(db.Integer, db.ForeignKey('loan_application.id'), nullable=True)
    notes            = db.Column(db.Text)
    status           = db.Column(db.String(20), default='pending')  # pending, confirmed, cancelled
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)


class SiteSettings(db.Model):
    key   = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200), nullable=False)


# ───────────────────────────── HELPERS ──────────────────────────────────── #

USD_TO_GHS_DEFAULT = 15.5

def get_ghs_rate():
    """Read the live GHS rate from DB; fall back to default."""
    try:
        row = SiteSettings.query.get('usd_to_ghs_rate')
        return float(row.value) if row else USD_TO_GHS_DEFAULT
    except Exception:
        return USD_TO_GHS_DEFAULT

# Keep a module-level alias for the email helper (uses live rate each call)
USD_TO_GHS = USD_TO_GHS_DEFAULT

def usd_to_ghs(usd):
    if usd is None:
        return None
    return usd * get_ghs_rate()

app.jinja_env.globals['usd_to_ghs'] = usd_to_ghs

def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

def allowed(filename, kind='all'):
    e = _ext(filename)
    if kind == 'image': return e in ALLOWED_IMAGES
    if kind == 'video': return e in ALLOWED_VIDEOS
    return e in ALLOWED_ALL

def save_upload(file, subfolder):
    """Upload to Cloudinary when configured, otherwise save to local disk."""
    if USE_CLOUDINARY:
        resource_type = 'video' if _ext(file.filename) in ALLOWED_VIDEOS else 'image'
        result = cloudinary.uploader.upload(
            file,
            folder=f"dealership/{subfolder}",
            resource_type=resource_type,
        )
        # Store Cloudinary public_id prefixed with 'cld:' so we can delete it later
        return f"cld:{result['public_id']}|{result['secure_url']}"
    # Local fallback
    filename = secure_filename(file.filename)
    ext = _ext(filename)
    unique = f"{uuid.uuid4().hex}.{ext}"
    folder = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(folder, exist_ok=True)
    file.save(os.path.join(folder, unique))
    return f"uploads/{subfolder}/{unique}"


def media_url(path):
    """Return a URL for a stored media path (Cloudinary or local static)."""
    if path and path.startswith('cld:'):
        return path.split('|', 1)[1]   # Cloudinary secure_url
    return url_for('static', filename=path) if path else ''

app.jinja_env.globals['media_url'] = media_url


def _delete_media_file(path):
    """Delete a media file from Cloudinary or local disk."""
    if not path:
        return
    if path.startswith('cld:'):
        try:
            public_id = path.split('cld:', 1)[1].split('|')[0]
            cloudinary.uploader.destroy(public_id)
        except Exception:
            pass
    else:
        try:
            os.remove(os.path.join('static', path))
        except Exception:
            pass

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in to access the admin panel.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

@app.template_filter('currency')
def currency_filter(value):
    if value is None: return 'N/A'
    return f"${value:,.2f}"

@app.template_filter('ghs')
def ghs_filter(value):
    if value is None: return 'N/A'
    return f"GH₵ {value * get_ghs_rate():,.2f}"

@app.template_filter('comma')
def comma_filter(value):
    if value is None: return 'N/A'
    return f"{int(value):,}"

@app.context_processor
def inject_globals():
    try:
        unread         = Contact.query.filter_by(status='unread').count()
        pending        = LoanApplication.query.filter_by(status='pending').count()
        pending_orders = CarOrder.query.filter_by(status='pending').count()
    except Exception:
        unread         = 0
        pending        = 0
        pending_orders = 0
    return {
        'business':        BUSINESS,
        'current_year':    datetime.utcnow().year,
        'unread_contacts': unread,
        'pending_loans':   pending,
        'pending_orders':  pending_orders,
        'USD_TO_GHS':      get_ghs_rate(),
    }


# ────────────────────────── PUBLIC ROUTES ───────────────────────────────── #

@app.route('/')
def index():
    featured_vehicles = Vehicle.query.filter_by(featured=True, available=True).limit(4).all()
    featured_solar    = SolarSystem.query.filter_by(featured=True, available=True).limit(2).all()
    latest_vehicles   = Vehicle.query.filter_by(available=True).order_by(Vehicle.created_at.desc()).limit(6).all()
    latest_solar      = SolarSystem.query.filter_by(available=True).order_by(SolarSystem.created_at.desc()).limit(4).all()
    newest_vehicle    = Vehicle.query.filter_by(available=True).order_by(Vehicle.created_at.desc()).first()
    return render_template('index.html',
                           featured_vehicles=featured_vehicles,
                           featured_solar=featured_solar,
                           latest_vehicles=latest_vehicles,
                           latest_solar=latest_solar,
                           newest_vehicle=newest_vehicle)


@app.route('/vehicles')
def vehicles():
    category  = request.args.get('category', '')
    fuel_type = request.args.get('fuel', '')
    min_price = request.args.get('min', type=float)
    max_price = request.args.get('max', type=float)
    search    = request.args.get('q', '').strip()
    sort      = request.args.get('sort', 'newest')

    q = Vehicle.query.filter_by(available=True)
    if category:  q = q.filter_by(category=category)
    if fuel_type: q = q.filter_by(fuel_type=fuel_type)
    if min_price: q = q.filter(Vehicle.price >= min_price)
    if max_price: q = q.filter(Vehicle.price <= max_price)
    if search:    q = q.filter(Vehicle.name.ilike(f'%{search}%'))

    if sort == 'price_asc':  q = q.order_by(Vehicle.price.asc())
    elif sort == 'price_desc': q = q.order_by(Vehicle.price.desc())
    else: q = q.order_by(Vehicle.created_at.desc())

    vehicle_list = q.all()
    categories = [r[0] for r in db.session.query(Vehicle.category).distinct() if r[0]]
    fuels      = [r[0] for r in db.session.query(Vehicle.fuel_type).distinct() if r[0]]

    return render_template('vehicles.html',
                           vehicles=vehicle_list,
                           categories=categories,
                           fuels=fuels,
                           current_category=category,
                           current_fuel=fuel_type,
                           current_sort=sort,
                           search=search)


@app.route('/vehicles/<int:vid>')
def vehicle_detail(vid):
    vehicle = Vehicle.query.get_or_404(vid)
    related = Vehicle.query.filter(Vehicle.id != vid,
                                   Vehicle.available == True,
                                   Vehicle.category == vehicle.category).limit(4).all()
    return render_template('vehicle_detail.html', vehicle=vehicle, related=related)


@app.route('/solar')
def solar():
    category = request.args.get('category', '')
    q = SolarSystem.query.filter_by(available=True)
    if category: q = q.filter_by(category=category)
    solar_list = q.order_by(SolarSystem.created_at.desc()).all()
    categories = [r[0] for r in db.session.query(SolarSystem.category).distinct() if r[0]]
    return render_template('solar.html',
                           solar_systems=solar_list,
                           categories=categories,
                           current_category=category)


@app.route('/solar/<int:sid>')
def solar_detail(sid):
    solar   = SolarSystem.query.get_or_404(sid)
    related = SolarSystem.query.filter(SolarSystem.id != sid,
                                        SolarSystem.available == True).limit(4).all()
    return render_template('solar_detail.html', solar=solar, related=related)


@app.route('/loan', methods=['GET', 'POST'])
def loan():
    all_vehicles = Vehicle.query.filter_by(available=True).all()
    all_solar    = SolarSystem.query.filter_by(available=True).all()

    if request.method == 'POST':
        product_type  = request.form.get('product_type')
        product_name  = ''
        product_price = 0.0
        product_id    = None

        if product_type == 'vehicle':
            product_id = request.form.get('vehicle_id', type=int)
            if product_id:
                v = Vehicle.query.get(product_id)
                if v:
                    product_name  = f"{v.name}{' (' + str(v.year) + ')' if v.year else ''}"
                    product_price = v.price
        elif product_type == 'solar':
            product_id = request.form.get('solar_id', type=int)
            if product_id:
                s = SolarSystem.query.get(product_id)
                if s:
                    product_name  = s.name
                    product_price = s.price

        app_obj = LoanApplication(
            first_name        = request.form.get('first_name', '').strip(),
            last_name         = request.form.get('last_name', '').strip(),
            email             = request.form.get('email', '').strip(),
            phone             = request.form.get('phone', '').strip(),
            date_of_birth     = request.form.get('date_of_birth'),
            id_number         = request.form.get('id_number', '').strip(),
            address           = request.form.get('address', '').strip(),
            product_type      = product_type,
            product_id        = product_id,
            product_name      = product_name,
            product_price     = product_price,
            loan_amount       = request.form.get('loan_amount', type=float),
            deposit_amount    = request.form.get('deposit_amount', type=float),
            loan_term         = request.form.get('loan_term', type=int),
            employment_status = request.form.get('employment_status'),
            employer          = request.form.get('employer', '').strip(),
            annual_income     = request.form.get('annual_income', type=float),
            message           = request.form.get('message', '').strip(),
        )
        db.session.add(app_obj)
        db.session.commit()
        send_loan_notification(app_obj)
        flash('Your loan application has been submitted successfully! We will contact you within 24–48 hours.', 'success')
        return redirect(url_for('loan'))

    preselect_v    = request.args.get('vehicle', type=int)
    preselect_s    = request.args.get('solar', type=int)
    preselect_type = request.args.get('product_type', '')  # 'vehicle' or 'solar'
    if preselect_type == 'solar' and not preselect_s:
        preselect_s = -1  # flag to pre-check solar radio without a specific item
    return render_template('loan.html',
                           vehicles=all_vehicles,
                           solar_systems=all_solar,
                           preselect_vehicle=preselect_v,
                           preselect_solar=preselect_s)


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        c = Contact(
            name    = request.form.get('name', '').strip(),
            email   = request.form.get('email', '').strip(),
            phone   = request.form.get('phone', '').strip(),
            subject = request.form.get('subject', '').strip(),
            message = request.form.get('message', '').strip(),
        )
        db.session.add(c)
        db.session.commit()
        flash('Thank you! Your message has been sent. We will be in touch shortly.', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/order/<int:vid>', methods=['GET', 'POST'])
def order_vehicle(vid):
    vehicle = Vehicle.query.get_or_404(vid)
    if request.method == 'POST':
        order = CarOrder(
            order_type     = request.form.get('order_type', 'order'),
            vehicle_id     = vid,
            name           = request.form.get('name', '').strip(),
            email          = request.form.get('email', '').strip(),
            phone          = request.form.get('phone', '').strip(),
            location       = request.form.get('location', '').strip(),
            latitude       = request.form.get('latitude', type=float),
            longitude      = request.form.get('longitude', type=float),
            preferred_date = request.form.get('preferred_date'),
            preferred_time = request.form.get('preferred_time'),
            notes          = request.form.get('notes', '').strip(),
        )
        db.session.add(order)
        db.session.commit()
        order_type_label = 'test drive' if order.order_type == 'test_drive' else 'order'
        flash(f'Your {order_type_label} request for the {vehicle.name} has been submitted! We will contact you shortly.', 'success')
        return redirect(url_for('vehicle_detail', vid=vid))
    order_type = request.args.get('type', 'order')  # 'order' or 'test_drive'
    return render_template('order.html', vehicle=vehicle, order_type=order_type)


@app.route('/admin/orders')
@admin_required
def admin_orders():
    order_type = request.args.get('type', '')
    status     = request.args.get('status', '')
    q = CarOrder.query
    if order_type: q = q.filter_by(order_type=order_type)
    if status:     q = q.filter_by(status=status)
    orders = q.order_by(CarOrder.created_at.desc()).all()
    return render_template('admin/orders.html', orders=orders, current_type=order_type, current_status=status)


@app.route('/admin/orders/<int:oid>/status', methods=['POST'])
@admin_required
def admin_update_order_status(oid):
    order = CarOrder.query.get_or_404(oid)
    order.status = request.form.get('status', 'pending')
    db.session.commit()
    flash('Order status updated.', 'success')
    return redirect(url_for('admin_orders'))


# ────────────────────────── ADMIN ROUTES ────────────────────────────────── #

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if 'admin_id' in session:
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        user = AdminUser.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password', '')):
            session['admin_id']   = user.id
            session['admin_name'] = user.full_name or user.username
            return redirect(url_for('admin_dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template('admin/login.html')


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


@app.route('/admin')
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    stats = {
        'vehicles':     Vehicle.query.count(),
        'solar':        SolarSystem.query.count(),
        'applications': LoanApplication.query.count(),
        'pending':      LoanApplication.query.filter_by(status='pending').count(),
        'contacts':     Contact.query.filter_by(status='unread').count(),
        'approved':     LoanApplication.query.filter_by(status='approved').count(),
    }
    recent_apps      = LoanApplication.query.order_by(LoanApplication.created_at.desc()).limit(6).all()
    recent_contacts  = Contact.query.order_by(Contact.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html',
                           stats=stats,
                           recent_apps=recent_apps,
                           recent_contacts=recent_contacts)


# ── Vehicles ── #

@app.route('/admin/vehicles')
@admin_required
def admin_vehicles():
    vlist = Vehicle.query.order_by(Vehicle.created_at.desc()).all()
    return render_template('admin/vehicles.html', vehicles=vlist)


@app.route('/admin/vehicles/add', methods=['GET', 'POST'])
@admin_required
def admin_add_vehicle():
    if request.method == 'POST':
        feats = [f.strip() for f in request.form.get('features', '').splitlines() if f.strip()]
        v = Vehicle(
            name         = request.form.get('name'),
            tagline      = request.form.get('tagline'),
            description  = request.form.get('description'),
            price        = request.form.get('price', type=float) or 0,
            category     = request.form.get('category'),
            year         = request.form.get('year', type=int),
            mileage      = request.form.get('mileage', type=int),
            transmission = request.form.get('transmission'),
            fuel_type    = request.form.get('fuel_type'),
            engine       = request.form.get('engine'),
            color        = request.form.get('color'),
            seats        = request.form.get('seats', type=int),
            features     = json.dumps(feats),
            images       = '[]',
            videos       = '[]',
            featured     = 'featured' in request.form,
            available    = 'available' in request.form,
        )
        db.session.add(v)
        db.session.flush()

        imgs = []
        for f in request.files.getlist('images'):
            if f and f.filename and allowed(f.filename, 'image'):
                imgs.append(save_upload(f, 'vehicles'))
        v.images = json.dumps(imgs)

        vids = []
        for f in request.files.getlist('videos'):
            if f and f.filename and allowed(f.filename, 'video'):
                vids.append(save_upload(f, 'vehicles'))
        v.videos = json.dumps(vids)

        db.session.commit()
        flash(f'Vehicle "{v.name}" added successfully!', 'success')
        return redirect(url_for('admin_vehicles'))
    return render_template('admin/vehicle_form.html', vehicle=None, action='Add')


@app.route('/admin/vehicles/edit/<int:vid>', methods=['GET', 'POST'])
@admin_required
def admin_edit_vehicle(vid):
    v = Vehicle.query.get_or_404(vid)
    if request.method == 'POST':
        feats = [f.strip() for f in request.form.get('features', '').splitlines() if f.strip()]
        v.name         = request.form.get('name')
        v.tagline      = request.form.get('tagline')
        v.description  = request.form.get('description')
        v.price        = request.form.get('price', type=float) or 0
        v.category     = request.form.get('category')
        v.year         = request.form.get('year', type=int)
        v.mileage      = request.form.get('mileage', type=int)
        v.transmission = request.form.get('transmission')
        v.fuel_type    = request.form.get('fuel_type')
        v.engine       = request.form.get('engine')
        v.color        = request.form.get('color')
        v.seats        = request.form.get('seats', type=int)
        v.features     = json.dumps(feats)
        v.featured     = 'featured' in request.form
        v.available    = 'available' in request.form
        v.updated_at   = datetime.utcnow()

        existing_imgs = v.get_images()
        for f in request.files.getlist('images'):
            if f and f.filename and allowed(f.filename, 'image'):
                existing_imgs.append(save_upload(f, 'vehicles'))
        v.images = json.dumps(existing_imgs)

        existing_vids = v.get_videos()
        for f in request.files.getlist('videos'):
            if f and f.filename and allowed(f.filename, 'video'):
                existing_vids.append(save_upload(f, 'vehicles'))
        v.videos = json.dumps(existing_vids)

        db.session.commit()
        flash(f'Vehicle "{v.name}" updated successfully!', 'success')
        return redirect(url_for('admin_vehicles'))
    return render_template('admin/vehicle_form.html', vehicle=v, action='Edit')


@app.route('/admin/vehicles/delete/<int:vid>', methods=['POST'])
@admin_required
def admin_delete_vehicle(vid):
    v = Vehicle.query.get_or_404(vid)
    db.session.delete(v)
    db.session.commit()
    flash('Vehicle deleted.', 'success')
    return redirect(url_for('admin_vehicles'))


@app.route('/admin/vehicles/<int:vid>/delete-media', methods=['POST'])
@admin_required
def admin_delete_vehicle_media(vid):
    v    = Vehicle.query.get_or_404(vid)
    path = request.json.get('path')
    kind = request.json.get('kind', 'image')
    if kind == 'image':
        items = [i for i in v.get_images() if i != path]
        v.images = json.dumps(items)
    else:
        items = [i for i in v.get_videos() if i != path]
        v.videos = json.dumps(items)
    db.session.commit()
    _delete_media_file(path)
    return jsonify({'ok': True})


# ── Solar ── #

@app.route('/admin/solar')
@admin_required
def admin_solar():
    slist = SolarSystem.query.order_by(SolarSystem.created_at.desc()).all()
    return render_template('admin/solar.html', solar_systems=slist)


@app.route('/admin/solar/add', methods=['GET', 'POST'])
@admin_required
def admin_add_solar():
    if request.method == 'POST':
        feats = [f.strip() for f in request.form.get('features', '').splitlines() if f.strip()]
        s = SolarSystem(
            name             = request.form.get('name'),
            tagline          = request.form.get('tagline'),
            description      = request.form.get('description'),
            price            = request.form.get('price', type=float) or 0,
            category         = request.form.get('category'),
            power_output     = request.form.get('power_output'),
            panel_count      = request.form.get('panel_count', type=int),
            battery_capacity = request.form.get('battery_capacity'),
            warranty         = request.form.get('warranty'),
            efficiency       = request.form.get('efficiency'),
            features         = json.dumps(feats),
            images           = '[]',
            videos           = '[]',
            featured         = 'featured' in request.form,
            available        = 'available' in request.form,
        )
        db.session.add(s)
        db.session.flush()

        imgs = []
        for f in request.files.getlist('images'):
            if f and f.filename and allowed(f.filename, 'image'):
                imgs.append(save_upload(f, 'solar'))
        s.images = json.dumps(imgs)

        vids = []
        for f in request.files.getlist('videos'):
            if f and f.filename and allowed(f.filename, 'video'):
                vids.append(save_upload(f, 'solar'))
        s.videos = json.dumps(vids)

        db.session.commit()
        flash(f'Solar system "{s.name}" added successfully!', 'success')
        return redirect(url_for('admin_solar'))
    return render_template('admin/solar_form.html', solar=None, action='Add')


@app.route('/admin/solar/edit/<int:sid>', methods=['GET', 'POST'])
@admin_required
def admin_edit_solar(sid):
    s = SolarSystem.query.get_or_404(sid)
    if request.method == 'POST':
        feats = [f.strip() for f in request.form.get('features', '').splitlines() if f.strip()]
        s.name             = request.form.get('name')
        s.tagline          = request.form.get('tagline')
        s.description      = request.form.get('description')
        s.price            = request.form.get('price', type=float) or 0
        s.category         = request.form.get('category')
        s.power_output     = request.form.get('power_output')
        s.panel_count      = request.form.get('panel_count', type=int)
        s.battery_capacity = request.form.get('battery_capacity')
        s.warranty         = request.form.get('warranty')
        s.efficiency       = request.form.get('efficiency')
        s.features         = json.dumps(feats)
        s.featured         = 'featured' in request.form
        s.available        = 'available' in request.form
        s.updated_at       = datetime.utcnow()

        existing_imgs = s.get_images()
        for f in request.files.getlist('images'):
            if f and f.filename and allowed(f.filename, 'image'):
                existing_imgs.append(save_upload(f, 'solar'))
        s.images = json.dumps(existing_imgs)

        existing_vids = s.get_videos()
        for f in request.files.getlist('videos'):
            if f and f.filename and allowed(f.filename, 'video'):
                existing_vids.append(save_upload(f, 'solar'))
        s.videos = json.dumps(existing_vids)

        db.session.commit()
        flash(f'Solar system "{s.name}" updated successfully!', 'success')
        return redirect(url_for('admin_solar'))
    return render_template('admin/solar_form.html', solar=s, action='Edit')


@app.route('/admin/solar/delete/<int:sid>', methods=['POST'])
@admin_required
def admin_delete_solar(sid):
    s = SolarSystem.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    flash('Solar system deleted.', 'success')
    return redirect(url_for('admin_solar'))


@app.route('/admin/solar/<int:sid>/delete-media', methods=['POST'])
@admin_required
def admin_delete_solar_media(sid):
    s    = SolarSystem.query.get_or_404(sid)
    path = request.json.get('path')
    kind = request.json.get('kind', 'image')
    if kind == 'image':
        items = [i for i in s.get_images() if i != path]
        s.images = json.dumps(items)
    else:
        items = [i for i in s.get_videos() if i != path]
        s.videos = json.dumps(items)
    db.session.commit()
    _delete_media_file(path)
    return jsonify({'ok': True})


# ── Applications & Contacts ── #

@app.route('/admin/applications')
@admin_required
def admin_applications():
    status = request.args.get('status', '')
    q = LoanApplication.query
    if status: q = q.filter_by(status=status)
    apps = q.order_by(LoanApplication.created_at.desc()).all()
    return render_template('admin/applications.html', applications=apps, current_status=status)


@app.route('/admin/applications/<int:aid>/status', methods=['POST'])
@admin_required
def admin_update_app_status(aid):
    a = LoanApplication.query.get_or_404(aid)
    a.status = request.form.get('status', 'pending')
    db.session.commit()
    flash(f'Application status updated to "{a.status}".', 'success')
    return redirect(url_for('admin_applications'))


@app.route('/admin/applications/<int:aid>')
@admin_required
def admin_view_application(aid):
    a = LoanApplication.query.get_or_404(aid)
    return render_template('admin/application_detail.html', app=a)


@app.route('/admin/contacts')
@admin_required
def admin_contacts():
    contacts = Contact.query.order_by(Contact.created_at.desc()).all()
    Contact.query.filter_by(status='unread').update({'status': 'read'})
    db.session.commit()
    return render_template('admin/contacts.html', contacts=contacts)


@app.route('/admin/contacts/delete/<int:cid>', methods=['POST'])
@admin_required
def admin_delete_contact(cid):
    c = Contact.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    flash('Message deleted.', 'success')
    return redirect(url_for('admin_contacts'))


# ── Salesperson Management ── #

@app.route('/admin/salespersons')
@admin_required
def admin_salespersons():
    people = Salesperson.query.order_by(Salesperson.created_at.desc()).all()
    return render_template('admin/salespersons.html', salespersons=people)


@app.route('/admin/salespersons/add', methods=['GET', 'POST'])
@admin_required
def admin_add_salesperson():
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        if Salesperson.query.filter_by(code=code).first():
            flash('That code is already taken. Choose a unique code.', 'error')
            return redirect(url_for('admin_add_salesperson'))
        sp = Salesperson(
            full_name      = request.form.get('full_name', '').strip(),
            email          = request.form.get('email', '').strip(),
            phone          = request.form.get('phone', '').strip(),
            code           = code,
            commission_pct = request.form.get('commission_pct', type=float) or 2.0,
            notes          = request.form.get('notes', '').strip(),
            active         = 'active' in request.form,
        )
        sp.set_password(request.form.get('password', ''))
        db.session.add(sp)
        db.session.commit()
        flash(f'Salesperson "{sp.full_name}" added with code {sp.code}.', 'success')
        return redirect(url_for('admin_salespersons'))
    return render_template('admin/salesperson_form.html', sp=None, action='Add')


@app.route('/admin/salespersons/edit/<int:sid>', methods=['GET', 'POST'])
@admin_required
def admin_edit_salesperson(sid):
    sp = Salesperson.query.get_or_404(sid)
    if request.method == 'POST':
        new_code = request.form.get('code', '').strip().upper()
        existing = Salesperson.query.filter_by(code=new_code).first()
        if existing and existing.id != sp.id:
            flash('That code is already taken.', 'error')
            return redirect(url_for('admin_edit_salesperson', sid=sid))
        sp.full_name      = request.form.get('full_name', '').strip()
        sp.email          = request.form.get('email', '').strip()
        sp.phone          = request.form.get('phone', '').strip()
        sp.code           = new_code
        sp.commission_pct = request.form.get('commission_pct', type=float) or 2.0
        sp.notes          = request.form.get('notes', '').strip()
        sp.active         = 'active' in request.form
        new_pw = request.form.get('new_password', '').strip()
        if new_pw:
            sp.set_password(new_pw)
        db.session.commit()
        flash('Salesperson updated.', 'success')
        return redirect(url_for('admin_salespersons'))
    return render_template('admin/salesperson_form.html', sp=sp, action='Edit')


@app.route('/admin/salespersons/delete/<int:sid>', methods=['POST'])
@admin_required
def admin_delete_salesperson(sid):
    sp = Salesperson.query.get_or_404(sid)
    db.session.delete(sp)
    db.session.commit()
    flash('Salesperson removed.', 'success')
    return redirect(url_for('admin_salespersons'))


@app.route('/admin/salespersons/<int:sid>/sales')
@admin_required
def admin_salesperson_sales(sid):
    sp    = Salesperson.query.get_or_404(sid)
    sales = SalespersonSale.query.filter_by(salesperson_id=sid).order_by(SalespersonSale.created_at.desc()).all()
    return render_template('admin/salesperson_sales.html', sp=sp, sales=sales)


@app.route('/admin/salespersons/<int:sid>/sales/add', methods=['GET', 'POST'])
@admin_required
def admin_add_sale(sid):
    sp = Salesperson.query.get_or_404(sid)
    if request.method == 'POST':
        sale = SalespersonSale(
            salesperson_id   = sid,
            product_type     = request.form.get('product_type'),
            product_id       = request.form.get('product_id', type=int),
            product_name     = request.form.get('product_name', '').strip(),
            sale_amount      = request.form.get('sale_amount', type=float),
            customer_name    = request.form.get('customer_name', '').strip(),
            customer_email   = request.form.get('customer_email', '').strip(),
            customer_phone   = request.form.get('customer_phone', '').strip(),
            notes            = request.form.get('notes', '').strip(),
            status           = request.form.get('status', 'pending'),
        )
        db.session.add(sale)
        db.session.commit()
        flash('Sale recorded.', 'success')
        return redirect(url_for('admin_salesperson_sales', sid=sid))
    vehicles    = Vehicle.query.filter_by(available=True).all()
    solar_list  = SolarSystem.query.filter_by(available=True).all()
    return render_template('admin/add_sale.html', sp=sp, vehicles=vehicles, solar_systems=solar_list)


@app.route('/admin/sales/<int:sale_id>/status', methods=['POST'])
@admin_required
def admin_update_sale_status(sale_id):
    sale = SalespersonSale.query.get_or_404(sale_id)
    sale.status = request.form.get('status', 'pending')
    db.session.commit()
    flash('Sale status updated.', 'success')
    return redirect(url_for('admin_salesperson_sales', sid=sale.salesperson_id))


# ── Salesperson Portal (their own login) ── #

@app.route('/sales/login', methods=['GET', 'POST'])
def sales_login():
    if 'sales_id' in session:
        return redirect(url_for('sales_portal'))
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        pw   = request.form.get('password', '')
        sp   = Salesperson.query.filter_by(code=code, active=True).first()
        if sp and sp.check_password(pw):
            session['sales_id']   = sp.id
            session['sales_name'] = sp.full_name
            session['sales_code'] = sp.code
            return redirect(url_for('sales_portal'))
        flash('Invalid code or password.', 'error')
    return render_template('sales/login.html')


@app.route('/sales/logout')
def sales_logout():
    session.pop('sales_id', None)
    session.pop('sales_name', None)
    session.pop('sales_code', None)
    return redirect(url_for('sales_login'))


def sales_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'sales_id' not in session:
            return redirect(url_for('sales_login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/sales')
@app.route('/sales/portal')
@sales_required
def sales_portal():
    sp     = Salesperson.query.get_or_404(session['sales_id'])
    sales  = SalespersonSale.query.filter_by(salesperson_id=sp.id).order_by(SalespersonSale.created_at.desc()).limit(10).all()
    return render_template('sales/portal.html', sp=sp, recent_sales=sales)


@app.route('/sales/inventory')
@sales_required
def sales_inventory():
    vehicles    = Vehicle.query.filter_by(available=True).all()
    solar_list  = SolarSystem.query.filter_by(available=True).all()
    return render_template('sales/inventory.html', vehicles=vehicles, solar_systems=solar_list)


@app.route('/sales/submit', methods=['GET', 'POST'])
@sales_required
def sales_submit_lead():
    sp = Salesperson.query.get_or_404(session['sales_id'])
    vehicles   = Vehicle.query.filter_by(available=True).all()
    solar_list = SolarSystem.query.filter_by(available=True).all()
    if request.method == 'POST':
        product_type = request.form.get('product_type')
        product_id   = request.form.get('product_id', type=int)
        product_name = request.form.get('product_name', '').strip()
        sale_amount  = request.form.get('sale_amount', type=float)

        # Also create a loan application if customer needs financing
        if request.form.get('needs_loan') == '1':
            loan_app = LoanApplication(
                first_name        = request.form.get('customer_name', '').split()[0] if request.form.get('customer_name') else '',
                last_name         = ' '.join(request.form.get('customer_name', '').split()[1:]) or '',
                email             = request.form.get('customer_email', '').strip(),
                phone             = request.form.get('customer_phone', '').strip(),
                product_type      = product_type,
                product_id        = product_id,
                product_name      = product_name,
                product_price     = sale_amount,
                loan_amount       = sale_amount,
                message           = f'Lead submitted by salesperson {sp.full_name} (Code: {sp.code})',
            )
            db.session.add(loan_app)
            db.session.flush()
            loan_id = loan_app.id
        else:
            loan_id = None

        sale = SalespersonSale(
            salesperson_id      = sp.id,
            product_type        = product_type,
            product_id          = product_id,
            product_name        = product_name,
            sale_amount         = sale_amount,
            customer_name       = request.form.get('customer_name', '').strip(),
            customer_email      = request.form.get('customer_email', '').strip(),
            customer_phone      = request.form.get('customer_phone', '').strip(),
            loan_application_id = loan_id,
            notes               = request.form.get('notes', '').strip(),
            status              = 'pending',
        )
        db.session.add(sale)
        db.session.commit()
        flash('Lead submitted successfully! The admin will review it shortly.', 'success')
        return redirect(url_for('sales_portal'))
    return render_template('sales/submit_lead.html', sp=sp, vehicles=vehicles, solar_systems=solar_list)


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    admin = AdminUser.query.get(session['admin_id'])
    if request.method == 'POST':
        admin.full_name = request.form.get('full_name', '').strip()
        admin.email     = request.form.get('email', '').strip()
        new_pw          = request.form.get('new_password', '').strip()
        if new_pw:
            if admin.check_password(request.form.get('current_password', '')):
                admin.set_password(new_pw)
                flash('Password updated.', 'success')
            else:
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('admin_settings'))
        # Save GHS rate
        rate_str = request.form.get('ghs_rate', '').strip()
        try:
            rate_val = float(rate_str)
            if rate_val > 0:
                row = SiteSettings.query.get('usd_to_ghs_rate')
                if row:
                    row.value = str(rate_val)
                else:
                    db.session.add(SiteSettings(key='usd_to_ghs_rate', value=str(rate_val)))
        except (ValueError, TypeError):
            pass
        db.session.commit()
        session['admin_name'] = admin.full_name or admin.username
        flash('Settings saved successfully.', 'success')
    current_rate = get_ghs_rate()
    return render_template('admin/settings.html', admin=admin, current_rate=current_rate)


# ─────────────────────────── INIT ───────────────────────────────────────── #

def init_db():
    try:
        with app.app_context():
            db.create_all()
            if not AdminUser.query.first():
                a = AdminUser(username='admin', full_name='Administrator', email='admin@autopowerdealership.com')
                a.set_password('admin123')
                db.session.add(a)
                db.session.commit()
                print("\n[OK] Default admin created")
                print("   Username : admin")
                print("   Password : admin123")
            print("   WARNING  : Change this password after first login!\n")
        for folder in ('vehicles', 'solar'):
            os.makedirs(os.path.join('static', 'uploads', folder), exist_ok=True)
    except Exception as e:
        print(f"[INIT] DB init warning: {e}")


# Initialise DB on every startup (works with gunicorn / Render too)
try:
    init_db()
except Exception as _e:
    print(f"[INIT] Startup warning: {_e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("[START] AutoPower Dealership is running at http://localhost:5000")
    print("[ADMIN] Admin panel at http://localhost:5000/admin")
    print("[SALES] Sales portal at http://localhost:5000/sales/login\n")
    app.run(debug=False, host='0.0.0.0', port=port)
