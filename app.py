from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import desc, or_
from datetime import datetime, timedelta
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
import os
import io
import csv
import json
import re
from functools import wraps
from flask import session

# Import messaging utilities
try:
    from utils.messaging import send_sms, send_whatsapp, send_invoice_notification, format_template
except ImportError:
    print("⚠️ Messaging utilities not found. SMS/WhatsApp features will be limited.")
    def send_sms(*args, **kwargs):
        return {"success": False, "error": "Messaging module not available"}
    def send_whatsapp(*args, **kwargs):
        return {"success": False, "error": "Messaging module not available"}
    def send_invoice_notification(*args, **kwargs):
        return {"sms": {"success": False}, "whatsapp": {"success": False}}
    def format_template(*args, **kwargs):
        return ""

# ------------------------------------------------------------
# Flask configuration
# ------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "crusher-secret")
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # 8 hour session timeout

RUNNING_ON_VERCEL = os.getenv("VERCEL", "0") == "1"
if RUNNING_ON_VERCEL:
    sqlite_path = "/tmp/data.db"
else:
    sqlite_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{sqlite_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ------------------------------------------------------------
# Tamil font registration for PDF outputs
# ------------------------------------------------------------
FONT_PATH = os.path.join("static", "fonts", "NotoSansTamil-Regular.ttf")
if os.path.exists(FONT_PATH):
    try:
        pdfmetrics.registerFont(TTFont("TamilFont", FONT_PATH))
        print("✅ Tamil font registered successfully")
    except Exception as err:
        print("⚠️ Tamil font registration failed:", err)
else:
    print("⚠️ Tamil font missing at static/fonts/NotoSansTamil-Regular.ttf")

# ------------------------------------------------------------
# Login manager setup
# ------------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ------------------------------------------------------------
# Database models
# ------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)
    name = db.Column(db.String(200), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="user")  # user, staff, admin
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    status = db.Column(db.String(20), default="active")  # active, inactive
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer", foreign_keys=[customer_id])

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
    
    def is_active_user(self):
        return self.status == "active"


class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    gst_number = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    invoices = db.relationship("Invoice", back_populates="customer")


class Vehicle(db.Model):
    __tablename__ = "vehicles"
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(50), unique=True, nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    invoices = db.relationship("Invoice", back_populates="vehicle")


class Item(db.Model):
    __tablename__ = "items"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    rate = db.Column(db.Float, nullable=False, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Invoice(db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)
    bill_no = db.Column(db.String(50), unique=True, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True)
    subtotal = db.Column(db.Float, nullable=False, default=0.0)
    cgst = db.Column(db.Float, nullable=False, default=0.0)
    sgst = db.Column(db.Float, nullable=False, default=0.0)
    grand_total = db.Column(db.Float, nullable=False, default=0.0)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    from_location = db.Column(db.String(100), default="நெமிலி")
    delivery_location = db.Column(db.String(200), nullable=True)
    has_waybill = db.Column(db.Boolean, default=False)

    customer = db.relationship("Customer", back_populates="invoices")
    vehicle = db.relationship("Vehicle", back_populates="invoices")
    user = db.relationship("User")
    items = db.relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    rate = db.Column(db.Float, nullable=False)
    amount = db.Column(db.Float, nullable=False)

    invoice = db.relationship("Invoice", back_populates="items")


class Waybill(db.Model):
    __tablename__ = "waybills"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False, unique=True)
    driver_name = db.Column(db.String(200), nullable=True)
    loading_time = db.Column(db.DateTime, nullable=True)
    unloading_time = db.Column(db.DateTime, nullable=True)
    material_type = db.Column(db.String(200), nullable=True)
    vehicle_capacity = db.Column(db.String(100), nullable=True)
    delivery_location = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    invoice = db.relationship("Invoice", backref="waybill")


class Settings(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True)
    company_name_tamil = db.Column(db.Text, default="ஸ்ரீ தனலட்சுமி புளூ மெட்டல்ஸ்")
    company_name_english = db.Column(db.String(200), default="Sri Dhanalakshmi Blue Metals")
    address_tamil = db.Column(db.Text, default="நெமிலி & எண்வரடி அஞ்சல், எண்டியூர்,\nவாணூர் தாலுகா, விழுப்புரம் மாவட்டம்.")
    address_english = db.Column(db.Text, default="Nemili & Envaradi Post, Endiyur,\nVandur Taluk, Villupuram District.")
    gstin = db.Column(db.String(50), default="33AUXPR8335C1Z7")
    phone_numbers = db.Column(db.String(200), default="97883 88823, 97515 31619, 75026 27223")
    cgst_percent = db.Column(db.Float, default=2.5)
    sgst_percent = db.Column(db.Float, default=2.5)
    from_location = db.Column(db.String(100), default="நெமிலி")
    # Messaging settings
    sms_provider = db.Column(db.String(50), default="twilio")  # twilio, msg91, generic
    sms_api_key = db.Column(db.String(200), nullable=True)
    sms_api_secret = db.Column(db.String(200), nullable=True)  # For Twilio Auth Token
    sms_sender_id = db.Column(db.String(50), nullable=True)
    sms_api_url = db.Column(db.String(500), nullable=True)  # For generic provider
    sms_template = db.Column(db.Text, nullable=True)
    whatsapp_provider = db.Column(db.String(50), default="twilio")  # twilio, generic
    whatsapp_sender_number = db.Column(db.String(20), nullable=True)
    whatsapp_api_key = db.Column(db.String(200), nullable=True)  # For generic provider
    whatsapp_api_url = db.Column(db.String(500), nullable=True)  # For generic provider
    whatsapp_template = db.Column(db.Text, nullable=True)
    auto_send_sms = db.Column(db.Boolean, default=False)  # Auto-send SMS after invoice creation
    auto_send_whatsapp = db.Column(db.Boolean, default=False)  # Auto-send WhatsApp after invoice creation
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)  # login, create_bill, edit_bill, delete_bill, etc.
    resource_type = db.Column(db.String(50), nullable=True)  # invoice, user, customer, etc.
    resource_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship("User")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------
def get_next_bill_no():
    """Generate next bill number (0001, 0002, ...)"""
    last_invoice = Invoice.query.order_by(desc(Invoice.id)).first()
    if last_invoice and last_invoice.bill_no:
        try:
            last_num = int(last_invoice.bill_no)
            return f"{last_num + 1:04d}"
        except:
            return f"{last_invoice.id + 1:04d}"
    return "0001"


def get_settings():
    """Get or create default settings"""
    settings = Settings.query.first()
    if not settings:
        settings = Settings()
        db.session.add(settings)
        db.session.commit()
    return settings


def admin_required(f):
    """Decorator to require admin role"""
    from functools import wraps

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != "admin":
            flash("Admin access required", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)

    return decorated_function


def staff_required(f):
    """Decorator to require staff or admin role"""
    from functools import wraps

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role not in ["staff", "admin"]:
            flash("Staff or admin access required", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)

    return decorated_function


def role_required(role):
    """Decorator to require specific role"""
    from functools import wraps
    
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if role == "admin" and current_user.role != "admin":
                flash("Admin access required", "danger")
                return redirect(url_for("dashboard"))
            elif role == "staff" and current_user.role not in ["staff", "admin"]:
                flash("Staff or admin access required", "danger")
                return redirect(url_for("dashboard"))
            elif role == "user" and current_user.role not in ["user", "staff", "admin"]:
                flash("Access denied", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def log_audit(action, resource_type=None, resource_id=None, details=None, ip_address=None):
    """Log an audit event"""
    try:
        log = AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address or request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"Error logging audit: {e}")
        db.session.rollback()


def get_user_invoices_query():
    """Get invoice query filtered by user role"""
    if current_user.role == "admin":
        return Invoice.query
    elif current_user.role == "staff":
        return Invoice.query
    else:  # user role - only their own invoices
        return Invoice.query.filter_by(customer_id=current_user.customer_id)


# ------------------------------------------------------------
# Database initialisation
# ------------------------------------------------------------
def init_db():
    """Create tables and seed default data if needed."""
    try:
        db.create_all()
        
        # Auto-migrate: Add new columns if they don't exist
        try:
            from sqlalchemy import inspect as sql_inspect
            inspector = sql_inspect(db.engine)
            if inspector.has_table('users'):
                columns = [col['name'] for col in inspector.get_columns('users')]
                
                if 'email' not in columns:
                    with db.engine.connect() as conn:
                        conn.execute(db.text('ALTER TABLE users ADD COLUMN email VARCHAR(150)'))
                        conn.commit()
                    print("✅ Added email column to users table")
                
                if 'name' not in columns:
                    with db.engine.connect() as conn:
                        conn.execute(db.text('ALTER TABLE users ADD COLUMN name VARCHAR(200)'))
                        conn.commit()
                    print("✅ Added name column to users table")
                
                if 'status' not in columns:
                    with db.engine.connect() as conn:
                        conn.execute(db.text('ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT "active"'))
                        conn.commit()
                    print("✅ Added status column to users table")
        except Exception as e:
            print(f"⚠️ Migration note: {e}")
        
        # Auto-migrate: Add messaging columns to settings table
        try:
            from sqlalchemy import inspect as sql_inspect
            inspector = sql_inspect(db.engine)
            if inspector.has_table('settings'):
                columns = [col['name'] for col in inspector.get_columns('settings')]
                
                messaging_fields = [
                    ('sms_provider', 'VARCHAR(50) DEFAULT "twilio"'),
                    ('sms_api_secret', 'VARCHAR(200)'),
                    ('sms_api_url', 'VARCHAR(500)'),
                    ('whatsapp_provider', 'VARCHAR(50) DEFAULT "twilio"'),
                    ('whatsapp_api_key', 'VARCHAR(200)'),
                    ('whatsapp_api_url', 'VARCHAR(500)'),
                    ('auto_send_sms', 'BOOLEAN DEFAULT 0'),
                    ('auto_send_whatsapp', 'BOOLEAN DEFAULT 0'),
                ]
                
                for field_name, field_type in messaging_fields:
                    if field_name not in columns:
                        with db.engine.connect() as conn:
                            conn.execute(db.text(f'ALTER TABLE settings ADD COLUMN {field_name} {field_type}'))
                            conn.commit()
                        print(f"✅ Added {field_name} column to settings table")
        except Exception as e:
            print(f"⚠️ Settings migration note: {e}")

        # Create default admin user
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@nrd",
                name="Administrator",
                password_hash=generate_password_hash("nrd"),
                role="admin",
                status="active"
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Default admin user created (email: admin@nrd, password: nrd)")

        # Create default items
        if Item.query.count() == 0:
            default_items = [
                {"name": "1½ ஜல்லி", "rate": 3000.0},
                {"name": "¾ ஜல்லி", "rate": 3000.0},
                {"name": "½ ஜல்லி", "rate": 3000.0},
                {"name": "¼ ஜல்லி", "rate": 3000.0},
                {"name": "பவுடர்", "rate": 3000.0},
                {"name": "மிக்சிங்", "rate": 3000.0},
            ]
            for item_data in default_items:
                item = Item(name=item_data["name"], rate=item_data["rate"])
                db.session.add(item)
            db.session.commit()
            print("✅ Default items created")

        # Create default settings
        get_settings()
        print("✅ Database initialized successfully")
        return True
    except Exception as err:
        print("⚠️ DB initialization error:", err)
        import traceback
        traceback.print_exc()
        return False


@app.before_request
def ensure_database():
    init_db()


# ------------------------------------------------------------
# Routes - Authentication
# ------------------------------------------------------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if user.status != "active":
                return render_template("login.html", error="Your account is inactive. Please contact administrator.")
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            log_audit("login", ip_address=request.remote_addr)
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="தவறான பயனர் பெயர் அல்லது கடவுச்சொல்")

    return render_template("login.html")


@app.route("/logout")
def logout():
    if current_user.is_authenticated:
        log_audit("logout", ip_address=request.remote_addr)
        logout_user()
    flash("Logged out successfully", "info")
    return redirect(url_for("login"))


# ------------------------------------------------------------
# Routes - Dashboard
# ------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Get filtered invoice query based on user role
    invoice_query = get_user_invoices_query()

    # Summary statistics
    today_invoices = invoice_query.filter(Invoice.date >= today).all()
    today_total = sum(inv.grand_total for inv in today_invoices)
    today_count = len(today_invoices)

    monthly_invoices = invoice_query.filter(Invoice.date >= month_start).all()
    monthly_total = sum(inv.grand_total for inv in monthly_invoices)

    # Customer count - only for admin/staff
    if current_user.role in ["admin", "staff"]:
        customer_count = Customer.query.count()
    else:
        customer_count = 1 if current_user.customer_id else 0

    # Recent invoices
    recent_invoices = invoice_query.order_by(desc(Invoice.created_at)).limit(10).all()

    # Recent customers - only for admin/staff
    if current_user.role in ["admin", "staff"]:
        recent_customers = (
            db.session.query(Customer)
            .join(Invoice)
            .order_by(desc(Invoice.created_at))
            .distinct()
            .limit(5)
            .all()
        )
    else:
        # For user role, show only their customer
        if current_user.customer_id:
            recent_customers = [current_user.customer] if current_user.customer else []
        else:
            recent_customers = []

    return render_template(
        "dashboard.html",
        today_count=today_count,
        today_total=today_total,
        monthly_total=monthly_total,
        customer_count=customer_count,
        recent_invoices=recent_invoices,
        recent_customers=recent_customers,
    )


# ------------------------------------------------------------
# Routes - Search
# ------------------------------------------------------------
@app.route("/search")
@login_required
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return redirect(url_for("dashboard"))

    # Get filtered invoice query based on user role
    invoice_query = get_user_invoices_query()

    # Search invoices by customer name, vehicle, or bill number
    invoices = (
        invoice_query.join(Customer)
        .outerjoin(Vehicle)
        .filter(
            db.or_(
                Customer.name.ilike(f"%{query}%"),
                Invoice.bill_no.ilike(f"%{query}%"),
                Vehicle.vehicle_number.ilike(f"%{query}%"),
            )
        )
        .order_by(desc(Invoice.created_at))
        .all()
    )

    return render_template("search_results.html", invoices=invoices, query=query)


# ------------------------------------------------------------
# Routes - Customers
# ------------------------------------------------------------
@app.route("/customers")
@login_required
def customers():
    if current_user.role == "user":
        # Users can only see their own customer
        if current_user.customer_id:
            customers_list = [current_user.customer] if current_user.customer else []
        else:
            customers_list = []
    else:
        customers_list = Customer.query.order_by(Customer.name).all()
    return render_template("customers.html", customers=customers_list)


@app.route("/customers/add", methods=["POST"])
@login_required
def add_customer():
    try:
        customer = Customer(
            name=request.form.get("name", "").strip(),
            gst_number=request.form.get("gst_number", "").strip() or None,
            phone=request.form.get("phone", "").strip() or None,
            address=request.form.get("address", "").strip() or None,
        )
        db.session.add(customer)
        db.session.commit()
        flash("Customer added successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding customer: {str(e)}", "danger")
    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/edit", methods=["POST"])
@staff_required
def edit_customer(customer_id):
    try:
        customer = Customer.query.get_or_404(customer_id)
        customer.name = request.form.get("name", "").strip()
        customer.gst_number = request.form.get("gst_number", "").strip() or None
        customer.phone = request.form.get("phone", "").strip() or None
        customer.address = request.form.get("address", "").strip() or None
        db.session.commit()
        flash("Customer updated successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating customer: {str(e)}", "danger")
    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/delete", methods=["POST"])
@admin_required
def delete_customer(customer_id):
    try:
        customer = Customer.query.get_or_404(customer_id)
        db.session.delete(customer)
        db.session.commit()
        flash("Customer deleted successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting customer: {str(e)}", "danger")
    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    # Check access - users can only see their own customer
    if current_user.role == "user" and current_user.customer_id != customer_id:
        flash("Access denied", "danger")
        return redirect(url_for("dashboard"))
    invoices = Invoice.query.filter_by(customer_id=customer_id).order_by(desc(Invoice.created_at)).all()
    return render_template("customer_detail.html", customer=customer, invoices=invoices)


# ------------------------------------------------------------
# Routes - API for autocomplete
# ------------------------------------------------------------
@app.route("/api/customers")
@login_required
def api_customers():
    query = request.args.get("q", "").strip()
    customers = Customer.query.filter(Customer.name.ilike(f"%{query}%")).limit(10).all()
    return jsonify([{"id": c.id, "name": c.name, "gst_number": c.gst_number or "", "phone": c.phone or "", "address": c.address or ""} for c in customers])


@app.route("/api/vehicles")
@login_required
def api_vehicles():
    query = request.args.get("q", "").strip().upper()
    customer_id = request.args.get("customer_id", type=int)
    
    # If customer_id provided, prioritize vehicles for that customer
    if customer_id:
        vehicles = Vehicle.query.filter(
            Vehicle.vehicle_number.ilike(f"%{query}%"),
            Vehicle.customer_id == customer_id
        ).order_by(desc(Vehicle.created_at)).limit(10).all()
        # If no matches for customer, fall back to all vehicles
        if not vehicles:
            vehicles = Vehicle.query.filter(Vehicle.vehicle_number.ilike(f"%{query}%")).limit(10).all()
    else:
        vehicles = Vehicle.query.filter(Vehicle.vehicle_number.ilike(f"%{query}%")).order_by(desc(Vehicle.created_at)).limit(10).all()
    
    return jsonify([{"id": v.id, "vehicle_number": v.vehicle_number, "vehicle_type": v.vehicle_type or ""} for v in vehicles])


# ------------------------------------------------------------
# Routes - Create Bill
# ------------------------------------------------------------
@app.route("/create_bill", methods=["GET", "POST"])
@staff_required
def create_bill():
    try:
        if request.method == "POST":
            try:
                # Get form data
                customer_name = request.form.get("customer_name", "").strip()
                vehicle_number = request.form.get("vehicle_number", "").strip().upper()
                bill_date = request.form.get("date", datetime.now().strftime("%Y-%m-%d"))
                
                if not customer_name:
                    flash("Customer name is required", "danger")
                    items = Item.query.filter_by(is_active=True).all() or []
                    items_data = [{"id": item.id, "name": item.name, "rate": float(item.rate)} for item in items]
                    return render_template("create_bill.html", items=items, items_data=items_data)
                
                if not vehicle_number:
                    flash("Vehicle number is required", "danger")
                    items = Item.query.filter_by(is_active=True).all() or []
                    items_data = [{"id": item.id, "name": item.name, "rate": float(item.rate)} for item in items]
                    return render_template("create_bill.html", items=items, items_data=items_data)
                
                # Validate vehicle format - Allow TN32AX3344, TN10AA9988, etc.
                import re
                # Pattern: 2 letters, 2 digits, 1-2 letters, 4 digits
                if not re.match(r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$", vehicle_number):
                    flash("Invalid vehicle number format. Expected format: TN32AX3344 or TN10AA9988", "danger")
                    items = Item.query.filter_by(is_active=True).all() or []
                    items_data = [{"id": item.id, "name": item.name, "rate": float(item.rate)} for item in items]
                    return render_template("create_bill.html", items=items, items_data=items_data)
                
                # Get or create customer
                customer = Customer.query.filter_by(name=customer_name).first()
                if not customer:
                    customer = Customer(
                        name=customer_name,
                        gst_number=request.form.get("customer_gst", "").strip() or None,
                        phone=request.form.get("customer_phone", "").strip() or None,
                        address=request.form.get("customer_address", "").strip() or None,
                    )
                    db.session.add(customer)
                    db.session.flush()
                
                # Get or create vehicle
                vehicle = Vehicle.query.filter_by(vehicle_number=vehicle_number).first()
                if not vehicle:
                    vehicle = Vehicle(
                        vehicle_number=vehicle_number,
                        vehicle_type=request.form.get("vehicle_type", "").strip() or None,
                        customer_id=customer.id,
                    )
                    db.session.add(vehicle)
                    db.session.flush()
                
                # Create invoice
                settings = get_settings()
                bill_no = get_next_bill_no()
                delivery_location = request.form.get("delivery_location", "").strip() or None
                has_waybill = request.form.get("generate_waybill") == "on"
                
                invoice = Invoice(
                    bill_no=bill_no,
                    date=datetime.strptime(bill_date, "%Y-%m-%d"),
                    customer_id=customer.id,
                    vehicle_id=vehicle.id,
                    user_id=current_user.id,
                    from_location=settings.from_location,
                    delivery_location=delivery_location,
                    has_waybill=has_waybill,
                )
                db.session.add(invoice)
                db.session.flush()
                
                # Create waybill if requested
                if has_waybill:
                    driver_name = request.form.get("driver_name", "").strip() or None
                    if not driver_name:
                        db.session.rollback()
                        flash("Driver name is required when generating waybill", "danger")
                        items = Item.query.filter_by(is_active=True).all() or []
                        items_data = [{"id": item.id, "name": item.name, "rate": float(item.rate)} for item in items]
                        return render_template("create_bill.html", items=items, items_data=items_data)
                    
                    material_type = request.form.get("material_type", "").strip() or None
                    vehicle_capacity = request.form.get("vehicle_capacity", "").strip() or None
                    
                    # Calculate loading and unloading times
                    # Loading time = current time
                    loading_time = datetime.now()
                    
                    # Unloading time = loading time + duration
                    delivery_duration = request.form.get("delivery_duration", "").strip()
                    duration_unit = request.form.get("duration_unit", "hours").strip()
                    
                    unloading_time = loading_time
                    if delivery_duration:
                        try:
                            duration = float(delivery_duration)
                            if duration_unit == "hours":
                                unloading_time = loading_time + timedelta(hours=duration)
                            else:  # minutes
                                unloading_time = loading_time + timedelta(minutes=duration)
                        except (ValueError, TypeError):
                            # If duration is invalid, set unloading time same as loading time
                            unloading_time = loading_time
                    else:
                        # Default to 2 hours if not specified
                        unloading_time = loading_time + timedelta(hours=2)
                    
                    waybill = Waybill(
                        invoice_id=invoice.id,
                        driver_name=driver_name,
                        loading_time=loading_time,
                        unloading_time=unloading_time,
                        material_type=material_type,
                        vehicle_capacity=vehicle_capacity,
                        delivery_location=delivery_location,
                    )
                    db.session.add(waybill)
                
                # Process items
                item_names = request.form.getlist("item_name[]")
                quantities = request.form.getlist("quantity[]")
                rates = request.form.getlist("rate[]")
                
                subtotal = 0.0
                for i in range(len(item_names)):
                    if item_names[i] and quantities[i] and rates[i]:
                        try:
                            qty = float(quantities[i])
                            rate = float(rates[i])
                            amount = qty * rate
                            subtotal += amount
                            
                            invoice_item = InvoiceItem(
                                invoice_id=invoice.id,
                                item_name=item_names[i],
                                quantity=qty,
                                rate=rate,
                                amount=amount,
                            )
                            db.session.add(invoice_item)
                        except (ValueError, TypeError) as e:
                            print(f"Error processing item {i}: {e}")
                            continue
                
                if subtotal == 0:
                    db.session.rollback()
                    flash("At least one item with quantity and rate is required", "danger")
                    items = Item.query.filter_by(is_active=True).all() or []
                    items_data = [{"id": item.id, "name": item.name, "rate": float(item.rate)} for item in items]
                    return render_template("create_bill.html", items=items, items_data=items_data)
                
                # Calculate GST
                cgst = subtotal * (settings.cgst_percent / 100)
                sgst = subtotal * (settings.sgst_percent / 100)
                grand_total = subtotal + cgst + sgst
                
                invoice.subtotal = subtotal
                invoice.cgst = cgst
                invoice.sgst = sgst
                invoice.grand_total = grand_total
                
                db.session.commit()
                log_audit("create_bill", "invoice", invoice.id, f"Bill {invoice.bill_no} created", request.remote_addr)
                
                # Auto-send SMS/WhatsApp notifications if enabled
                try:
                    settings_obj = get_settings()
                    if settings_obj.auto_send_sms or settings_obj.auto_send_whatsapp:
                        base_url = request.url_root.rstrip('/')
                        notification_results = send_invoice_notification(settings_obj, invoice, base_url)
                        
                        if settings_obj.auto_send_sms and notification_results.get("sms", {}).get("success"):
                            flash("Bill created and SMS sent successfully!", "success")
                        elif settings_obj.auto_send_whatsapp and notification_results.get("whatsapp", {}).get("success"):
                            flash("Bill created and WhatsApp sent successfully!", "success")
                        else:
                            flash("Bill created successfully!", "success")
                    else:
                        flash("Bill created successfully!", "success")
                except Exception as e:
                    print(f"⚠️ Error sending notifications: {e}")
                    flash("Bill created successfully! (Notification sending failed)", "success")
                
                return redirect(url_for("invoice_detail", invoice_id=invoice.id))
                
            except Exception as e:
                db.session.rollback()
                flash(f"Error creating bill: {str(e)}", "danger")
                import traceback
                traceback.print_exc()
                items = Item.query.filter_by(is_active=True).all() or []
                items_data = [{"id": item.id, "name": item.name, "rate": float(item.rate)} for item in items]
                return render_template("create_bill.html", items=items, items_data=items_data)
        
        # GET request - show form
        try:
            items = Item.query.filter_by(is_active=True).all()
            # Convert to list of dicts for JSON serialization
            items_data = [{"id": item.id, "name": item.name, "rate": float(item.rate)} for item in items]
        except Exception as e:
            print(f"Error fetching items: {e}")
            items = []
            items_data = []
        
        return render_template("create_bill.html", items=items, items_data=items_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f"Error loading create bill page: {str(e)}", "danger")
        return redirect(url_for("dashboard"))


# ------------------------------------------------------------
# Routes - Invoice Detail & PDF
# ------------------------------------------------------------
@app.route("/invoice/<int:invoice_id>")
@login_required
def invoice_detail(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    # Check access - users can only see their own invoices
    if current_user.role == "user" and current_user.customer_id != invoice.customer_id:
        flash("Access denied", "danger")
        return redirect(url_for("dashboard"))
    settings = get_settings()
    return render_template("invoice_detail.html", invoice=invoice, settings=settings)


@app.route("/invoice/<int:invoice_id>/pdf")
@login_required
def invoice_pdf(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    # Check access - users can only see their own invoices
    if current_user.role == "user" and current_user.customer_id != invoice.customer_id:
        flash("Access denied", "danger")
        return redirect(url_for("dashboard"))
    settings = get_settings()
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    # Use Tamil font if available
    font_name = "TamilFont" if "TamilFont" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    c.setFont(font_name, 16)
    
    y = 800
    # Company header
    c.setFont(font_name, 18)
    c.drawString(60, y, settings.company_name_tamil)
    y -= 25
    c.setFont("Helvetica", 14)
    c.drawString(60, y, settings.company_name_english)
    y -= 20
    
    # Address
    c.setFont(font_name, 10)
    for line in settings.address_tamil.split("\n"):
        c.drawString(60, y, line)
        y -= 15
    
    # GSTIN and Phone
    c.setFont("Helvetica", 10)
    c.drawString(60, y, f"GSTIN: {settings.gstin} | Phone: {settings.phone_numbers}")
    y -= 30
    
    # Bill details
    c.setFont(font_name, 12)
    c.drawString(60, y, f"பில் எண் / Bill No: {invoice.bill_no}")
    y -= 20
    c.drawString(60, y, f"தேதி / Date: {invoice.date.strftime('%d-%m-%Y')}")
    y -= 20
    c.drawString(60, y, f"இடம் / From: {invoice.from_location}")
    y -= 30
    
    # Customer details
    c.drawString(60, y, f"வாடிக்கையாளர் / Customer: {invoice.customer.name}")
    y -= 20
    if invoice.customer.gst_number:
        c.drawString(60, y, f"GST No: {invoice.customer.gst_number}")
        y -= 20
    c.drawString(60, y, f"வாகன எண் / Vehicle: {invoice.vehicle.vehicle_number if invoice.vehicle else 'N/A'}")
    y -= 20
    if invoice.delivery_location:
        c.drawString(60, y, f"விநியோக இடம் / Delivery Location: {invoice.delivery_location}")
        y -= 20
    y -= 10
    
    # Items table header
    c.setFont(font_name, 11)
    c.drawString(60, y, "பொருள் / Item")
    c.drawString(200, y, "அளவு / Qty")
    c.drawString(280, y, "விலை / Rate")
    c.drawString(360, y, "தொகை / Amount")
    y -= 20
    c.line(60, y, 500, y)
    y -= 15
    
    # Items
    c.setFont("Helvetica", 10)
    for item in invoice.items:
        c.drawString(60, y, item.item_name)
        c.drawString(200, y, f"{item.quantity:.2f}")
        c.drawString(280, y, f"₹{item.rate:.2f}")
        c.drawString(360, y, f"₹{item.amount:.2f}")
        y -= 20
    
    y -= 10
    c.line(60, y, 500, y)
    y -= 20
    
    # Totals
    c.setFont(font_name, 11)
    c.drawString(300, y, f"Subtotal: ₹{invoice.subtotal:.2f}")
    y -= 20
    c.drawString(300, y, f"CGST {settings.cgst_percent}%: ₹{invoice.cgst:.2f}")
    y -= 20
    c.drawString(300, y, f"SGST {settings.sgst_percent}%: ₹{invoice.sgst:.2f}")
    y -= 20
    c.setFont("Helvetica-Bold", 14)
    c.drawString(300, y, f"Grand Total: ₹{invoice.grand_total:.2f}")
    y -= 40
    
    # Waybill information if exists
    if invoice.has_waybill and invoice.waybill:
        y -= 20
        c.line(60, y, 500, y)
        y -= 20
        c.setFont(font_name, 12)
        c.drawString(60, y, "வேய்பில் தகவல் / Waybill Information:")
        y -= 20
        c.setFont("Helvetica", 10)
        if invoice.waybill.driver_name:
            c.drawString(60, y, f"Driver Name / ஓட்டுநர் பெயர்: {invoice.waybill.driver_name}")
            y -= 15
        if invoice.waybill.material_type:
            c.drawString(60, y, f"Material Type / பொருள் வகை: {invoice.waybill.material_type}")
            y -= 15
        if invoice.waybill.loading_time:
            c.drawString(60, y, f"Loading Time / ஏற்ற நேரம்: {invoice.waybill.loading_time.strftime('%d-%m-%Y %H:%M')}")
            y -= 15
        if invoice.waybill.unloading_time:
            c.drawString(60, y, f"Unloading Time / இறக்கும் நேரம்: {invoice.waybill.unloading_time.strftime('%d-%m-%Y %H:%M')}")
            y -= 15
            # Calculate and display duration
            if invoice.waybill.loading_time:
                duration = invoice.waybill.unloading_time - invoice.waybill.loading_time
                hours = duration.total_seconds() / 3600
                if hours >= 1:
                    duration_str = f"{hours:.1f} hours"
                else:
                    minutes = duration.total_seconds() / 60
                    duration_str = f"{minutes:.0f} minutes"
                c.drawString(60, y, f"Duration / காலம்: {duration_str}")
                y -= 15
        if invoice.waybill.vehicle_capacity:
            c.drawString(60, y, f"Vehicle Capacity / வாகன திறன்: {invoice.waybill.vehicle_capacity}")
            y -= 15
        if invoice.waybill.delivery_location:
            c.drawString(60, y, f"Delivery Location / விநியோக இடம்: {invoice.waybill.delivery_location}")
            y -= 15
        y -= 10
    
    # Footer with signature block
    y -= 20
    c.setFont(font_name, 10)
    c.drawString(60, y, "அங்கீகரிக்கப்பட்டவர் – ஸ்ரீ தனலட்சுமி புளு மெட்டல்ஸ்")
    y -= 30
    
    # Signature area
    c.setFont("Helvetica", 10)
    c.drawString(60, y, "__________________________")
    y -= 15
    c.drawString(60, y, "Authorized Signature")
    
    c.showPage()
    c.save()
    buffer.seek(0)
    
    return send_file(
        buffer,
        download_name=f"invoice_{invoice.bill_no}.pdf",
        as_attachment=True,
        mimetype="application/pdf",
    )


@app.route("/invoice/<int:invoice_id>/duplicate", methods=["POST"])
@staff_required
def duplicate_invoice(invoice_id):
    try:
        original = Invoice.query.get_or_404(invoice_id)
        bill_no = get_next_bill_no()
        
        new_invoice = Invoice(
            bill_no=bill_no,
            date=datetime.now(),
            customer_id=original.customer_id,
            vehicle_id=original.vehicle_id,
            user_id=current_user.id,
            subtotal=original.subtotal,
            cgst=original.cgst,
            sgst=original.sgst,
            grand_total=original.grand_total,
            from_location=original.from_location,
        )
        db.session.add(new_invoice)
        db.session.flush()
        
        for item in original.items:
            new_item = InvoiceItem(
                invoice_id=new_invoice.id,
                item_name=item.item_name,
                quantity=item.quantity,
                rate=item.rate,
                amount=item.amount,
            )
            db.session.add(new_item)
        
        db.session.commit()
        log_audit("duplicate_bill", "invoice", new_invoice.id, f"Bill {new_invoice.bill_no} duplicated from {original.bill_no}", request.remote_addr)
        flash("Invoice duplicated successfully", "success")
        return redirect(url_for("invoice_detail", invoice_id=new_invoice.id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error duplicating invoice: {str(e)}", "danger")
        return redirect(url_for("dashboard"))


@app.route("/invoice/<int:invoice_id>/delete", methods=["POST"])
@staff_required
def delete_invoice(invoice_id):
    try:
        invoice = Invoice.query.get_or_404(invoice_id)
        bill_no = invoice.bill_no
        db.session.delete(invoice)
        db.session.commit()
        log_audit("delete_bill", "invoice", invoice_id, f"Bill {bill_no} deleted", request.remote_addr)
        flash("Invoice deleted successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting invoice: {str(e)}", "danger")
    return redirect(url_for("dashboard"))


# ------------------------------------------------------------
# Routes - Reports
# ------------------------------------------------------------
@app.route("/reports")
@login_required
def reports():
    return render_template("reports.html")


@app.route("/reports/daily")
@login_required
def daily_report():
    date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    try:
        report_date = datetime.strptime(date_str, "%Y-%m-%d")
        start = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = report_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Get filtered invoice query based on user role
        invoice_query = get_user_invoices_query()
        invoices = invoice_query.filter(Invoice.date >= start, Invoice.date <= end).order_by(Invoice.date).all()
        total_amount = sum(inv.grand_total for inv in invoices)
        
        return render_template("daily_report.html", invoices=invoices, date=report_date, total_amount=total_amount, count=len(invoices))
    except:
        flash("Invalid date format", "danger")
        return redirect(url_for("reports"))


@app.route("/reports/weekly")
@login_required
def weekly_report():
    week_str = request.args.get("week", "")
    try:
        if week_str:
            # Handle ISO week format: YYYY-Www
            if "-W" in week_str:
                year, week = map(int, week_str.split("-W"))
                # Calculate start of week (Monday)
                jan1 = datetime(year, 1, 1)
                days_offset = (week - 1) * 7
                start = jan1 + timedelta(days=days_offset - jan1.weekday())
            else:
                # Handle HTML5 week input format: YYYY-Www
                parts = week_str.split("-W")
                if len(parts) == 2:
                    year, week = int(parts[0]), int(parts[1])
                    jan1 = datetime(year, 1, 1)
                    days_offset = (week - 1) * 7
                    start = jan1 + timedelta(days=days_offset - jan1.weekday())
                else:
                    raise ValueError("Invalid week format")
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        else:
            # Default to current week
            today = datetime.now()
            start = today - timedelta(days=today.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        
        # Get filtered invoice query based on user role
        invoice_query = get_user_invoices_query()
        invoices = invoice_query.filter(Invoice.date >= start, Invoice.date <= end).order_by(Invoice.date).all()
        total_amount = sum(inv.grand_total for inv in invoices)
        
        return render_template("weekly_report.html", invoices=invoices, start_date=start, end_date=end, total_amount=total_amount, count=len(invoices))
    except Exception as e:
        flash(f"Invalid week format: {str(e)}", "danger")
        return redirect(url_for("reports"))


@app.route("/reports/monthly")
@login_required
def monthly_report():
    month_str = request.args.get("month", datetime.now().strftime("%Y-%m"))
    try:
        year, month = map(int, month_str.split("-"))
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end = datetime(year, month + 1, 1) - timedelta(seconds=1)
        
        # Get filtered invoice query based on user role
        invoice_query = get_user_invoices_query()
        invoices = invoice_query.filter(Invoice.date >= start, Invoice.date <= end).order_by(Invoice.date).all()
        
        # Group by week
        weekly_data = {}
        for inv in invoices:
            week_num = (inv.date.day - 1) // 7 + 1
            if week_num not in weekly_data:
                weekly_data[week_num] = []
            weekly_data[week_num].append(inv)
        
        weekly_totals = {week: sum(inv.grand_total for inv in invs) for week, invs in weekly_data.items()}
        monthly_total = sum(inv.grand_total for inv in invoices)
        
        return render_template("monthly_report.html", invoices=invoices, month=start, weekly_totals=weekly_totals, monthly_total=monthly_total)
    except:
        flash("Invalid month format", "danger")
        return redirect(url_for("reports"))


@app.route("/reports/customer/<int:customer_id>")
@login_required
def customer_report(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    # Check access - users can only see their own customer
    if current_user.role == "user" and current_user.customer_id != customer_id:
        flash("Access denied", "danger")
        return redirect(url_for("dashboard"))
    invoices = Invoice.query.filter_by(customer_id=customer_id).order_by(desc(Invoice.date)).all()
    total = sum(inv.grand_total for inv in invoices)
    last_visit = invoices[0].date if invoices else None
    
    return render_template("customer_report.html", customer=customer, invoices=invoices, total=total, last_visit=last_visit)


@app.route("/reports/vehicle/<int:vehicle_id>")
@login_required
def vehicle_report(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    invoices = Invoice.query.filter_by(vehicle_id=vehicle_id).order_by(desc(Invoice.date)).all()
    total = sum(inv.grand_total for inv in invoices)
    
    return render_template("vehicle_report.html", vehicle=vehicle, invoices=invoices, total=total)


@app.route("/reports/gst")
@login_required
def gst_report():
    month_str = request.args.get("month", datetime.now().strftime("%Y-%m"))
    try:
        year, month = map(int, month_str.split("-"))
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end = datetime(year, month + 1, 1) - timedelta(seconds=1)
        
        # Get filtered invoice query based on user role
        invoice_query = get_user_invoices_query()
        invoices = invoice_query.filter(Invoice.date >= start, Invoice.date <= end).all()
        total_cgst = sum(inv.cgst for inv in invoices)
        total_sgst = sum(inv.sgst for inv in invoices)
        total_amount = sum(inv.grand_total for inv in invoices)
        
        return render_template("gst_report.html", invoices=invoices, month=start, total_cgst=total_cgst, total_sgst=total_sgst, total_amount=total_amount)
    except:
        flash("Invalid month format", "danger")
        return redirect(url_for("reports"))


# ------------------------------------------------------------
# Routes - Export Reports
# ------------------------------------------------------------
@app.route("/reports/weekly/export")
@login_required
def export_weekly_csv():
    week_str = request.args.get("week", "")
    try:
        if week_str:
            year, week = map(int, week_str.split("-W"))
            jan1 = datetime(year, 1, 1)
            days_offset = (week - 1) * 7
            start = jan1 + timedelta(days=days_offset - jan1.weekday())
            end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        else:
            today = datetime.now()
            start = today - timedelta(days=today.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        
        # Get filtered invoice query based on user role
        invoice_query = get_user_invoices_query()
        invoices = invoice_query.filter(Invoice.date >= start, Invoice.date <= end).all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Bill No", "Customer", "Vehicle", "Date", "Amount"])
        for inv in invoices:
            writer.writerow([inv.bill_no, inv.customer.name, inv.vehicle.vehicle_number if inv.vehicle else "", inv.date.strftime("%Y-%m-%d"), inv.grand_total])
        
        output.seek(0)
        week_label = week_str if week_str else f"{start.strftime('%Y-%m-%d')}_to_{end.strftime('%Y-%m-%d')}"
        return send_file(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"weekly_report_{week_label}.csv",
        )
    except Exception as e:
        flash(f"Error exporting report: {str(e)}", "danger")
        return redirect(url_for("reports"))


@app.route("/reports/daily/export")
@login_required
def export_daily_csv():
    date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    report_date = datetime.strptime(date_str, "%Y-%m-%d")
    start = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = report_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Get filtered invoice query based on user role
    invoice_query = get_user_invoices_query()
    invoices = invoice_query.filter(Invoice.date >= start, Invoice.date <= end).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bill No", "Customer", "Vehicle", "Date", "Amount"])
    for inv in invoices:
        writer.writerow([inv.bill_no, inv.customer.name, inv.vehicle.vehicle_number if inv.vehicle else "", inv.date.strftime("%Y-%m-%d"), inv.grand_total])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"daily_report_{date_str}.csv",
    )


# ------------------------------------------------------------
# Routes - Settings
# ------------------------------------------------------------
@app.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        try:
            settings_obj = get_settings()
            settings_obj.company_name_tamil = request.form.get("company_name_tamil", "").strip()
            settings_obj.company_name_english = request.form.get("company_name_english", "").strip()
            settings_obj.address_tamil = request.form.get("address_tamil", "").strip()
            settings_obj.address_english = request.form.get("address_english", "").strip()
            settings_obj.gstin = request.form.get("gstin", "").strip()
            settings_obj.phone_numbers = request.form.get("phone_numbers", "").strip()
            settings_obj.cgst_percent = float(request.form.get("cgst_percent", 2.5))
            settings_obj.sgst_percent = float(request.form.get("sgst_percent", 2.5))
            settings_obj.from_location = request.form.get("from_location", "நெமிலி").strip()
            settings_obj.updated_at = datetime.utcnow()
            db.session.commit()
            flash("Settings updated successfully", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating settings: {str(e)}", "danger")
    
    settings_obj = get_settings()
    return render_template("settings.html", settings=settings_obj)


@app.route("/backup")
@admin_required
def backup_database():
    """Export all data as JSON"""
    data = {
        "customers": [{"id": c.id, "name": c.name, "gst_number": c.gst_number, "phone": c.phone, "address": c.address} for c in Customer.query.all()],
        "vehicles": [{"id": v.id, "vehicle_number": v.vehicle_number, "vehicle_type": v.vehicle_type} for v in Vehicle.query.all()],
        "invoices": [
            {
                "id": inv.id,
                "bill_no": inv.bill_no,
                "date": inv.date.isoformat(),
                "customer_id": inv.customer_id,
                "vehicle_id": inv.vehicle_id,
                "grand_total": inv.grand_total,
            }
            for inv in Invoice.query.all()
        ],
    }
    
    return send_file(
        io.BytesIO(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )


# ------------------------------------------------------------
# Routes - Items Management
# ------------------------------------------------------------
@app.route("/items")
@admin_required
def items():
    items_list = Item.query.order_by(Item.name).all()
    return render_template("items.html", items=items_list)


@app.route("/items/add", methods=["POST"])
@admin_required
def add_item():
    try:
        item = Item(
            name=request.form.get("name", "").strip(),
            rate=float(request.form.get("rate", 0)),
            is_active=True,
        )
        db.session.add(item)
        db.session.commit()
        flash("Item added successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding item: {str(e)}", "danger")
    return redirect(url_for("items"))


@app.route("/items/<int:item_id>/edit", methods=["POST"])
@admin_required
def edit_item(item_id):
    try:
        item = Item.query.get_or_404(item_id)
        item.name = request.form.get("name", "").strip()
        item.rate = float(request.form.get("rate", 0))
        item.is_active = request.form.get("is_active") == "on"
        item.updated_at = datetime.utcnow()
        db.session.commit()
        flash("Item updated successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating item: {str(e)}", "danger")
    return redirect(url_for("items"))


@app.route("/items/<int:item_id>/toggle", methods=["POST"])
@admin_required
def toggle_item(item_id):
    try:
        item = Item.query.get_or_404(item_id)
        item.is_active = not item.is_active
        item.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f"Item {'activated' if item.is_active else 'deactivated'} successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error toggling item: {str(e)}", "danger")
    return redirect(url_for("items"))


@app.route("/items/<int:item_id>/delete", methods=["POST"])
@admin_required
def delete_item(item_id):
    try:
        item = Item.query.get_or_404(item_id)
        db.session.delete(item)
        db.session.commit()
        flash("Item deleted successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting item: {str(e)}", "danger")
    return redirect(url_for("items"))


# ------------------------------------------------------------
# Routes - Admin Panel
# ------------------------------------------------------------
@app.route("/admin")
@role_required("admin")
def admin_panel():
    return render_template("admin_panel.html")


@app.route("/admin/users")
@role_required("admin")
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template("admin_users.html", users=users, customers=customers)


@app.route("/admin/users/add", methods=["POST"])
@role_required("admin")
def admin_add_user():
    try:
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "user").strip()
        customer_id = request.form.get("customer_id", type=int) or None
        
        if not username or not password:
            flash("Username and password are required", "danger")
            return redirect(url_for("admin_users"))
        
        if User.query.filter_by(username=username).first():
            flash("Username already exists", "danger")
            return redirect(url_for("admin_users"))
        
        user = User(
            username=username,
            email=email or None,
            name=name or None,
            password_hash=generate_password_hash(password),
            role=role,
            customer_id=customer_id,
            status="active"
        )
        db.session.add(user)
        db.session.commit()
        log_audit("create_user", "user", user.id, f"User {username} created with role {role}", request.remote_addr)
        flash("User created successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error creating user: {str(e)}", "danger")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/edit", methods=["POST"])
@role_required("admin")
def admin_edit_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        user.email = request.form.get("email", "").strip() or None
        user.name = request.form.get("name", "").strip() or None
        user.role = request.form.get("role", "user").strip()
        user.customer_id = request.form.get("customer_id", type=int) or None
        user.status = request.form.get("status", "active").strip()
        
        password = request.form.get("password", "").strip()
        if password:
            user.password_hash = generate_password_hash(password)
        
        db.session.commit()
        log_audit("edit_user", "user", user.id, f"User {user.username} updated", request.remote_addr)
        flash("User updated successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating user: {str(e)}", "danger")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            flash("Cannot delete your own account", "danger")
            return redirect(url_for("admin_users"))
        username = user.username
        db.session.delete(user)
        db.session.commit()
        log_audit("delete_user", "user", user_id, f"User {username} deleted", request.remote_addr)
        flash("User deleted successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting user: {str(e)}", "danger")
    return redirect(url_for("admin_users"))


@app.route("/admin/audit-logs")
@role_required("admin")
def admin_audit_logs():
    from sqlalchemy import select
    page = request.args.get("page", 1, type=int)
    per_page = 50
    logs_query = AuditLog.query.order_by(desc(AuditLog.created_at))
    total = logs_query.count()
    logs = logs_query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Create pagination object manually
    class Pagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if self.has_prev else None
            self.next_num = page + 1 if self.has_next else None
    
    pagination = Pagination(logs, page, per_page, total)
    return render_template("admin_audit_logs.html", logs=pagination)


@app.route("/admin/messaging", methods=["GET", "POST"])
@role_required("admin")
def admin_messaging():
    if request.method == "POST":
        try:
            settings = get_settings()
            # SMS Settings
            settings.sms_provider = request.form.get("sms_provider", "twilio").strip()
            settings.sms_api_key = request.form.get("sms_api_key", "").strip() or None
            settings.sms_api_secret = request.form.get("sms_api_secret", "").strip() or None
            settings.sms_sender_id = request.form.get("sms_sender_id", "").strip() or None
            settings.sms_api_url = request.form.get("sms_api_url", "").strip() or None
            settings.sms_template = request.form.get("sms_template", "").strip() or None
            settings.auto_send_sms = request.form.get("auto_send_sms") == "on"
            
            # WhatsApp Settings
            settings.whatsapp_provider = request.form.get("whatsapp_provider", "twilio").strip()
            settings.whatsapp_sender_number = request.form.get("whatsapp_sender_number", "").strip() or None
            settings.whatsapp_api_key = request.form.get("whatsapp_api_key", "").strip() or None
            settings.whatsapp_api_url = request.form.get("whatsapp_api_url", "").strip() or None
            settings.whatsapp_template = request.form.get("whatsapp_template", "").strip() or None
            settings.auto_send_whatsapp = request.form.get("auto_send_whatsapp") == "on"
            
            db.session.commit()
            flash("Messaging settings updated successfully", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating settings: {str(e)}", "danger")
    
    settings = get_settings()
    return render_template("admin_messaging.html", settings=settings)


@app.route("/admin/messaging/test-sms", methods=["POST"])
@role_required("admin")
def test_sms():
    """Send test SMS"""
    try:
        settings = get_settings()
        test_number = request.form.get("test_number", "").strip()
        
        if not test_number:
            flash("Please provide a test phone number", "danger")
            return redirect(url_for("admin_messaging"))
        
        if not settings.sms_api_key:
            flash("SMS API key not configured", "danger")
            return redirect(url_for("admin_messaging"))
        
        test_message = "Test message from Crusher Billing System. SMS integration is working!"
        if settings.sms_template:
            test_message = format_template(
                settings.sms_template,
                {
                    "customer": "Test Customer",
                    "amount": "₹1000.00",
                    "bill_no": "TEST001",
                    "date": datetime.now().strftime("%d-%m-%Y"),
                    "pdf_link": "https://example.com/invoice/TEST001/pdf"
                }
            )
        
        result = send_sms(settings, test_number, test_message)
        
        if result.get("success"):
            flash(f"Test SMS sent successfully! Message ID: {result.get('message_id', 'N/A')}", "success")
        else:
            flash(f"Failed to send test SMS: {result.get('error', 'Unknown error')}", "danger")
    except Exception as e:
        flash(f"Error sending test SMS: {str(e)}", "danger")
    
    return redirect(url_for("admin_messaging"))


@app.route("/admin/messaging/test-whatsapp", methods=["POST"])
@role_required("admin")
def test_whatsapp():
    """Send test WhatsApp message"""
    try:
        settings = get_settings()
        test_number = request.form.get("test_number", "").strip()
        
        if not test_number:
            flash("Please provide a test phone number", "danger")
            return redirect(url_for("admin_messaging"))
        
        if not settings.whatsapp_sender_number:
            flash("WhatsApp sender number not configured", "danger")
            return redirect(url_for("admin_messaging"))
        
        test_message = "Test message from Crusher Billing System. WhatsApp integration is working!"
        if settings.whatsapp_template:
            test_message = format_template(
                settings.whatsapp_template,
                {
                    "customer": "Test Customer",
                    "amount": "₹1000.00",
                    "bill_no": "TEST001",
                    "date": datetime.now().strftime("%d-%m-%Y"),
                    "pdf_link": "https://example.com/invoice/TEST001/pdf"
                }
            )
        
        result = send_whatsapp(settings, test_number, test_message)
        
        if result.get("success"):
            flash(f"Test WhatsApp sent successfully! Message ID: {result.get('message_id', 'N/A')}", "success")
        else:
            flash(f"Failed to send test WhatsApp: {result.get('error', 'Unknown error')}", "danger")
    except Exception as e:
        flash(f"Error sending test WhatsApp: {str(e)}", "danger")
    
    return redirect(url_for("admin_messaging"))


@app.route("/admin/backup-page")
@role_required("admin")
def admin_backup_page():
    """Backup/Restore page"""
    return render_template("admin_backup.html")


@app.route("/admin/backup")
@role_required("admin")
def admin_backup():
    """Download database backup"""
    try:
        backup_data = {
            "customers": [{"id": c.id, "name": c.name, "gst_number": c.gst_number, "phone": c.phone, "address": c.address} for c in Customer.query.all()],
            "vehicles": [{"id": v.id, "vehicle_number": v.vehicle_number, "vehicle_type": v.vehicle_type, "customer_id": v.customer_id} for v in Vehicle.query.all()],
            "invoices": [
                {
                    "id": inv.id,
                    "bill_no": inv.bill_no,
                    "date": inv.date.isoformat(),
                    "customer_id": inv.customer_id,
                    "vehicle_id": inv.vehicle_id,
                    "grand_total": inv.grand_total,
                    "delivery_location": inv.delivery_location,
                    "has_waybill": inv.has_waybill,
                }
                for inv in Invoice.query.all()
            ],
            "users": [{"id": u.id, "username": u.username, "email": u.email, "name": u.name, "role": u.role, "status": u.status} for u in User.query.all()],
            "settings": {
                "company_name_tamil": get_settings().company_name_tamil,
                "company_name_english": get_settings().company_name_english,
                "gstin": get_settings().gstin,
            },
            "backup_date": datetime.now().isoformat(),
        }
        
        return send_file(
            io.BytesIO(json.dumps(backup_data, indent=2, ensure_ascii=False).encode("utf-8")),
            mimetype="application/json",
            as_attachment=True,
            download_name=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )
    except Exception as e:
        flash(f"Error creating backup: {str(e)}", "danger")
        return redirect(url_for("admin_panel"))


@app.route("/admin/restore", methods=["POST"])
@role_required("admin")
def admin_restore():
    """Restore database from backup file"""
    try:
        if 'backup_file' not in request.files:
            flash("No file provided", "danger")
            return redirect(url_for("admin_panel"))
        
        file = request.files['backup_file']
        if file.filename == '':
            flash("No file selected", "danger")
            return redirect(url_for("admin_panel"))
        
        data = json.loads(file.read().decode('utf-8'))
        
        # Restore logic would go here - for safety, this is a placeholder
        flash("Restore functionality - implement with caution. This will overwrite existing data.", "warning")
        return redirect(url_for("admin_panel"))
    except Exception as e:
        flash(f"Error restoring backup: {str(e)}", "danger")
        return redirect(url_for("admin_panel"))


@app.route("/api/set-language", methods=["POST"])
def set_language():
    """Set language preference"""
    lang = request.json.get("lang", "ta")
    if lang in ["ta", "en"]:
        session["language"] = lang
        return jsonify({"success": True, "lang": lang})
    return jsonify({"success": False}), 400


@app.context_processor
def inject_language():
    """Inject language into all templates"""
    lang = session.get("language", "ta")
    return dict(current_lang=lang)


# ------------------------------------------------------------
# Routes - Health check
# ------------------------------------------------------------
@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})


# ------------------------------------------------------------
# Error handling
# ------------------------------------------------------------
@app.errorhandler(Exception)
def handle_exception(err):
    import traceback
    print("⚠️ Error:", err)
    traceback.print_exc()
    message = "An error occurred. Please try again." if RUNNING_ON_VERCEL else str(err)
    return render_template("error.html", error=message), 500


# ------------------------------------------------------------
# App factory for Vercel
# ------------------------------------------------------------
def create_app():
    with app.app_context():
        init_db()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
