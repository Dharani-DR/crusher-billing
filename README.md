# Crusher Billing System

A full-stack Flask web application for managing crusher plant billing with admin and user roles.

## Features

- **Admin Features**:
  - Manage items with Tamil names
  - Manage users and roles
  - View all invoices
  - Export invoices to CSV
  - Sales reports (daily/monthly)
  - GST configuration
  - Database backup
  - Audit logs

- **User Features**:
  - Create invoices
  - Auto-calculate GST (CGST 2.5%, SGST 2.5%)
  - Print/save invoices (PDF/HTML)
  - View recent invoices

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Initialize the database:
```bash
python app.py
```
Then visit `/setup` to initialize the database with default users.

3. Default credentials:
   - Admin: `admin` / `adminpass`
   - User: `user` / `userpass`

## Running

```bash
python app.py
```

The application will run on `http://localhost:5000`

## Project Structure

```
crusher-billing/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables
├── instance/
│   └── billing.db        # SQLite database
├── templates/            # HTML templates
└── static/               # CSS, JS, images
```

