"""
Sri Dhanalakshmi Blue Metals - Crusher Billing System
Flask + SQLAlchemy Full-Stack Application
"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, func, desc
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import traceback
import csv
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import threading

# Import models
from models import Base, User, Customer, Vehicle, Item, Bill, CompanySettings


load_dotenv()

# Create Flask app (ensure only one instance)
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    DEBUG=False
)

# Vercel serverless compatibility: Use in-memory SQLite for Vercel, file-based for local/dev
# Detect Vercel environment
IS_VERCEL = os.getenv('VERCEL', '0') == '1' or os.getenv('VERCEL_ENV') is not None

if IS_VERCEL:
    # Vercel: Use in-memory SQLite (data persists only during function execution)
    # For production, consider using Vercel Postgres or external database
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    print("🔵 Running on Vercel - using in-memory SQLite")
else:
    # Local/Dev: Use file-based SQLite
    try:
        instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
        os.makedirs(instance_path, exist_ok=True)
        db_path_file = os.path.join(instance_path, 'data.db')
        if not os.path.exists(db_path_file):
            open(db_path_file, 'a').close()
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path_file.replace(os.sep, "/")}'
        print("🟢 Running locally - using file-based SQLite")
    except (OSError, PermissionError) as e:
        # Fallback to in-memory if file operations fail
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        print(f"⚠️ File operations failed, using in-memory SQLite: {e}")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Runtime error log file and global error handler (Vercel-compatible)
LOG_FILE = '/tmp/runtime_error.log' if IS_VERCEL or os.path.exists('/tmp') else None

@app.errorhandler(Exception)
def handle_exception(e):
    # Log errors safely (works in Vercel /tmp, fails gracefully otherwise)
    if LOG_FILE:
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"\n==== ERROR OCCURRED {datetime.now()} ====\n")
                traceback.print_exc(file=f)
        except (OSError, PermissionError):
            pass  # Silently fail if logging not possible
    return jsonify({"error": "Internal Server Error"}), 500

@app.route("/debug-log")
def show_debug():
    if LOG_FILE and os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                return "<pre>" + f.read() + "</pre>"
        except (OSError, PermissionError):
            return "Log file not accessible."
    return "No errors logged yet."

# Register Tamil font early (before PDF generation)
tamil_font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'fonts', 'NotoSansTamil-Regular.ttf')
tamil_font_name = 'NotoTamil'
try:
    if os.path.exists(tamil_font_path):
        if tamil_font_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(tamil_font_name, tamil_font_path))
            print(f"✅ Tamil font registered: {tamil_font_name}")
    else:
        print(f"⚠️ Tamil font not found at: {tamil_font_path}")
except Exception as e:
    print(f"⚠️ Could not register Tamil font: {e}")

engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'], echo=False)
Session = sessionmaker(bind=engine)
db_session = Session()
bill_lock = threading.Lock()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    return db_session.query(User).get(int(user_id))

# Security: Talisman, CSRF, Rate Limiter
# Note: For Vercel, we disable force_https as Vercel handles HTTPS
Talisman(app, content_security_policy=None)
csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])

# Helper function to require admin role
def admin_required(f):
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Helper function to get next bill number (sequential INV-0001)
def get_next_bill_no():
    last_bill = db_session.query(Bill).order_by(desc(Bill.id)).first()
    if last_bill and last_bill.bill_no and last_bill.bill_no.startswith('INV-'):
        try:
            last_num = int(last_bill.bill_no.split('-')[1])
        except Exception:
            last_num = last_bill.id or 0
    elif last_bill:
        last_num = last_bill.id or 0
    else:
        last_num = 0
    return f"INV-{last_num + 1:04d}"

# Helper function to get company settings
def get_company_settings():
    settings = db_session.query(CompanySettings).first()
    if not settings:
        # Create default settings
        settings = CompanySettings(
            company_name_tamil="ஸ்ரீ தனலட்சுமி புளூ மெட்டல்ஸ்",
            company_name_english="Sri Dhanalakshmi Blue Metals",
            address_tamil="நெமிலி & எண்வரடி அஞ்சல், எண்டியூர்,\nவாணூர் தாலுகா, விழுப்புரம் மாவட்டம்.",
            address_english="Nemili & Envaradi Post, Endiyur,\nVandur Taluk, Villupuram District.",
            gstin="33AUXPR8335C1Z7",
            phone_numbers="97883 88823, 97515 31619, 75026 27223",
            footer_message="நன்றி!"
        )
        db_session.add(settings)
        db_session.commit()
    return settings

# Helper function to suggest rate (based on last 3 bills of same item)
def suggest_rate(item_id):
    recent_bills = db_session.query(Bill).filter(
        Bill.item_id == item_id
    ).order_by(desc(Bill.date)).limit(3).all()
    
    if recent_bills:
        avg_rate = sum([b.rate for b in recent_bills]) / len(recent_bills)
        return round(avg_rate, 2)
    return None

# ==================== ROUTES ====================

@app.route('/ping')
def ping():
    """Health check endpoint for Vercel"""
    return jsonify({"status": "ok", "environment": "vercel" if IS_VERCEL else "local"})

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        # Rate limit by IP for login
        try:
            limiter.limit("5 per minute")(lambda: None)()
        except Exception:
            flash('Too many attempts. Please try again later.', 'danger')
            return redirect(url_for('login'))
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = db_session.query(User).filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            user.last_login = datetime.utcnow()
            db_session.commit()
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/setup')
def setup():
    """Initialize database with default users and sample data"""
    try:
        Base.metadata.create_all(engine)
        
        # Check if admin already exists
        admin = db_session.query(User).filter_by(username='admin').first()
        if not admin:
            # Create default admin
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                role='admin'
            )
            db_session.add(admin)
            
            # Create default user
            user = User(
                username='user',
                password_hash=generate_password_hash('user123'),
                role='user'
            )
            db_session.add(user)
            
            # Create sample items
            sample_items = [
                {'name': '½ ஜெல்லி', 'rate': 3000.0},
                {'name': '¾ ஜெல்லி', 'rate': 3000.0},
                {'name': '1" ஜெல்லி', 'rate': 3000.0},
                {'name': '1½" ஜெல்லி', 'rate': 3000.0},
                {'name': '2" ஜெல்லி', 'rate': 3000.0},
                {'name': '40mm ஜெல்லி', 'rate': 3000.0},
                {'name': '20mm ஜெல்லி', 'rate': 3000.0},
                {'name': '12mm ஜெல்லி', 'rate': 3000.0},
                {'name': '6mm ஜெல்லி', 'rate': 3000.0},
                {'name': 'மணல்', 'rate': 3000.0},
            ]
            
            for item_data in sample_items:
                item = Item(
                    name=item_data['name'],
                    rate=item_data['rate']
                )
                db_session.add(item)
            
            # Initialize company settings
            get_company_settings()
            
            db_session.commit()
            flash('Database initialized successfully! Default users: admin/admin123, user/user123', 'success')
        else:
            flash('Database already initialized.', 'info')
    except Exception as e:
        db_session.rollback()
        flash(f'Error initializing database: {str(e)}', 'danger')
    
    return render_template('login.html')

# ==================== DASHBOARD ====================

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    # User dashboard - show their recent bills
    recent_bills = db_session.query(Bill).filter_by(user_id=current_user.id).order_by(desc(Bill.date)).limit(10).all()
    
    # Calculate statistics
    total_bills = db_session.query(Bill).filter_by(user_id=current_user.id).count()
    total_sales = db_session.query(func.sum(Bill.grand_total)).filter_by(user_id=current_user.id).scalar() or 0.0
    
    return render_template('dashboard.html', 
                         recent_bills=recent_bills,
                         total_bills=total_bills,
                         total_sales=total_sales)

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Admin dashboard statistics
    total_users = db_session.query(User).count()
    total_customers = db_session.query(Customer).count()
    total_vehicles = db_session.query(Vehicle).count()
    total_items = db_session.query(Item).filter_by(is_active=True).count()
    total_bills = db_session.query(Bill).count()
    total_sales = db_session.query(func.sum(Bill.grand_total)).scalar() or 0.0
    
    # Today's sales
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sales = db_session.query(func.sum(Bill.grand_total)).filter(
        Bill.date >= today_start
    ).scalar() or 0.0
    
    # Monthly sales
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_sales = db_session.query(func.sum(Bill.grand_total)).filter(
        Bill.date >= month_start
    ).scalar() or 0.0
    
    # Top customers (by total sales)
    top_customers = db_session.query(
        Customer.name,
        func.sum(Bill.grand_total).label('total')
    ).join(Bill).group_by(Customer.id).order_by(desc('total')).limit(5).all()
    
    # Top-selling items
    top_items = db_session.query(
        Item.name,
        func.sum(Bill.quantity).label('total_qty'),
        func.sum(Bill.grand_total).label('total_amount')
    ).join(Bill).group_by(Item.id).order_by(desc('total_qty')).limit(5).all()
    
    # Monthly summary data for chart
    monthly_data = []
    for i in range(6):  # Last 6 months
        month_date = datetime.now().replace(day=1) - timedelta(days=30*i)
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if i == 0:
            month_end = datetime.now()
        else:
            next_month = month_date + timedelta(days=32)
            month_end = next_month.replace(day=1) - timedelta(seconds=1)
        
        month_sales = db_session.query(func.sum(Bill.grand_total)).filter(
            Bill.date >= month_start,
            Bill.date <= month_end
        ).scalar() or 0.0
        
        monthly_data.append({
            'month': month_date.strftime('%b %Y'),
            'sales': float(month_sales)
        })
    
    monthly_data.reverse()
    
    return render_template('admin_dashboard.html',
                         total_users=total_users,
                         total_customers=total_customers,
                         total_vehicles=total_vehicles,
                         total_items=total_items,
                         total_bills=total_bills,
                         total_sales=total_sales,
                         today_sales=today_sales,
                         monthly_sales=monthly_sales,
                         top_customers=top_customers,
                         top_items=top_items,
                         monthly_data=monthly_data)

# ==================== BILLING ====================

@app.route('/billing', methods=['GET', 'POST'])
@login_required
def billing():
    if request.method == 'POST':
        try:
            customer_name = request.form.get('customer_name', '').strip()
            customer_gst = request.form.get('customer_gst', '').strip()
            customer_phone = request.form.get('customer_phone', '').strip()
            customer_address = request.form.get('customer_address', '').strip()
            vehicle_number = request.form.get('vehicle_number', '').strip()
            vehicle_type = request.form.get('vehicle_type', '').strip()
            item_id = int(request.form.get('item_id'))
            quantity = float(request.form.get('quantity', 0))
            rate = float(request.form.get('rate', 0))
            round_off = float(request.form.get('round_off', 0))

            # Validate vehicle number (required)
            import re
            vehicle_pattern = re.compile(r'^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$')
            vehicle_number = vehicle_number.upper()
            if not vehicle_pattern.match(vehicle_number):
                flash('Invalid vehicle number. Format example: TN32AX3344', 'danger')
                return redirect(url_for('billing'))
            
            # Get or create customer
            customer = db_session.query(Customer).filter_by(name=customer_name).first()
            if not customer:
                customer = Customer(
                    name=customer_name,
                    gst_number=customer_gst if customer_gst else None,
                    phone=customer_phone if customer_phone else None,
                    address=customer_address if customer_address else None
                )
                db_session.add(customer)
                db_session.flush()
            else:
                # Update customer info if provided
                if customer_gst and not customer.gst_number:
                    customer.gst_number = customer_gst
                if customer_phone and not customer.phone:
                    customer.phone = customer_phone
                if customer_address and not customer.address:
                    customer.address = customer_address
            
            # Get or create vehicle
            vehicle = None
            if vehicle_number:
                vehicle = db_session.query(Vehicle).filter_by(vehicle_number=vehicle_number).first()
                if not vehicle:
                    vehicle = Vehicle(
                        vehicle_number=vehicle_number,
                        vehicle_type=vehicle_type if vehicle_type else None
                    )
                    db_session.add(vehicle)
                    db_session.flush()
            
            # Get item
            item = db_session.query(Item).get(item_id)
            if not item or not item.is_active:
                flash('Invalid item selected.', 'danger')
                return redirect(url_for('billing'))
            
            # Calculate totals
            total = quantity * rate
            gst_rate = 5.0  # 5% GST (2.5% CGST + 2.5% SGST)
            gst = total * (gst_rate / 100)
            grand_total = total + gst + round_off
            
            # Create bill (thread-safe number generation)
            with bill_lock:
                bill = Bill(
                    bill_no=get_next_bill_no(),
                    date=datetime.now(),
                    customer_id=customer.id,
                    vehicle_id=vehicle.id if vehicle else None,
                    item_id=item.id,
                    quantity=quantity,
                    rate=rate,
                    total=total,
                    gst=gst,
                    grand_total=grand_total,
                    user_id=current_user.id
                )
                db_session.add(bill)
                db_session.commit()
            
            flash('Bill created successfully!', 'success')
            return redirect(url_for('invoice_detail', bill_id=bill.id))
        except Exception as e:
            db_session.rollback()
            flash(f'Error creating bill: {str(e)}', 'danger')
    
    # GET request - show billing form
    customers = db_session.query(Customer).order_by(Customer.name).all()
    items = db_session.query(Item).filter_by(is_active=True).order_by(Item.name).all()
    
    return render_template('billing.html', customers=customers, items=items)

@app.route('/api/customers')
@login_required
def api_customers():
    """Unified customers suggestion endpoint ?q="""
    query = request.args.get('q', '').strip()
    customers = db_session.query(Customer).filter(Customer.name.ilike(f'%{query}%')).limit(10).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'gst_number': c.gst_number or '',
        'phone': c.phone or '',
        'address': c.address or ''
    } for c in customers])

@app.route('/api/vehicles')
@login_required
def api_vehicles():
    """Vehicle suggestions ?q="""
    query = request.args.get('q', '').strip().upper()
    vehicles = db_session.query(Vehicle).filter(Vehicle.vehicle_number.ilike(f'%{query}%')).limit(10).all()
    return jsonify([{
        'id': v.id,
        'vehicle_number': v.vehicle_number,
        'vehicle_type': v.vehicle_type or ''
    } for v in vehicles])

@app.route('/api/invoices', methods=['POST'])
@login_required
def api_create_invoice():
    """Create invoice via JSON"""
    data = request.get_json(silent=True) or {}
    try:
        customer_name = (data.get('customer_name') or '').strip()
        customer_gst = (data.get('customer_gst') or '').strip()
        vehicle_number = (data.get('vehicle_number') or '').strip().upper()
        vehicle_type = (data.get('vehicle_type') or '').strip()
        item_id = int(data.get('item_id'))
        quantity = float(data.get('quantity', 0))
        rate = float(data.get('rate', 0))
        round_off = float(data.get('round_off', 0))

        import re
        vehicle_pattern = re.compile(r'^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$')
        if not vehicle_pattern.match(vehicle_number):
            return jsonify({'error': 'Invalid vehicle number'}), 400

        customer = db_session.query(Customer).filter_by(name=customer_name).first()
        if not customer:
            customer = Customer(name=customer_name, gst_number=customer_gst or None)
            db_session.add(customer)
            db_session.flush()

        vehicle = db_session.query(Vehicle).filter_by(vehicle_number=vehicle_number).first()
        if not vehicle:
            vehicle = Vehicle(vehicle_number=vehicle_number, vehicle_type=vehicle_type or None)
            db_session.add(vehicle)
            db_session.flush()

        item = db_session.query(Item).get(item_id)
        if not item or not item.is_active:
            return jsonify({'error': 'Invalid item'}), 400

        total = quantity * rate
        gst_rate = 5.0
        gst = total * (gst_rate / 100)
        grand_total = total + gst + round_off

        with bill_lock:
            bill = Bill(
                bill_no=get_next_bill_no(),
                date=datetime.now(),
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                item_id=item.id,
                quantity=quantity,
                rate=rate,
                total=total,
                gst=gst,
                grand_total=grand_total,
                user_id=current_user.id
            )
            db_session.add(bill)
            db_session.commit()
        return jsonify({'id': bill.id, 'bill_no': bill.bill_no}), 201
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/invoices/<int:bill_id>/pdf')
@login_required
def api_invoice_pdf(bill_id):
    """Return invoice PDF"""
    return invoice_pdf(bill_id)

@app.route('/api/settings', methods=['GET', 'PUT'])
@login_required
def api_settings():
    if current_user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    if request.method == 'GET':
        s = get_company_settings()
        return jsonify({
            'company_name_tamil': s.company_name_tamil,
            'company_name_english': s.company_name_english,
            'gstin': s.gstin,
            'address_tamil': s.address_tamil,
            'address_english': s.address_english,
            'phone_numbers': s.phone_numbers,
            'footer_message': s.footer_message
        })
    data = request.get_json(silent=True) or {}
    s = get_company_settings()
    s.company_name_tamil = data.get('company_name_tamil', s.company_name_tamil)
    s.company_name_english = data.get('company_name_english', s.company_name_english)
    s.gstin = data.get('gstin', s.gstin)
    s.address_tamil = data.get('address_tamil', s.address_tamil)
    s.address_english = data.get('address_english', s.address_english)
    s.phone_numbers = data.get('phone_numbers', s.phone_numbers)
    s.footer_message = data.get('footer_message', s.footer_message)
    s.updated_at = datetime.utcnow()
    db_session.commit()
    return jsonify({'status': 'ok'})
@app.route('/api/customers/search')
@login_required
def api_customers_search():
    """API endpoint for customer autocomplete"""
    query = request.args.get('q', '').lower()
    customers = db_session.query(Customer).filter(
        Customer.name.ilike(f'%{query}%')
    ).limit(10).all()
    
    results = []
    for customer in customers:
        results.append({
            'id': customer.id,
            'name': customer.name,
            'gst_number': customer.gst_number or '',
            'phone': customer.phone or '',
            'address': customer.address or ''
        })
    
    return jsonify(results)

@app.route('/api/items/<int:item_id>/suggest-rate')
@login_required
def api_suggest_rate(item_id):
    """API endpoint to suggest rate based on last 3 bills"""
    suggested_rate = suggest_rate(item_id)
    item = db_session.query(Item).get(item_id)
    
    return jsonify({
        'suggested_rate': suggested_rate,
        'current_rate': item.rate if item else None
    })

# ==================== INVOICE ====================

@app.route('/invoice/<int:bill_id>')
@login_required
def invoice_detail(bill_id):
    bill = db_session.query(Bill).get(bill_id)
    if not bill:
        flash('Bill not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check access
    if current_user.role != 'admin' and bill.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    company_settings = get_company_settings()
    
    return render_template('invoice_detail.html', bill=bill, company_settings=company_settings)

@app.route('/invoice/<int:bill_id>/pdf')
@login_required
def invoice_pdf(bill_id):
    bill = db_session.query(Bill).get(bill_id)
    if not bill:
        flash('Bill not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check access
    if current_user.role != 'admin' and bill.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    company_settings = get_company_settings()

    # Use registered Tamil font or fallback (font registered at startup)
    if tamil_font_name not in pdfmetrics.getRegisteredFontNames():
        tamil_font_name = 'Helvetica'  # Fallback

    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=24)
    
    story = []
    styles = getSampleStyleSheet()

    # Typography
    header_font = tamil_font_name if tamil_font_name in pdfmetrics.getRegisteredFontNames() else 'Helvetica-Bold'
    body_font = tamil_font_name if tamil_font_name in pdfmetrics.getRegisteredFontNames() else 'Helvetica'

    title_style = ParagraphStyle('CompanyTitle', parent=styles['Heading1'], fontName=header_font, fontSize=20, textColor=colors.HexColor('#c2185b'), alignment=1, spaceAfter=6)
    subtitle_style = ParagraphStyle('SubTitle', parent=styles['Normal'], fontName=body_font, fontSize=11, alignment=1, textColor=colors.HexColor('#333'))
    label_style = ParagraphStyle('Label', parent=styles['Normal'], fontName=body_font, fontSize=10)

    # Header block (with logo left, text right-aligned)
    story.append(Paragraph(company_settings.company_name_tamil or 'ஸ்ரீ தனலட்சுமி புளூ மெட்டல்ஸ்', title_style))
    story.append(Paragraph(company_settings.company_name_english or 'Sri Dhanalakshmi Blue Metals', subtitle_style))
    story.append(Paragraph(company_settings.address_tamil or 'எண்டியூர் & எரியூர் அஞ்சல், வாணூர் தாலுகா, விழுப்புரம் மாவட்டம்', subtitle_style))

    header_table = Table([
        [Paragraph(f'GSTIN: {company_settings.gstin or "33AUXPR8335C1Z7"}', label_style),
         '', 
         Paragraph(f'மொபைல்: {company_settings.phone_numbers or "97883 88823, 97515 31619, 75026 27223"}', label_style)]
    ], colWidths=[2.5*inch, 1*inch, 2.5*inch])
    header_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'LEFT')]))
    story.append(header_table)
    story.append(Spacer(1, 10))

    # Top block (Bill meta)
    top_data = [
        [Paragraph('பில் எண் / Bill No', label_style), Paragraph(bill.bill_no, label_style),
         Paragraph('தேதி / Date', label_style), Paragraph(bill.date.strftime('%d-%m-%Y %H:%M'), label_style)],
        [Paragraph('இடம் / Place', label_style), Paragraph('நெமிலி', label_style),
         Paragraph('வாகன எண் / Vehicle No', label_style), Paragraph(bill.vehicle.vehicle_number if bill.vehicle else '-', label_style)]
    ]
    top_table = Table(top_data, colWidths=[1.4*inch, 2.0*inch, 1.4*inch, 2.2*inch])
    top_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#fde0ef'))]))
    story.append(top_table)
    story.append(Spacer(1, 8))

    # Customer block
    cust_rows = [
        [Paragraph('வாடிக்கையாளர் / Customer', label_style), Paragraph(bill.customer.name, label_style)],
        [Paragraph('GST No', label_style), Paragraph(bill.customer.gst_number or '-', label_style)]
    ]
    cust_table = Table(cust_rows, colWidths=[1.8*inch, 5.2*inch])
    cust_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black)]))
    story.append(cust_table)
    story.append(Spacer(1, 8))

    # Items table
    items_header = [Paragraph('அ/எ', label_style), Paragraph('பொருள் விவரம்', label_style), Paragraph('அளவு', label_style), Paragraph('விலை', label_style), Paragraph('தொகை', label_style)]
    items_rows = [items_header]
    items_rows.append(['1', Paragraph(bill.item.name, label_style), f'{bill.quantity:.2f}', f'₹{bill.rate:.2f}', f'₹{bill.total:.2f}'])

    items_table = Table(items_rows, colWidths=[0.6*inch, 3.6*inch, 0.9*inch, 1.0*inch, 1.0*inch])
    items_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f8bbd0')),
        ('ALIGN', (2,1), (-1,-1), 'CENTER')
    ]))
    story.append(items_table)
    story.append(Spacer(1, 8))

    # Summary with GST split
    cgst = bill.total * 0.025
    sgst = bill.total * 0.025
    summary_rows = [
        [Paragraph('Subtotal', label_style), Paragraph(f'₹{bill.total:.2f}', label_style)],
        [Paragraph('CGST 2.5%', label_style), Paragraph(f'₹{cgst:.2f}', label_style)],
        [Paragraph('SGST 2.5%', label_style), Paragraph(f'₹{sgst:.2f}', label_style)],
        [Paragraph('<b>Grand Total</b>', label_style), Paragraph(f'<b>₹{bill.grand_total:.2f}</b>', label_style)]
    ]
    summary_table = Table(summary_rows, colWidths=[5.1*inch, 1.9*inch])
    summary_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#fde0ef'))]))
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # Footer/signature
    footer_text = company_settings.footer_message or 'நன்றி!'
    story.append(Paragraph(footer_text, ParagraphStyle('Footer', parent=styles['Normal'], fontName=body_font, fontSize=10, alignment=1, textColor=colors.grey)))
    story.append(Spacer(1, 6))
    story.append(Paragraph('அங்கீகரிக்கப்பட்டவர் – ஸ்ரீ தனலட்சுமி புளு மெட்டல்ஸ்', ParagraphStyle('Sign', parent=styles['Normal'], fontName=body_font, fontSize=10, alignment=2)))
    
    # Watermark and logo on page
    from reportlab.platypus import Image as RLImage
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'img', 'logo.png')

    def draw_page(canvas, doc_obj):
        # Watermark
        try:
            if os.path.exists(logo_path):
                canvas.saveState()
                canvas.setFillAlpha(0.1)
                canvas.drawImage(logo_path, 300, 600, width=180, height=180, mask='auto', preserveAspectRatio=True, anchor='c')
                canvas.restoreState()
        except Exception:
            pass
        # Header logo top-left
        try:
            if os.path.exists(logo_path):
                canvas.drawImage(logo_path, 36, A4[1]-120, width=80, height=80, mask='auto', preserveAspectRatio=True)
        except Exception:
            pass

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{bill.bill_no}.pdf'
    )

# ==================== ADMIN - CUSTOMERS ====================

@app.route('/admin/customers')
@admin_required
def admin_customers():
    customers = db_session.query(Customer).order_by(Customer.name).all()
    return render_template('customers.html', customers=customers)

@app.route('/admin/customers/add', methods=['POST'])
@admin_required
def admin_customers_add():
    try:
        customer = Customer(
            name=request.form.get('name'),
            gst_number=request.form.get('gst_number') or None,
            phone=request.form.get('phone') or None,
            address=request.form.get('address') or None
        )
        db_session.add(customer)
        db_session.commit()
        flash('Customer added successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error adding customer: {str(e)}', 'danger')
    return redirect(url_for('admin_customers'))

@app.route('/admin/customers/<int:customer_id>/edit', methods=['POST'])
@admin_required
def admin_customers_edit(customer_id):
    try:
        customer = db_session.query(Customer).get(customer_id)
        if customer:
            customer.name = request.form.get('name')
            customer.gst_number = request.form.get('gst_number') or None
            customer.phone = request.form.get('phone') or None
            customer.address = request.form.get('address') or None
            db_session.commit()
            flash('Customer updated successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error updating customer: {str(e)}', 'danger')
    return redirect(url_for('admin_customers'))

@app.route('/admin/customers/<int:customer_id>/delete', methods=['POST'])
@admin_required
def admin_customers_delete(customer_id):
    try:
        customer = db_session.query(Customer).get(customer_id)
        if customer:
            db_session.delete(customer)
            db_session.commit()
            flash('Customer deleted successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error deleting customer: {str(e)}', 'danger')
    return redirect(url_for('admin_customers'))

# ==================== ADMIN - VEHICLES ====================

@app.route('/admin/vehicles')
@admin_required
def admin_vehicles():
    vehicles = db_session.query(Vehicle).order_by(Vehicle.vehicle_number).all()
    return render_template('vehicles.html', vehicles=vehicles)

@app.route('/admin/vehicles/add', methods=['POST'])
@admin_required
def admin_vehicles_add():
    try:
        vehicle = Vehicle(
            vehicle_number=request.form.get('vehicle_number'),
            vehicle_type=request.form.get('vehicle_type') or None
        )
        db_session.add(vehicle)
        db_session.commit()
        flash('Vehicle added successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error adding vehicle: {str(e)}', 'danger')
    return redirect(url_for('admin_vehicles'))

@app.route('/admin/vehicles/<int:vehicle_id>/edit', methods=['POST'])
@admin_required
def admin_vehicles_edit(vehicle_id):
    try:
        vehicle = db_session.query(Vehicle).get(vehicle_id)
        if vehicle:
            vehicle.vehicle_number = request.form.get('vehicle_number')
            vehicle.vehicle_type = request.form.get('vehicle_type') or None
            db_session.commit()
            flash('Vehicle updated successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error updating vehicle: {str(e)}', 'danger')
    return redirect(url_for('admin_vehicles'))

@app.route('/admin/vehicles/<int:vehicle_id>/delete', methods=['POST'])
@admin_required
def admin_vehicles_delete(vehicle_id):
    try:
        vehicle = db_session.query(Vehicle).get(vehicle_id)
        if vehicle:
            db_session.delete(vehicle)
            db_session.commit()
            flash('Vehicle deleted successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error deleting vehicle: {str(e)}', 'danger')
    return redirect(url_for('admin_vehicles'))

# ==================== ADMIN - ITEMS ====================

@app.route('/admin/items')
@admin_required
def admin_items():
    items = db_session.query(Item).order_by(Item.name).all()
    return render_template('items.html', items=items)

@app.route('/admin/items/add', methods=['POST'])
@admin_required
def admin_items_add():
    try:
        item = Item(
            name=request.form.get('name'),
            rate=float(request.form.get('rate', 0))
        )
        db_session.add(item)
        db_session.commit()
        flash('Item added successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error adding item: {str(e)}', 'danger')
    return redirect(url_for('admin_items'))

@app.route('/admin/items/<int:item_id>/edit', methods=['POST'])
@admin_required
def admin_items_edit(item_id):
    try:
        item = db_session.query(Item).get(item_id)
        if item:
            item.name = request.form.get('name')
            item.rate = float(request.form.get('rate', 0))
            item.updated_at = datetime.utcnow()
            db_session.commit()
            flash('Item updated successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error updating item: {str(e)}', 'danger')
    return redirect(url_for('admin_items'))

@app.route('/admin/items/<int:item_id>/delete', methods=['POST'])
@admin_required
def admin_items_delete(item_id):
    try:
        item = db_session.query(Item).get(item_id)
        if item:
            item.is_active = False
            db_session.commit()
            flash('Item deactivated successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error deleting item: {str(e)}', 'danger')
    return redirect(url_for('admin_items'))

# ==================== ADMIN - USERS ====================

@app.route('/admin/users')
@admin_required
def admin_users():
    users = db_session.query(User).order_by(User.username).all()
    return render_template('users.html', users=users)

@app.route('/admin/users/add', methods=['POST'])
@admin_required
def admin_users_add():
    try:
        username = request.form.get('username')
        if db_session.query(User).filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('admin_users'))
        
        user = User(
            username=username,
            password_hash=generate_password_hash(request.form.get('password')),
            role=request.form.get('role', 'user')
        )
        db_session.add(user)
        db_session.commit()
        flash('User added successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error adding user: {str(e)}', 'danger')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_users_delete(user_id):
    try:
        user = db_session.query(User).get(user_id)
        if user and user.id != current_user.id:
            db_session.delete(user)
            db_session.commit()
            flash('User deleted successfully.', 'success')
        else:
            flash('Cannot delete your own account.', 'danger')
    except Exception as e:
        db_session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
    return redirect(url_for('admin_users'))

# ==================== ADMIN - SETTINGS ====================

@app.route('/admin/settings')
@admin_required
def admin_settings():
    company_settings = get_company_settings()
    items = db_session.query(Item).filter_by(is_active=True).order_by(Item.name).all()
    users = db_session.query(User).order_by(User.username).all()
    return render_template('settings.html', company_settings=company_settings, items=items, users=users)

@app.route('/admin/settings/company', methods=['POST'])
@admin_required
def admin_settings_company():
    try:
        settings = get_company_settings()
        settings.company_name_tamil = request.form.get('company_name_tamil')
        settings.company_name_english = request.form.get('company_name_english')
        settings.address_tamil = request.form.get('address_tamil')
        settings.address_english = request.form.get('address_english')
        settings.gstin = request.form.get('gstin')
        settings.phone_numbers = request.form.get('phone_numbers')
        settings.footer_message = request.form.get('footer_message')
        settings.updated_at = datetime.utcnow()
        db_session.commit()
        flash('Company settings updated successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error updating settings: {str(e)}', 'danger')
    return redirect(url_for('admin_settings'))



# ==================== ADMIN - BILLS ====================

@app.route('/admin/bills')
@admin_required
def admin_bills():
    bills = db_session.query(Bill).order_by(desc(Bill.date)).limit(100).all()
    return render_template('bills.html', bills=bills)

@app.route('/admin/bills/export')
@admin_required
def admin_bills_export():
    bills = db_session.query(Bill).order_by(desc(Bill.date)).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Bill No', 'Date', 'Customer', 'Vehicle', 'Item', 'Quantity', 'Rate', 'Total', 'GST', 'Grand Total'])
    
    # Write data
    for bill in bills:
        writer.writerow([
            bill.bill_no,
            bill.date.strftime('%Y-%m-%d %H:%M:%S'),
            bill.customer.name,
            bill.vehicle.vehicle_number if bill.vehicle else '',
            bill.item.name,
            f'{bill.quantity:.2f}',
            f'{bill.rate:.2f}',
            f'{bill.total:.2f}',
            f'{bill.gst:.2f}',
            f'{bill.grand_total:.2f}'
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'bills_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

# ==================== DB INITIALIZATION UTILITIES ====================

@app.route('/init-db')
def init_db():
    """
    One-time route to create database tables.
    """
    try:
        Base.metadata.create_all(engine)
        return "✅ Database tables created successfully!"
    except Exception as e:
        import traceback
        return f"❌ Database initialization failed:<br><pre>{traceback.format_exc()}</pre>"

# ==================== AUTOMATION ====================

# Note: Scheduler removed for Vercel serverless compatibility
# Scheduled tasks should be handled via Vercel Cron Jobs or external services

# ==================== MAIN ====================

# Create tables at startup (safe no-op if already created)
try:
    Base.metadata.create_all(engine)
    print("✅ Tables verified/created successfully at startup.")
except Exception as e:
    print("⚠️ Database initialization error:", e)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

# For Vercel deployment
app = app
