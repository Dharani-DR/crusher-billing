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
from sqlalchemy import desc
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
import os
import io

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

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Invoice(db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(200), nullable=False)
    vehicle_no = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ------------------------------------------------------------
# Database initialisation helpers
# ------------------------------------------------------------
def init_db():
    """Create tables and seed default admin if needed."""
    try:
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                password_hash=generate_password_hash("admin"),
                role="admin",
            )
            db.session.add(admin)
            db.session.commit()
        return True
    except Exception as err:
        print("⚠️ DB initialisation error:", err)
        return False


@app.before_request
def ensure_database():
    init_db()


# ------------------------------------------------------------
# Routes
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


@app.route("/dashboard")
@login_required
def dashboard():
    invoices = Invoice.query.order_by(desc(Invoice.created_at)).all()
    total_sales = sum(inv.amount for inv in invoices)
    return render_template(
        "dashboard.html",
        invoices=invoices,
        total_sales=total_sales,
        user=current_user.username,
    )


@app.route("/create_invoice", methods=["POST"])
@login_required
def create_invoice():
    try:
        customer = request.form.get("customer_name", "").strip()
        vehicle = request.form.get("vehicle_no", "").strip()
        amount = float(request.form.get("amount", 0) or 0)
        date = request.form.get("date", "").strip()

        if not customer or not vehicle or amount <= 0 or not date:
            flash("தவறான விவரங்கள் / Invalid invoice details", "danger")
            return redirect(url_for("dashboard"))

        invoice = Invoice(
            customer_name=customer,
            vehicle_no=vehicle,
            amount=amount,
            date=date,
        )
        db.session.add(invoice)
        db.session.commit()
        flash("Invoice created successfully", "success")
    except Exception as err:
        db.session.rollback()
        flash("Failed to create invoice", "danger")
        print("⚠️ create_invoice error:", err)
    return redirect(url_for("dashboard"))


@app.route("/invoice/<int:invoice_id>/pdf")
@login_required
def invoice_pdf(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    if "TamilFont" in pdfmetrics.getRegisteredFontNames():
        c.setFont("TamilFont", 14)
    else:
        c.setFont("Helvetica", 14)

    c.drawString(60, 800, "ஸ்ரீ தனலட்சுமி புளு மெட்டல்ஸ் (Sree Dhanalakshmi Blue Metals)")
    c.drawString(60, 770, f"வாடிக்கையாளர் / Customer: {invoice.customer_name}")
    c.drawString(60, 745, f"வாகன எண் / Vehicle: {invoice.vehicle_no}")
    c.drawString(60, 720, f"தொகை / Amount: ₹{invoice.amount}")
    c.drawString(60, 695, f"தேதி / Date: {invoice.date}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return send_file(
        buffer,
        download_name=f"invoice_{invoice_id}.pdf",
        as_attachment=True,
        mimetype="application/pdf",
    )


@app.route("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
    flash("Logged out", "info")
    return redirect(url_for("login"))


@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})


# ------------------------------------------------------------
# Error handling
# ------------------------------------------------------------
@app.errorhandler(Exception)
def handle_exception(err):
    print("⚠️", err)
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
