# CyberTrust KSA - AI-Powered Cybersecurity Compliance Platform

## Overview

CyberTrust KSA is an AI-powered continuous cybersecurity compliance platform designed for Saudi Arabian enterprises. It automates compliance assessments against NCA ECC, Aramco SACS-002, and SABIC CyberTrust frameworks using OpenAI LLM and OCR technology.

## Key Features

| Feature | Description |
|---------|-------------|
| AI Classification Engine | Automatically determines applicable controls based on company profile |
| OCR Document Analysis | Extracts text from uploaded PDFs and images using Tesseract |
| AI Evidence Auditing | OpenAI-powered analysis of compliance evidence with bilingual verdicts |
| Gap Analysis | Predictive risk scoring and remediation prioritization |
| Cross-Framework Mapping | 334 controls mapped across NCA, Aramco, and SABIC |
| Role-Based Dashboards | Executive, Compliance Officer, IT/Security, BU Manager views |
| Auditor Portal | Dedicated interface for certified auditors |
| Continuous Monitoring | Daily score updates and real-time alerts |

## Technology Stack

- **Backend:** Python 3.11+ / Django 6.0
- **AI Engine:** OpenAI GPT-4o (configurable)
- **OCR:** Tesseract + pdf2image
- **Database:** SQLite (dev) / PostgreSQL (production)
- **Frontend:** Django Templates + Tailwind CSS
- **Task Queue:** Celery + Redis (for async AI processing)
- **API:** Django REST Framework

## Quick Start

```bash
# Clone the project
git clone <repository-url>
cd cybertrust_django

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Install system dependencies (Ubuntu)
sudo apt-get install tesseract-ocr tesseract-ocr-ara poppler-utils

# Configure environment
cp .env.example .env
# Edit .env with your OpenAI API key

# Run migrations
python manage.py migrate

# Seed compliance controls database
python manage.py seed_controls

# Create admin user
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

## Environment Variables

Create a `.env` file in the project root:

```env
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL=gpt-4o
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1
```

## Project Structure

```
cybertrust_django/
├── core/               # User management, registration, authentication
├── compliance/         # Controls database, evidence upload, AI analysis
├── ai_engine/          # OpenAI integration, OCR, classification, gap analysis
├── dashboard/          # Role-specific dashboards
├── auditor_portal/     # Auditor review interface
├── monitoring/         # Continuous compliance monitoring
├── cybertrust_ksa/     # Django project settings
├── templates/          # HTML templates (Tailwind CSS)
├── static/             # Static assets
├── media/              # Uploaded files
└── manage.py
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page |
| `/register/` | GET/POST | Company registration |
| `/login/` | GET/POST | User login |
| `/dashboard/` | GET | Role-based dashboard |
| `/compliance/controls/` | GET | Controls list |
| `/compliance/control/<id>/` | GET/POST | Control detail + evidence upload |
| `/ai/classify/` | POST | AI company classification |
| `/ai/gap-analysis/` | GET | AI gap analysis |
| `/auditor/` | GET | Auditor dashboard |
| `/monitoring/` | GET | Compliance monitoring hub |
| `/admin/` | GET | Django admin panel |

## AI Engine Architecture

The AI engine uses OpenAI's GPT-4o model for three core functions:

1. **Company Classification:** Analyzes sector, size, and vendor targets to determine applicable control sets and risk levels.

2. **Evidence Auditing:** Processes uploaded documents via OCR, then uses AI to determine compliance status with detailed reasoning in Arabic and English.

3. **Gap Analysis:** Calculates compliance scores per framework, identifies critical gaps, and provides prioritized remediation roadmaps.

## Deployment (Production)

For production deployment:

```bash
# Use PostgreSQL
pip install psycopg2-binary

# Update settings
export DATABASE_URL=postgresql://user:pass@host:5432/cybertrust_ksa
export DEBUG=False
export ALLOWED_HOSTS=your-domain.com

# Collect static files
python manage.py collectstatic

# Run with Gunicorn
gunicorn cybertrust_ksa.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

## Admin Credentials (Development)

- **Email:** admin@cybertrust.sa
- **Password:** CyberTrust2024!

## License

Proprietary - CyberTrust KSA. All rights reserved.
