# Smart Expense Tracker

A modern, full-stack Finance Management SaaS Dashboard built with **Django**, **MongoDB** (PyMongo), **Chart.js**, and **Lucide Icons**. Inspired by premium Dribbble finance dashboard designs.

![Dashboard Preview](static/images/preview.png)

---

## ✨ Features

- **Dashboard** — Financial summary cards, monthly line chart, category doughnut chart, recent transactions
- **Full CRUD** — Add, edit, delete expenses with server-side validation
- **Categories** — 9 default categories + custom category creation with color picker
- **Filters** — Search, category, payment method, and date range filters
- **Reports & Analytics** — Monthly trends, category breakdown, daily spending bar chart, month-over-month comparison
- **CSV Import** — Upload CSV, preview data, validate rows, detect duplicates
- **Authentication** — Registration, login, logout with user-scoped data
- **Responsive** — Works on desktop, tablet, and mobile
- **Real Data** — All stats and charts computed from actual MongoDB data

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 4.2 |
| Database (App Data) | MongoDB via PyMongo |
| Database (Auth) | SQLite (Django default) |
| Frontend | HTML5, CSS3, JavaScript |
| Charts | Chart.js 4 |
| Icons | Lucide |
| Font | Inter (Google Fonts) |

## 📦 Prerequisites

- **Python 3.10+**
- **MongoDB 6.0+** running locally or remotely
- **pip** package manager

## 🚀 Quick Start

### 1. Clone & Install

```bash
cd "mongodb project"
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example env file and edit it:

```bash
cp .env.example .env
# Edit .env with your MongoDB URI and secret key
```

Default `.env` values work for a local MongoDB on port 27017.

### 3. Run Migrations (SQLite for auth)

```bash
python manage.py migrate
```

### 4. Start MongoDB

Make sure MongoDB is running:

```bash
# Windows (if installed as service)
net start MongoDB

# Or start manually
mongod --dbpath C:\data\db
```

### 5. (Optional) Seed Demo Data

```bash
python manage.py seed_data
# Creates user "demo" with password "demo1234" and 60 sample expenses
```

### 6. Run the Server

```bash
python manage.py runserver
```

Visit **http://127.0.0.1:8000** and register a new account or login with demo/demo1234.

## 📁 Project Structure

```
mongodb project/
├── manage.py
├── requirements.txt
├── .env / .env.example
├── config/
│   ├── settings.py          # Django settings (SQLite + MongoDB config)
│   ├── urls.py               # Root URL routing
│   └── wsgi.py
├── expenses/
│   ├── views.py              # All page views
│   ├── auth_views.py         # Registration, login, logout
│   ├── urls.py               # App URL patterns
│   ├── auth_urls.py          # Auth URL patterns
│   ├── db.py                 # MongoDB connection + indexes
│   ├── services.py           # Business logic (CRUD, stats, CSV import)
│   ├── validators.py         # Server-side validation
│   ├── tests.py              # Unit tests
│   └── management/commands/
│       └── seed_data.py      # Demo data seeder
├── templates/
│   ├── base.html             # Layout with sidebar + topbar
│   ├── dashboard.html
│   ├── transactions.html
│   ├── expense_form.html
│   ├── categories.html
│   ├── reports.html
│   ├── import_csv.html
│   ├── settings.html
│   └── registration/
│       ├── login.html
│       └── register.html
└── static/
    ├── css/style.css         # Complete design system
    └── js/dashboard.js       # Utility functions
```

## 🧪 Running Tests

```bash
python manage.py test expenses
```

Tests cover:
- Authentication flows (register, login, logout)
- Input validation (amounts, dates, payment methods)
- Protected route access control

## 🔒 Security

- CSRF protection on all forms
- Server-side validation on all inputs
- User-scoped queries (no cross-user data access)
- Passwords stored with Django's PBKDF2 hasher
- MongoDB credentials in environment variables only
- No sensitive data in frontend code

## 📊 Database Design

**MongoDB Collections:**

- `expenses` — User transactions with Decimal128 amounts
- `categories` — User categories with colors

**Indexes:**
- `(user_id, date)` — Fast date-range queries
- `(user_id, category)` — Fast category filters
- `(user_id, fingerprint)` — CSV dedup (unique, sparse)
- `(user_id, name)` on categories — Unique category names per user

## 📝 CSV Import Format

```csv
date,description,amount,category,payment_method
2024-03-15,Grocery shopping,1250.00,Food & Dining,UPI
2024-03-14,Uber ride,350.00,Transportation,Wallet
```

Required columns: `date`, `description`, `amount`
Optional: `category` (defaults to "Other"), `payment_method` (defaults to "Other")

## 📄 License

MIT License — Feel free to use and modify for your own projects.
