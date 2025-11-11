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
import os
import traceback
import csv
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit

# Import models
from models import Base, User, Customer, Vehicle, Item, Bill, CompanySettings
from forecast import forecast_demand, get_forecast_insights

load_dotenv()

# Create Flask app (ensure only one instance)
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Ensure 'instance' directory exists (needed on Render for SQLite)
instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
os.makedirs(instance_path, exist_ok=True)

# Define SQLite DB path safely and auto-create file
db_path_file = os.path.join(instance_path, 'data.db')
if not os.path.exists(db_path_file):
    open(db_path_file, 'a').close()

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path_file.replace(os.sep, "/")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Runtime error log file and global error handler
LOG_FILE = '/tmp/runtime_error.log'

@app.errorhandler(Exception)
def handle_exception(e):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write("\n==== ERROR OCCURRED ====\n")
        traceback.print_exc(file=f)
    return jsonify({"error": "Internal Server Error"}), 500

@app.route("/debug-log")
def show_debug():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            return "<pre>" + f.read() + "</pre>"
    return "No errors logged yet."

engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'], echo=False)
Session = sessionmaker(bind=engine)
db_session = Session()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    return db_session.query(User).get(int(user_id))

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

# Helper function to get next bill number
def get_next_bill_no():
    last_bill = db_session.query(Bill).order_by(desc(Bill.id)).first()
    if last_bill:
        # Extract number from bill_no (format: BILL-YYYYMMDD-XXXX)
        try:
            parts = last_bill.bill_no.split('-')
            if len(parts) == 3:
                last_num = int(parts[2])
                new_num = last_num + 1
            else:
                new_num = 1
        except:
            new_num = 1
    else:
        new_num = 1
    
    bill_no = f"BILL-{datetime.now().strftime('%Y%m%d')}-{new_num:04d}"
    return bill_no

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
    
    # Get forecast insights
    forecast_insights = get_forecast_insights(db_session, Bill, Item, days=30)
    
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
                         monthly_data=monthly_data,
                         forecast_insights=forecast_insights)

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
            
            # Create bill
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
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Company header (Tamil)
    title_style = ParagraphStyle(
        'CompanyTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a237e'),
        spaceAfter=12,
        alignment=1  # Center
    )
    
    story.append(Paragraph(company_settings.company_name_tamil or 'ஸ்ரீ தனலட்சுமி புளூ மெட்டல்ஸ்', title_style))
    story.append(Spacer(1, 6))
    
    # Address (Tamil)
    address_style = ParagraphStyle(
        'AddressStyle',
        parent=styles['Normal'],
        fontSize=11,
        alignment=1
    )
    story.append(Paragraph(company_settings.address_tamil or 'நெமிலி & எண்வரடி அஞ்சல், எண்டியூர், வாணூர் தாலுகா, விழுப்புரம் மாவட்டம்.', address_style))
    story.append(Spacer(1, 6))
    
    # GST and Phone
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1
    )
    story.append(Paragraph(f'GSTIN: {company_settings.gstin or "33AUXPR8335C1Z7"}', info_style))
    story.append(Paragraph(f'மொபைல்: {company_settings.phone_numbers or "97883 88823, 97515 31619, 75026 27223"}', info_style))
    story.append(Spacer(1, 20))
    
    # Invoice details
    invoice_style = styles['Normal']
    story.append(Paragraph(f'<b>Bill Number:</b> {bill.bill_no}', invoice_style))
    story.append(Paragraph(f'<b>Date:</b> {bill.date.strftime("%d-%m-%Y %H:%M")}', invoice_style))
    story.append(Spacer(1, 12))
    
    # Customer details
    story.append(Paragraph('<b>Customer Details:</b>', invoice_style))
    story.append(Paragraph(f'Name: {bill.customer.name}', invoice_style))
    if bill.customer.gst_number:
        story.append(Paragraph(f'GST: {bill.customer.gst_number}', invoice_style))
    if bill.customer.phone:
        story.append(Paragraph(f'Phone: {bill.customer.phone}', invoice_style))
    if bill.customer.address:
        story.append(Paragraph(f'Address: {bill.customer.address}', invoice_style))
    if bill.vehicle:
        story.append(Paragraph(f'Vehicle: {bill.vehicle.vehicle_number} ({bill.vehicle.vehicle_type or ""})', invoice_style))
    story.append(Spacer(1, 12))
    
    # Items table
    data = [['S.No', 'Item Name', 'Qty', 'Rate', 'Amount', 'GST (5%)', 'Total']]
    
    data.append([
        '1',
        bill.item.name,
        f'{bill.quantity:.2f}',
        f'₹{bill.rate:.2f}',
        f'₹{bill.total:.2f}',
        f'₹{bill.gst:.2f}',
        f'₹{bill.grand_total:.2f}'
    ])
    
    # Totals
    data.append(['', '', '', '', '', '<b>Subtotal:</b>', f'<b>₹{bill.total:.2f}</b>'])
    data.append(['', '', '', '', '', '<b>GST (5%):</b>', f'<b>₹{bill.gst:.2f}</b>'])
    data.append(['', '', '', '', '', '<b>Grand Total:</b>', f'<b>₹{bill.grand_total:.2f}</b>'])
    
    table = Table(data, colWidths=[0.5*inch, 2*inch, 0.7*inch, 0.8*inch, 0.8*inch, 1*inch, 1*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -4), colors.beige),
        ('GRID', (0, 0), (-1, -4), 1, colors.black),
        ('BACKGROUND', (0, -3), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -3), (-1, -1), 'Helvetica-Bold'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 20))
    
    # Footer
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1,
        textColor=colors.grey
    )
    footer_text = company_settings.footer_message or 'நன்றி!'
    story.append(Paragraph(footer_text, footer_style))
    
    doc.build(story)
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

# ==================== ADMIN - FORECAST ====================

@app.route('/admin/forecast')
@admin_required
def admin_forecast():
    """AI Demand Forecasting page"""
    forecasts = forecast_demand(db_session, Bill, Item, days=30)
    insights = get_forecast_insights(db_session, Bill, Item, days=30)
    
    return render_template('forecast.html', forecasts=forecasts, insights=insights)

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

# ==================== AUTOMATION ====================

def daily_sales_summary():
    """Send daily sales summary email (scheduled task)"""
    try:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_bills = db_session.query(Bill).filter(Bill.date >= today_start).all()
        
        total_sales = sum([b.grand_total for b in today_bills])
        total_bills = len(today_bills)
        
        # TODO: Implement email sending
        print(f"Daily Sales Summary: {total_bills} bills, ₹{total_sales:.2f} total sales")
    except Exception as e:
        print(f"Error in daily sales summary: {e}")

def update_forecast():
    """Update forecast every Sunday midnight"""
    try:
        # Forecast is generated on-demand, but we can pre-cache it here
        print("Forecast update scheduled task executed")
    except Exception as e:
        print(f"Error updating forecast: {e}")

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=daily_sales_summary,
    trigger=CronTrigger(hour=20, minute=0),  # 8 PM daily
    id='daily_sales_summary',
    name='Daily Sales Summary Email',
    replace_existing=True
)
scheduler.add_job(
    func=update_forecast,
    trigger=CronTrigger(day_of_week='sun', hour=0, minute=0),  # Sunday midnight
    id='update_forecast',
    name='Update Forecast',
    replace_existing=True
)
scheduler.start()

# Shut down scheduler on app exit
atexit.register(lambda: scheduler.shutdown())

# ==================== MAIN ====================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
