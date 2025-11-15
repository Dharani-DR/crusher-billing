# Crusher Billing - Glassmorphic Upgrade (Tamil + English)

This update modernizes the UI, adds Tamil print/PDF support, integrates logo branding, and hardens security without changing routes, APIs, or database models.

## What's New (Vercel-Ready Upgrade)

- ✅ **Vercel Deployment Ready** - Configured with `vercel.json` and optimized dependencies
- ✅ **Modern UI/UX** - TailwindCSS with glass-style cards, responsive design
- ✅ **Tamil Font Support** - Google Fonts (Noto Sans Tamil) + local font fallback
- ✅ **Bilingual UI** - Tamil-English labels throughout, perfectly aligned layouts
- ✅ **Print/PDF Fixes** - Proper Tamil font rendering in PDFs and print pages
- ✅ **Mobile Responsive** - Sticky bottom buttons, auto-collapsing layouts
- ✅ **Security Enhanced** - Flask-Talisman, CSRF protection, rate limiting, secure cookies
- ✅ **Optimized Dependencies** - Removed heavy packages (APScheduler, pandas, numpy) for Vercel

## Assets to Provide
1) Place these files (recommended sizes):
- `static/fonts/NotoSansTamil-Regular.ttf` (Google Noto Tamil)
- `static/img/logo.png` (square transparent PNG, e.g., 512x512)
- Optional: `static/img/logo.webp` (used by browsers that support it)

2) Font source:
- Notofonts Tamil releases: https://github.com/notofonts/tamil/releases

## Development
Create and activate a virtual environment, then install requirements:

```bash
pip install -r requirements.txt
```

Run locally:

```bash
python app.py
```

Initialize DB (one-time):

```
/setup
```

## Deployment
- Use gunicorn:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

- Ensure `.env` is not committed; we load values via `python-dotenv`. Required:
  - `SECRET_KEY`

- Upload `static/fonts/NotoSansTamil-Regular.ttf` and `static/img/logo.png`.

## Security
- HTTPS and CSP enforced via Flask-Talisman
- CSRF protection (`flask-wtf`) – hidden field `csrf_token` added in forms
- Rate limiting (`Flask-Limiter`) – login attempts limited (5/min)
- Hardened cookies:
  - `SESSION_COOKIE_SECURE=True`
  - `SESSION_COOKIE_HTTPONLY=True`
  - `SESSION_COOKIE_SAMESITE='Lax'`

## Printing and PDF
- HTML print optimized in `static/css/glass.css` `@media print` section
- ReportLab registers `NotoTamil` from `static/fonts/NotoSansTamil-Regular.ttf`
- PDF includes:
  - Header (Tamil + English, GSTIN, Phones, Address)
  - Top-left logo (80x80)
  - Watermark logo at 10% opacity
  - CGST/SGST split (2.5% each)

## Extra Utilities
- Daily DB backup (APScheduler) to `instance/backups/`
- `scripts/init_bill_counter.py` to check/initialize billing counter

## Notes
- All original routes/APIs preserved.
- Autocomplete endpoints in use:
  - `/api/customers/search`
  - `/api/vehicles?q=`
- Vehicle number validated via regex `^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$`.

## Branding
- Navbar: small logo + bilingual name
- Dashboard: watermark corner logo
- Invoice: top-left logo + watermark + Tamil first header

# Sri Dhanalakshmi Blue Metals – Crusher Billing System

A comprehensive, mobile-responsive GST billing platform for crusher plant business management.

## Features

- ✅ **Customer & Vehicle Management** - Manage customers with GST numbers and vehicle information
- ✅ **Billing System** - Create bills with auto-calculated GST and round-off adjustments
- ✅ **Tamil-English Bilingual Invoices** - Professional invoices with company details in both languages
- ✅ **PDF Generation** - Download invoices as PDF
- ✅ **Admin Dashboard** - Comprehensive dashboard with charts and statistics
- ✅ **AI Demand Forecasting** - Facebook Prophet-based demand forecasting for next 30 days
- ✅ **Automated Tasks** - Daily sales summary emails and weekly forecast updates
- ✅ **Mobile Responsive** - Works seamlessly on mobile, tablet, and desktop

## Tech Stack

- **Backend**: Flask 3.0.0
- **Database**: PostgreSQL with SQLAlchemy ORM (via DATABASE_URL)
- **Authentication**: Flask-Login
- **PDF Generation**: ReportLab
- **AI Forecasting**: Facebook Prophet
- **Scheduling**: APScheduler
- **Frontend**: Bootstrap 5, Chart.js
- **Deployment**: Vercel (serverless) or Gunicorn (Render)

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd crusher-billing
   ```

2. **Create virtual environment** (Python 3.12 recommended)
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Set up PostgreSQL database**
   - Create a PostgreSQL database (e.g., using Neon, Supabase, or local PostgreSQL)
   - Set the `DATABASE_URL` environment variable:
     ```bash
     export DATABASE_URL="postgresql://user:password@host:port/database"
     ```
   - Run Alembic migrations:
     ```bash
     alembic upgrade head
     ```
   - Initialize default data (optional):
     ```bash
     python scripts/init_db.py
     ```

6. **Run the application**
   ```bash
   python app.py
   ```

   Or with Gunicorn (production):
   ```bash
   gunicorn app:app
   ```

## Default Credentials

- **Admin**: username: `admin`, password: `admin123`
- **User**: username: `user`, password: `user123`

**⚠️ Change these passwords immediately in production!**

## Project Structure

```
crusher-billing/
├── app.py                 # Main Flask application
├── models.py             # SQLAlchemy database models
├── forecast.py          # AI demand forecasting logic
├── requirements.txt     # Python dependencies
├── Procfile             # Render deployment configuration
├── .env.example        # Environment variables template
├── templates/          # Jinja2 HTML templates
│   ├── base.html
│   ├── billing.html
│   ├── invoice_detail.html
│   ├── admin_dashboard.html
│   ├── forecast.html
│   └── ...
└── static/             # CSS, JS, and assets
    ├── css/
    └── js/
```

## Key Features Explained

### Billing System
- Customer autocomplete from existing customers
- Auto-fill GST number when customer is selected
- Rate suggestion based on last 3 bills of the same item
- Real-time total calculation with GST (5%)
- Round-off adjustment support

### Invoice Generation
- Tamil-English bilingual layout
- Company header with Tamil text
- Auto-generated bill numbers (BILL-YYYYMMDD-XXXX)
- Print, PDF download, and WhatsApp sharing options

### Admin Dashboard
- Daily, monthly, and total sales statistics
- Monthly sales chart (Chart.js)
- Top customers and top-selling items
- AI demand forecast insights

### AI Demand Forecasting
- Uses Facebook Prophet for time-series forecasting
- Predicts next 30 days of demand by item
- Provides insights in Tamil and English
- Auto-updates every Sunday midnight

### Automation
- Daily sales summary email at 8 PM (configurable)
- Weekly forecast update on Sunday midnight
- Auto rate suggestion based on historical data

## Deployment

### Deployment on Vercel (Recommended)

1. **Push your code to GitHub**
   ```bash
   git add .
   git commit -m "Ready for Vercel deployment"
   git push origin main
   ```

2. **Go to [Vercel](https://vercel.com/new)**
   - Click "Import Project"
   - Select your GitHub repository
   - Vercel will auto-detect the Python runtime and `@vercel/python` builder

3. **Configure Environment Variables** (if needed):
   - `SECRET_KEY`: Generate a secure secret key
   - Add any other required environment variables

4. **Deploy**
   - Vercel will automatically:
     - Detect `vercel.json` configuration
     - Use Python 3.12.7 (from `runtime.txt`)
     - Install dependencies from `requirements.txt`
     - Deploy your Flask app

5. **Configure Environment Variables in Vercel Dashboard**:
   - `DATABASE_URL`: Your PostgreSQL connection string (required)
     - Example: `postgresql://user:password@host:port/database`
     - For Neon: Copy connection string from Neon dashboard
     - For Vercel Postgres: Automatically provided when you add Vercel Postgres
   - `SECRET_KEY`: Generate a secure secret key for Flask sessions

6. **Run Database Migrations**:
   - After first deployment, run migrations:
     ```bash
     alembic upgrade head
     ```
   - Or use Vercel CLI: `vercel env pull` then `alembic upgrade head`

7. **Access your app**
   - After deployment, visit: `https://your-project.vercel.app`
   - Default admin credentials: `admin` / `nrd`

**Important Notes for Vercel Deployment**:

- **Database**: PostgreSQL is required. The app uses `DATABASE_URL` environment variable.
  - **Recommended**: Neon (free tier available) or Vercel Postgres
  - Connection pooling is configured automatically
  
- **Scheduled Tasks**: APScheduler removed for serverless compatibility. Use Vercel Cron Jobs or external services.

- **File Storage**: Static files (fonts, images) must be in the repository.

### Deployment on Render

1. **Create a new Web Service** on Render
2. **Connect your repository**
3. **Add PostgreSQL Database** (if not already added)
   - Render provides a PostgreSQL database automatically
   - Copy the `DATABASE_URL` from the database dashboard
4. **Set environment variables**:
   - `DATABASE_URL`: PostgreSQL connection string (from Render database)
   - `SECRET_KEY`: Generate a secure secret key
5. **Build Command**: `pip install -r requirements.txt && alembic upgrade head`
6. **Start Command**: `gunicorn app:app`

## Database Models

- **User**: Authentication and user management
- **Customer**: Customer information with GST numbers
- **Vehicle**: Vehicle number and type
- **Item**: Items with rates
- **Bill**: Billing records with relationships to Customer, Vehicle, and Item
- **CompanySettings**: Company information for invoices

## API Endpoints

- `GET /api/customers/search?q=<query>` - Customer autocomplete
- `GET /api/items/<id>/suggest-rate` - Rate suggestion for item

## License

This project is proprietary software for Sri Dhanalakshmi Blue Metals.

## Support

For issues or questions, please contact the development team.
