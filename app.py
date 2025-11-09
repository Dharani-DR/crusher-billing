from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import csv
import io
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Ensure instance directory exists
instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
os.makedirs(instance_path, exist_ok=True)

# Database setup
db_file = os.path.join(instance_path, 'billing.db')
db_path = os.getenv('DATABASE_URL', f'sqlite:///{db_file.replace(os.sep, "/")}')
app.config['SQLALCHEMY_DATABASE_URI'] = db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

Base = declarative_base()
engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'], echo=False)
Session = sessionmaker(bind=engine)
db_session = Session()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Database Models
class User(UserMixin, Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default='user')  # admin or user
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    invoices = relationship('Invoice', back_populates='user')

class Item(Base):
    __tablename__ = 'items'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)  # Tamil name
    name_english = Column(String(200), nullable=True)
    price = Column(Float, nullable=False, default=3000.0)
    gst_type = Column(String(20), nullable=False, default='standard')  # standard, exempt, etc.
    gst_rate = Column(Float, nullable=False, default=5.0)  # Total GST (CGST + SGST)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    invoice_lines = relationship('InvoiceLine', back_populates='item')

class Invoice(Base):
    __tablename__ = 'invoices'
    
    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    customer_name = Column(String(200), nullable=True)
    customer_address = Column(Text, nullable=True)
    date = Column(DateTime, default=datetime.utcnow)
    subtotal = Column(Float, nullable=False, default=0.0)
    cgst_amount = Column(Float, nullable=False, default=0.0)
    sgst_amount = Column(Float, nullable=False, default=0.0)
    total = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship('User', back_populates='invoices')
    invoice_lines = relationship('InvoiceLine', back_populates='invoice', cascade='all, delete-orphan')

class InvoiceLine(Base):
    __tablename__ = 'invoice_lines'
    
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False)
    item_id = Column(Integer, ForeignKey('items.id'), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)
    gst_type = Column(String(20), nullable=False)
    gst_rate = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)
    
    invoice = relationship('Invoice', back_populates='invoice_lines')
    item = relationship('Item', back_populates='invoice_lines')

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    action = Column(String(50), nullable=False)  # create, update, delete
    table_name = Column(String(50), nullable=False)
    record_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    return db_session.query(User).get(int(user_id))

# Helper function to log admin actions
def log_admin_action(action, table_name, record_id=None, details=None):
    if current_user.is_authenticated and current_user.role == 'admin':
        log = AuditLog(
            user_id=current_user.id,
            action=action,
            table_name=table_name,
            record_id=record_id,
            details=details
        )
        db_session.add(log)
        db_session.commit()

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

# Routes
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
    """Initialize database with default users and sample items"""
    try:
        # Create tables
        Base.metadata.create_all(engine)
        
        # Check if admin already exists
        admin = db_session.query(User).filter_by(username='admin').first()
        if not admin:
            # Create default admin
            admin = User(
                username='admin',
                password_hash=generate_password_hash('adminpass'),
                role='admin'
            )
            db_session.add(admin)
            
            # Create default user
            user = User(
                username='user',
                password_hash=generate_password_hash('userpass'),
                role='user'
            )
            db_session.add(user)
            
            # Create sample items with Tamil names
            sample_items = [
                {'name': '½ ஜெல்லி', 'name_english': '1/2 Jelly', 'price': 3000.0},
                {'name': '¾ ஜெல்லி', 'name_english': '3/4 Jelly', 'price': 3000.0},
                {'name': '1" ஜெல்லி', 'name_english': '1" Jelly', 'price': 3000.0},
                {'name': '1½" ஜெல்லி', 'name_english': '1.5" Jelly', 'price': 3000.0},
                {'name': '2" ஜெல்லி', 'name_english': '2" Jelly', 'price': 3000.0},
                {'name': '40mm ஜெல்லி', 'name_english': '40mm Jelly', 'price': 3000.0},
                {'name': '20mm ஜெல்லி', 'name_english': '20mm Jelly', 'price': 3000.0},
                {'name': '12mm ஜெல்லி', 'name_english': '12mm Jelly', 'price': 3000.0},
                {'name': '6mm ஜெல்லி', 'name_english': '6mm Jelly', 'price': 3000.0},
                {'name': 'மணல்', 'name_english': 'Sand', 'price': 3000.0},
            ]
            
            for item_data in sample_items:
                item = Item(
                    name=item_data['name'],
                    name_english=item_data['name_english'],
                    price=item_data['price'],
                    gst_type='standard',
                    gst_rate=5.0  # 2.5% CGST + 2.5% SGST
                )
                db_session.add(item)
            
            db_session.commit()
            flash('Database initialized successfully! Default users created: admin/adminpass, user/userpass', 'success')
        else:
            flash('Database already initialized.', 'info')
    except Exception as e:
        db_session.rollback()
        flash(f'Error initializing database: {str(e)}', 'danger')
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    # User dashboard
    recent_invoices = db_session.query(Invoice).filter_by(user_id=current_user.id).order_by(Invoice.created_at.desc()).limit(10).all()
    
    # Calculate statistics
    total_invoices = db_session.query(Invoice).filter_by(user_id=current_user.id).count()
    total_sales = db_session.query(Invoice).filter_by(user_id=current_user.id).with_entities(db_session.query(Invoice.total).label('total')).all()
    total_sales_sum = sum([inv.total for inv in db_session.query(Invoice).filter_by(user_id=current_user.id).all()])
    
    return render_template('dashboard.html', 
                         recent_invoices=recent_invoices,
                         total_invoices=total_invoices,
                         total_sales=total_sales_sum)

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Admin dashboard statistics
    total_users = db_session.query(User).count()
    total_items = db_session.query(Item).filter_by(is_active=True).count()
    total_invoices = db_session.query(Invoice).count()
    total_sales = sum([inv.total for inv in db_session.query(Invoice).all()])
    
    recent_invoices = db_session.query(Invoice).order_by(Invoice.created_at.desc()).limit(10).all()
    recent_logs = db_session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(10).all()
    
    return render_template('admin_dashboard.html',
                         total_users=total_users,
                         total_items=total_items,
                         total_invoices=total_invoices,
                         total_sales=total_sales,
                         recent_invoices=recent_invoices,
                         recent_logs=recent_logs)

# Admin - Items Management
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
            name_english=request.form.get('name_english', ''),
            price=float(request.form.get('price', 3000)),
            gst_type=request.form.get('gst_type', 'standard'),
            gst_rate=float(request.form.get('gst_rate', 5.0))
        )
        db_session.add(item)
        db_session.commit()
        log_admin_action('create', 'items', item.id, f'Created item: {item.name}')
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
            old_price = item.price
            item.name = request.form.get('name')
            item.name_english = request.form.get('name_english', '')
            item.price = float(request.form.get('price', 3000))
            item.gst_type = request.form.get('gst_type', 'standard')
            item.gst_rate = float(request.form.get('gst_rate', 5.0))
            item.updated_at = datetime.utcnow()
            db_session.commit()
            log_admin_action('update', 'items', item.id, f'Updated item: {item.name} (price: {old_price} -> {item.price})')
            flash('Item updated successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error updating item: {str(e)}', 'danger')
    return redirect(url_for('admin_items'))

@app.route('/admin/items/<int:item_id>/update_price', methods=['POST'])
@admin_required
def admin_items_update_price(item_id):
    try:
        data = request.get_json()
        item = db_session.query(Item).get(item_id)
        if item:
            old_price = item.price
            item.price = float(data.get('price', 3000))
            item.updated_at = datetime.utcnow()
            db_session.commit()
            log_admin_action('update', 'items', item.id, f'Live price update: {old_price} -> {item.price}')
            return jsonify({'success': True, 'price': item.price})
    except Exception as e:
        db_session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': False, 'error': 'Item not found'}), 404

@app.route('/admin/items/<int:item_id>/delete', methods=['POST'])
@admin_required
def admin_items_delete(item_id):
    try:
        item = db_session.query(Item).get(item_id)
        if item:
            item_name = item.name
            item.is_active = False
            db_session.commit()
            log_admin_action('delete', 'items', item.id, f'Deactivated item: {item_name}')
            flash('Item deactivated successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error deleting item: {str(e)}', 'danger')
    return redirect(url_for('admin_items'))

# Admin - Users Management
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
        log_admin_action('create', 'users', user.id, f'Created user: {username}')
        flash('User added successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error adding user: {str(e)}', 'danger')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/edit', methods=['POST'])
@admin_required
def admin_users_edit(user_id):
    try:
        user = db_session.query(User).get(user_id)
        if user:
            old_role = user.role
            user.role = request.form.get('role', 'user')
            if request.form.get('password'):
                user.password_hash = generate_password_hash(request.form.get('password'))
            db_session.commit()
            log_admin_action('update', 'users', user.id, f'Updated user: {user.username} (role: {old_role} -> {user.role})')
            flash('User updated successfully.', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error updating user: {str(e)}', 'danger')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_users_delete(user_id):
    try:
        user = db_session.query(User).get(user_id)
        if user and user.id != current_user.id:
            username = user.username
            db_session.delete(user)
            db_session.commit()
            log_admin_action('delete', 'users', user_id, f'Deleted user: {username}')
            flash('User deleted successfully.', 'success')
        else:
            flash('Cannot delete your own account.', 'danger')
    except Exception as e:
        db_session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
    return redirect(url_for('admin_users'))

# Admin - Invoices View
@app.route('/admin/invoices')
@admin_required
def admin_invoices():
    invoices = db_session.query(Invoice).order_by(Invoice.created_at.desc()).all()
    return render_template('invoices.html', invoices=invoices)

@app.route('/admin/invoices/export')
@admin_required
def admin_invoices_export():
    invoices = db_session.query(Invoice).order_by(Invoice.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Invoice Number', 'Date', 'Customer Name', 'Subtotal', 'CGST', 'SGST', 'Total', 'Created By'])
    
    # Write data
    for invoice in invoices:
        user = db_session.query(User).get(invoice.user_id)
        writer.writerow([
            invoice.invoice_number,
            invoice.date.strftime('%Y-%m-%d %H:%M:%S'),
            invoice.customer_name or '',
            f'{invoice.subtotal:.2f}',
            f'{invoice.cgst_amount:.2f}',
            f'{invoice.sgst_amount:.2f}',
            f'{invoice.total:.2f}',
            user.username if user else ''
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'invoices_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

# Admin - Reports
@app.route('/admin/reports')
@admin_required
def admin_reports():
    period = request.args.get('period', 'month')
    
    if period == 'day':
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = datetime.now()
    elif period == 'month':
        start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = datetime.now()
    else:
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
    
    invoices = db_session.query(Invoice).filter(
        Invoice.date >= start_date,
        Invoice.date <= end_date
    ).all()
    
    total_sales = sum([inv.total for inv in invoices])
    total_invoices = len(invoices)
    total_cgst = sum([inv.cgst_amount for inv in invoices])
    total_sgst = sum([inv.sgst_amount for inv in invoices])
    
    # Daily sales data for chart
    daily_sales = {}
    for invoice in invoices:
        date_key = invoice.date.strftime('%Y-%m-%d')
        if date_key not in daily_sales:
            daily_sales[date_key] = 0
        daily_sales[date_key] += invoice.total
    
    # Item-wise sales
    item_sales = {}
    for invoice in invoices:
        for line in invoice.invoice_lines:
            item_name = line.item.name if line.item else 'Unknown'
            if item_name not in item_sales:
                item_sales[item_name] = {'quantity': 0, 'amount': 0}
            item_sales[item_name]['quantity'] += line.quantity
            item_sales[item_name]['amount'] += line.line_total
    
    return render_template('reports.html',
                         period=period,
                         invoices=invoices,
                         total_sales=total_sales,
                         total_invoices=total_invoices,
                         total_cgst=total_cgst,
                         total_sgst=total_sgst,
                         daily_sales=daily_sales,
                         item_sales=item_sales)

# Admin - Settings
@app.route('/admin/settings')
@admin_required
def admin_settings():
    return render_template('settings.html')

@app.route('/admin/settings/backup')
@admin_required
def admin_settings_backup():
    try:
        import shutil
        
        db_file = os.path.join(instance_path, 'billing.db')
        if not os.path.exists(db_file):
            flash('Database file not found.', 'danger')
            return redirect(url_for('admin_settings'))
        
        backup_filename = f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
        backup_path = os.path.join(instance_path, backup_filename)
        shutil.copy2(db_file, backup_path)
        
        log_admin_action('backup', 'database', None, f'Database backup created: {backup_filename}')
        flash(f'Backup created successfully: {backup_filename}', 'success')
    except Exception as e:
        flash(f'Error creating backup: {str(e)}', 'danger')
    return redirect(url_for('admin_settings'))

# User - Create Invoice
@app.route('/invoice/create', methods=['GET', 'POST'])
@login_required
def create_invoice():
    if request.method == 'POST':
        try:
            # Generate invoice number
            last_invoice = db_session.query(Invoice).order_by(Invoice.id.desc()).first()
            invoice_number = f'INV-{datetime.now().strftime("%Y%m%d")}-{last_invoice.id + 1 if last_invoice else 1:04d}'
            
            invoice = Invoice(
                invoice_number=invoice_number,
                user_id=current_user.id,
                customer_name=request.form.get('customer_name', ''),
                customer_address=request.form.get('customer_address', ''),
                date=datetime.now()
            )
            db_session.add(invoice)
            db_session.flush()
            
            # Process invoice lines
            items = request.form.getlist('item_id[]')
            quantities = request.form.getlist('quantity[]')
            
            subtotal = 0.0
            cgst_total = 0.0
            sgst_total = 0.0
            
            for item_id, quantity in zip(items, quantities):
                if not item_id or not quantity:
                    continue
                
                item = db_session.query(Item).get(int(item_id))
                if not item or not item.is_active:
                    continue
                
                qty = float(quantity)
                unit_price = item.price
                line_subtotal = qty * unit_price
                
                # Calculate GST (2.5% CGST + 2.5% SGST = 5% total)
                gst_rate = item.gst_rate
                if item.gst_type == 'standard':
                    cgst_rate = gst_rate / 2  # Split equally
                    sgst_rate = gst_rate / 2
                else:
                    cgst_rate = 0
                    sgst_rate = 0
                
                gst_amount = line_subtotal * (gst_rate / 100)
                cgst_amount = line_subtotal * (cgst_rate / 100)
                sgst_amount = line_subtotal * (sgst_rate / 100)
                line_total = line_subtotal + gst_amount
                
                invoice_line = InvoiceLine(
                    invoice_id=invoice.id,
                    item_id=item.id,
                    quantity=qty,
                    unit_price=unit_price,
                    gst_type=item.gst_type,
                    gst_rate=gst_rate,
                    line_total=line_total
                )
                db_session.add(invoice_line)
                
                subtotal += line_subtotal
                cgst_total += cgst_amount
                sgst_total += sgst_amount
            
            invoice.subtotal = subtotal
            invoice.cgst_amount = cgst_total
            invoice.sgst_amount = sgst_total
            invoice.total = subtotal + cgst_total + sgst_total
            
            db_session.commit()
            flash('Invoice created successfully.', 'success')
            return redirect(url_for('invoice_detail', invoice_id=invoice.id))
        except Exception as e:
            db_session.rollback()
            flash(f'Error creating invoice: {str(e)}', 'danger')
    
    items = db_session.query(Item).filter_by(is_active=True).order_by(Item.name).all()
    return render_template('create_invoice.html', items=items)

@app.route('/invoice/<int:invoice_id>')
@login_required
def invoice_detail(invoice_id):
    invoice = db_session.query(Invoice).get(invoice_id)
    if not invoice:
        flash('Invoice not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check access
    if current_user.role != 'admin' and invoice.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('invoice_detail.html', invoice=invoice)

@app.route('/invoice/<int:invoice_id>/pdf')
@login_required
def invoice_pdf(invoice_id):
    invoice = db_session.query(Invoice).get(invoice_id)
    if not invoice:
        flash('Invoice not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check access
    if current_user.role != 'admin' and invoice.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#E91E63'),
        spaceAfter=30,
        alignment=1  # Center
    )
    story.append(Paragraph('CRUSHER PLANT BILL', title_style))
    story.append(Spacer(1, 12))
    
    # Company details
    company_style = ParagraphStyle(
        'CompanyStyle',
        parent=styles['Normal'],
        fontSize=12,
        alignment=1
    )
    story.append(Paragraph('Crusher Plant Company', company_style))
    story.append(Paragraph('Address Line 1, City, State', company_style))
    story.append(Paragraph('Phone: +91-XXXXXXXXXX | Email: info@crusher.com', company_style))
    story.append(Spacer(1, 20))
    
    # Invoice details
    info_style = styles['Normal']
    story.append(Paragraph(f'<b>Invoice Number:</b> {invoice.invoice_number}', info_style))
    story.append(Paragraph(f'<b>Date:</b> {invoice.date.strftime("%d-%m-%Y %H:%M")}', info_style))
    if invoice.customer_name:
        story.append(Paragraph(f'<b>Customer:</b> {invoice.customer_name}', info_style))
    if invoice.customer_address:
        story.append(Paragraph(f'<b>Address:</b> {invoice.customer_address}', info_style))
    story.append(Spacer(1, 20))
    
    # Items table
    data = [['S.No', 'Item Name (Tamil)', 'Qty', 'Rate', 'Amount', 'GST', 'Total']]
    
    for idx, line in enumerate(invoice.invoice_lines, 1):
        item_name = line.item.name if line.item else 'Unknown'
        gst_text = f'{line.gst_rate}%' if line.gst_type == 'standard' else 'Exempt'
        data.append([
            str(idx),
            item_name,
            f'{line.quantity:.2f}',
            f'₹{line.unit_price:.2f}',
            f'₹{line.quantity * line.unit_price:.2f}',
            gst_text,
            f'₹{line.line_total:.2f}'
        ])
    
    # Totals
    data.append(['', '', '', '', '', '<b>Subtotal:</b>', f'<b>₹{invoice.subtotal:.2f}</b>'])
    data.append(['', '', '', '', '', '<b>CGST (2.5%):</b>', f'<b>₹{invoice.cgst_amount:.2f}</b>'])
    data.append(['', '', '', '', '', '<b>SGST (2.5%):</b>', f'<b>₹{invoice.sgst_amount:.2f}</b>'])
    data.append(['', '', '', '', '', '<b>Grand Total:</b>', f'<b>₹{invoice.total:.2f}</b>'])
    
    table = Table(data, colWidths=[0.5*inch, 2*inch, 0.7*inch, 0.8*inch, 0.8*inch, 1*inch, 1*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E91E63')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -5), colors.beige),
        ('GRID', (0, 0), (-1, -5), 1, colors.black),
        ('BACKGROUND', (0, -4), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -4), (-1, -1), 'Helvetica-Bold'),
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
    story.append(Paragraph('Thank you for your business!', footer_style))
    
    doc.build(story)
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{invoice.invoice_number}.pdf'
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

