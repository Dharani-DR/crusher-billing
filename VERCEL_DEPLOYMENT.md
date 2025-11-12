# Vercel Deployment Guide - Crusher Billing

## ✅ Vercel Compatibility Fixes Applied

### 1. Database Configuration
- **Vercel Environment**: Automatically detects Vercel and uses in-memory SQLite
- **Local Environment**: Uses file-based SQLite in `instance/data.db`
- **Fallback**: Gracefully falls back to in-memory if file operations fail

### 2. File Operations
- All file write operations wrapped in try/except blocks
- Log file uses `/tmp` (available on Vercel)
- Database file creation skipped on Vercel

### 3. Tamil Font Registration
- Font registered at startup (before PDF generation)
- Works in serverless environment
- Graceful fallback to Helvetica if font not found

### 4. Health Check Endpoint
- Added `/ping` route for Vercel health checks
- Returns: `{"status": "ok", "environment": "vercel"}`

### 5. Dependencies Optimized
- Removed `gunicorn` (not needed for Vercel)
- Removed heavy packages (APScheduler, pandas, numpy)
- Kept only essential packages

## 🚀 Deployment Steps

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Vercel-ready deployment"
   git push origin main
   ```

2. **Deploy on Vercel**
   - Go to https://vercel.com/new
   - Import your GitHub repository
   - Vercel auto-detects Python and `vercel.json`
   - Click "Deploy"

3. **Test Deployment**
   - Visit: `https://your-project.vercel.app/ping`
   - Should return: `{"status": "ok", "environment": "vercel"}`

4. **Initialize Database**
   - Visit: `https://your-project.vercel.app/setup`
   - Creates default users and sample data

## ⚠️ Important Limitations

### Database Persistence
- **In-memory SQLite**: Data is lost when function execution ends
- **Solution**: Use Vercel Postgres or external database for production

### To Use Vercel Postgres:
1. Add Vercel Postgres in Vercel Dashboard
2. Set environment variable:
   ```
   SQLALCHEMY_DATABASE_URI=postgresql://user:pass@host/dbname
   ```
3. Update `app.py` to use PostgreSQL connection string from env

### Static Files
- All static files (fonts, images) must be in the repository
- They are served from the `/static` directory

## ✅ What Works on Vercel

- ✅ All routes and templates
- ✅ Tamil font rendering (web and PDF)
- ✅ Responsive UI
- ✅ Billing and invoice generation
- ✅ PDF generation with Tamil text
- ✅ Authentication and authorization
- ✅ All CRUD operations (with persistent database)

## 🔧 Configuration Files

### `vercel.json`
```json
{
  "version": 2,
  "builds": [{ "src": "app.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "app.py" }]
}
```

### `runtime.txt`
```
python-3.12.7
```

### `requirements.txt`
- Optimized for Vercel (no heavy dependencies)
- All packages compatible with serverless

## 🧪 Local Testing

Test locally before deploying:

```bash
python app.py
```

Visit: http://127.0.0.1:5000/ping

Should return: `{"status": "ok", "environment": "local"}`

## 📝 Environment Variables

Set in Vercel Dashboard → Settings → Environment Variables:

- `SECRET_KEY`: Flask secret key (required)
- `SQLALCHEMY_DATABASE_URI`: (Optional) External database connection string
- `VERCEL`: Automatically set by Vercel (don't set manually)

## 🎯 Expected Result

After deployment:
- ✅ No 500 errors
- ✅ All routes render properly
- ✅ UI aligned and Tamil text visible
- ✅ PDF & print working (no box issue)
- ✅ Mobile responsive
- ✅ `/ping` endpoint returns OK

