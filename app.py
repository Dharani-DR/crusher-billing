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
from sqlalchemy import desc, func, and_
from datetime import datetime, timedelta
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib import colors
from reportlab.lib.units import inch
import os
import io
import csv
import json

# ------------------------------------------------------------
# Flask configuration
# ------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "crusher-secret")

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
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="user")
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


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
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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


# ------------------------------------------------------------
# Database initialisation
# ------------------------------------------------------------
def init_db():
    """Create tables and seed default data if needed."""
    try:
        db.create_all()

        # Create default admin user
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                password_hash=generate_password_hash("admin"),
                role="admin",
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Default admin user created")

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
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="தவறான பயனர் பெயர் அல்லது கடவுச்சொல்")

    return render_template("login.html")


@app.route("/logout")
def logout():
    if current_user.is_authenticated:
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

    # Summary statistics
    today_invoices = Invoice.query.filter(Invoice.date >= today).all()
    today_total = sum(inv.grand_total for inv in today_invoices)
    today_count = len(today_invoices)

    monthly_invoices = Invoice.query.filter(Invoice.date >= month_start).all()
    monthly_total = sum(inv.grand_total for inv in monthly_invoices)

    customer_count = Customer.query.count()

    # Recent invoices
    recent_invoices = Invoice.query.order_by(desc(Invoice.created_at)).limit(10).all()

    # Recent customers
    recent_customers = (
        db.session.query(Customer)
        .join(Invoice)
        .order_by(desc(Invoice.created_at))
        .distinct()
        .limit(5)
        .all()
    )

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

    # Search invoices by customer name, vehicle, or bill number
    invoices = (
        Invoice.query.join(Customer)
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
@admin_required
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
    vehicles = Vehicle.query.filter(Vehicle.vehicle_number.ilike(f"%{query}%")).limit(10).all()
    return jsonify([{"id": v.id, "vehicle_number": v.vehicle_number, "vehicle_type": v.vehicle_type or ""} for v in vehicles])


# ------------------------------------------------------------
# Routes - Create Bill
# ------------------------------------------------------------
@app.route("/create_bill", methods=["GET", "POST"])
@login_required
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
                    return render_template("create_bill.html", items=items)
                
                if not vehicle_number:
                    flash("Vehicle number is required", "danger")
                    items = Item.query.filter_by(is_active=True).all() or []
                    return render_template("create_bill.html", items=items)
                
                # Validate vehicle format
                import re
                if not re.match(r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$", vehicle_number):
                    flash("Invalid vehicle number format. Expected: TN32AX3344", "danger")
                    items = Item.query.filter_by(is_active=True).all() or []
                    return render_template("create_bill.html", items=items)
                
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
                invoice = Invoice(
                    bill_no=bill_no,
                    date=datetime.strptime(bill_date, "%Y-%m-%d"),
                    customer_id=customer.id,
                    vehicle_id=vehicle.id,
                    user_id=current_user.id,
                    from_location=settings.from_location,
                )
                db.session.add(invoice)
                db.session.flush()
                
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
                    return render_template("create_bill.html", items=items)
                
                # Calculate GST
                cgst = subtotal * (settings.cgst_percent / 100)
                sgst = subtotal * (settings.sgst_percent / 100)
                grand_total = subtotal + cgst + sgst
                
                invoice.subtotal = subtotal
                invoice.cgst = cgst
                invoice.sgst = sgst
                invoice.grand_total = grand_total
                
                db.session.commit()
                flash("Bill created successfully!", "success")
                return redirect(url_for("invoice_detail", invoice_id=invoice.id))
                
            except Exception as e:
                db.session.rollback()
                flash(f"Error creating bill: {str(e)}", "danger")
                import traceback
                traceback.print_exc()
                items = Item.query.filter_by(is_active=True).all() or []
                return render_template("create_bill.html", items=items)
        
        # GET request - show form
        try:
            items = Item.query.filter_by(is_active=True).all()
        except Exception as e:
            print(f"Error fetching items: {e}")
            items = []
        
        return render_template("create_bill.html", items=items)
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
    settings = get_settings()
    return render_template("invoice_detail.html", invoice=invoice, settings=settings)


@app.route("/invoice/<int:invoice_id>/pdf")
@login_required
def invoice_pdf(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
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
    y -= 30
    
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
    
    # Footer
    c.setFont(font_name, 10)
    c.drawString(60, y, "அங்கீகரிக்கப்பட்டவர் – ஸ்ரீ தனலட்சுமி புளு மெட்டல்ஸ்")
    
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
@login_required
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
        flash("Invoice duplicated successfully", "success")
        return redirect(url_for("invoice_detail", invoice_id=new_invoice.id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error duplicating invoice: {str(e)}", "danger")
        return redirect(url_for("dashboard"))


@app.route("/invoice/<int:invoice_id>/delete", methods=["POST"])
@admin_required
def delete_invoice(invoice_id):
    try:
        invoice = Invoice.query.get_or_404(invoice_id)
        db.session.delete(invoice)
        db.session.commit()
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
        
        invoices = Invoice.query.filter(Invoice.date >= start, Invoice.date <= end).order_by(Invoice.date).all()
        total_amount = sum(inv.grand_total for inv in invoices)
        
        return render_template("daily_report.html", invoices=invoices, date=report_date, total_amount=total_amount, count=len(invoices))
    except:
        flash("Invalid date format", "danger")
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
        
        invoices = Invoice.query.filter(Invoice.date >= start, Invoice.date <= end).order_by(Invoice.date).all()
        
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
        
        invoices = Invoice.query.filter(Invoice.date >= start, Invoice.date <= end).all()
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
@app.route("/reports/daily/export")
@login_required
def export_daily_csv():
    date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    report_date = datetime.strptime(date_str, "%Y-%m-%d")
    start = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = report_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    invoices = Invoice.query.filter(Invoice.date >= start, Invoice.date <= end).all()
    
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
