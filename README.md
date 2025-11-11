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
- **Database**: SQLAlchemy ORM (SQLite locally, PostgreSQL on Render)
- **Authentication**: Flask-Login
- **PDF Generation**: ReportLab
- **AI Forecasting**: Facebook Prophet
- **Scheduling**: APScheduler
- **Frontend**: Bootstrap 5, Chart.js
- **Deployment**: Gunicorn (Render)

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

5. **Initialize database**
   - Visit `http://localhost:5000/setup` in your browser
   - This creates the database and default users:
     - Admin: `admin` / `admin123`
     - User: `user` / `user123`

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

## Deployment on Render

1. **Create a new Web Service** on Render
2. **Connect your repository**
3. **Set environment variables**:
   - `SECRET_KEY`: Generate a secure secret key
   - `DATABASE_URL`: PostgreSQL connection string (provided by Render)
4. **Build Command**: `pip install -r requirements.txt`
5. **Start Command**: `gunicorn app:app`

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
