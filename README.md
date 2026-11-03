<div align="center">

# 🎓 PiyuGuide Web Application

### A university inquiry and counseling platform that connects students with the right campus office

[![Flask](https://img.shields.io/badge/Flask-2.3.3-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-psycopg2-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![WebRTC](https://img.shields.io/badge/Video-WebRTC-333333?logo=webrtc&logoColor=white)](https://webrtc.org/)
[![WebSocket](https://img.shields.io/badge/Realtime-Flask--SocketIO-010101?logo=socketdotio&logoColor=white)](https://flask-socketio.readthedocs.io/)
[![Tailwind CSS](https://img.shields.io/badge/UI-Tailwind%20CSS-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![Deployment](https://img.shields.io/badge/Deployment-Nginx%20%2B%20Gunicorn-009639?logo=nginx&logoColor=white)](https://gunicorn.org/)
[![License](https://img.shields.io/badge/license-not%20specified-lightgrey)](#-project-status)

</div>

> **Portfolio project by Gerald Pandaan** — BS Information Technology graduate, Cum Laude.

## 📌 Table of Contents

- [About](#-about)
- [Screenshots / Demo](#-screenshots--demo)
- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [System Architecture](#-system-architecture)
- [Getting Started](#-getting-started)
- [Project Structure](#-project-structure)
- [Related Repositories](#-related-repositories)
- [Project Status](#-project-status)
- [Author](#-author)

## 💡 About

PiyuGuide is a campus inquiry and counseling system designed to make university support easier to access. Students can find offices, submit questions, track responses, and request counseling sessions from one platform instead of switching between disconnected channels.

The web application is the original capstone platform. It serves students, office staff, campus administrators, and super administrators through role-based workflows, with real-time chat and browser-based video counseling supported by the same Flask backend used by the companion mobile application.

## 🖼️ Screenshots / Demo

| Landing / campus selection | Student dashboard | Inquiry conversation |
|---|---|---|
| ![Landing page](/assets/screenshots/landing.png) | ![Student dashboard](/assets/screenshots/student-dashboard.png) | ![Inquiry chat](/assets/screenshots/inquiry-chat.png) |

| Counseling session | Office dashboard | Administration |
|---|---|---|
| ![Counseling session](/assets/screenshots/counseling.png) | ![Office dashboard](/assets/screenshots/office-dashboard.png) | ![Admin dashboard](/assets/screenshots/admin-dashboard.png) |

## ✨ Key Features

### 🎓 Students

- Campus-aware landing pages and university office directory
- Account registration, email verification, login, and profile management
- Submit inquiries to university offices and follow their status
- Real-time inquiry messaging with attachments and notifications
- Browse counseling availability and request counseling sessions
- Join video counseling sessions with WebRTC media controls
- View announcements, notifications, feedback, and session history

### 🏢 Office administrators and counselors

- Office dashboard with inquiry and activity summaries
- Review, respond to, and manage student inquiries
- Real-time office chat and notification updates
- Configure concern types and counseling concern types
- Manage counseling availability, appointments, feedback, and video sessions
- Publish office announcements and review office reports
- Manage office team members and account settings

### 🛡️ Campus and system administrators

- Campus-admin dashboards, office statistics, and inquiry oversight
- Manage departments, offices, office administrators, concern types, and students
- Manage campus announcements and account lock history
- Configure system branding, campus themes, logos, and landing backgrounds
- Super-admin campus management, administration, settings, and audit logs

## 🧰 Tech Stack

| Area | Technologies |
|---|---|
| Web application | Python, Flask, Jinja2, Flask-Login, Flask-WTF |
| Backend | Flask application factory, role-based blueprints, Flask-SQLAlchemy |
| Database | PostgreSQL, psycopg2, SQLAlchemy, Flask-Migrate/Alembic |
| Real-time | Flask-SocketIO, Eventlet, WebSocket events for chat, dashboards, notifications, and counseling |
| Video | WebRTC browser sessions with configurable STUN/TURN ICE servers |
| Frontend | Server-rendered HTML, Tailwind CSS, custom CSS, local Font Awesome assets |
| Email | Flask-Mail with SMTP/Brevo-compatible configuration |
| Deployment | Ubuntu server, Nginx reverse proxy, Gunicorn with Eventlet, systemd |

## 🏗️ System Architecture

```mermaid
flowchart LR
    B[Student / Staff Browser]
    M[React Native + Expo<br/>Companion Mobile App]
    N[Nginx<br/>TLS + Reverse Proxy]
    APP[Flask Application<br/>Role-based web + mobile routes]
    DB[(PostgreSQL)]
    SOCKET[Flask-SocketIO / WebSocket<br/>Chat, notifications, dashboards]
    SIGNAL[WebRTC signaling<br/>Session offers, answers, ICE]
    RTC[WebRTC peer media<br/>Audio + video]
    MAIL[SMTP / Brevo<br/>Verification and email]

    B -->|HTTPS| N
    M -->|HTTPS| N
    N --> APP
    APP --> DB
    B <-->|Socket.IO events| SOCKET
    M <-->|Socket.IO events| SOCKET
    APP --> SOCKET
    B <-->|Signaling messages| SIGNAL
    M <-->|Signaling messages| SIGNAL
    B <-->|Peer audio/video| RTC
    M <-->|Peer audio/video| RTC
    APP --> MAIL
```

## 🚀 Getting Started

### Prerequisites

- Python and `pip`
- PostgreSQL
- Node.js and npm for Tailwind CSS assets
- A configured SMTP account for email verification and notifications
- Optional STUN/TURN infrastructure for cross-network WebRTC calls

### 1. Clone the repository

```bash
git clone https://github.com/Eraal/PiyuGuide.git
cd PiyuGuide
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Configure environment variables

Copy the included template and replace the placeholders:

```bash
cp .env.example .env
```

At minimum, configure a strong secret key and a PostgreSQL connection:

```dotenv
SECRET_KEY=replace-with-a-random-secret
DATABASE_URL=postgresql+psycopg2://user:password@localhost/piyuguide
SESSION_COOKIE_SECURE=false
SOCKETIO_ASYNC_MODE=eventlet
HOST=127.0.0.1
PORT=5000
DEBUG=1
```

For production, also configure HTTPS cookie settings, allowed Socket.IO origins, SMTP credentials, and TURN/ICE settings in the environment. Never commit real secrets.

### 4. Prepare the database

Create the PostgreSQL database, then apply migrations:

```bash
flask db upgrade
```

The repository also includes `init_database.sql` and the migration configuration under `migrations/` for database setup and schema history.

### 5. Build frontend assets

```bash
npm run build:css
```

Use the watcher during CSS development:

```bash
npm run watch:css
```

### 6. Run locally

```bash
python run.py
```

Open `http://127.0.0.1:5000` in a browser. The development entry point reads `HOST`, `PORT`, and `DEBUG` from the environment.

### Production deployment

The repository includes deployment examples under `deploy/`:

- `deploy/nginx/piyuguide.conf` — HTTPS, static files, reverse proxy, and Socket.IO upgrade handling
- `deploy/gunicorn.conf.py` — one Eventlet worker and long-lived connection settings
- `deploy/systemd/piyuguide.service` — service definition using `/etc/piyuguide.env`

The reference production layout runs Gunicorn on `127.0.0.1:8000` behind Nginx on an Ubuntu server.

## 🗂️ Project Structure

<details>
<summary>Expand the main folder tree</summary>

```text
PiyuGuide/
├── app/
│   ├── auth/                 # Authentication and verification routes
│   ├── main/                 # Public landing, campus, and office pages
│   ├── student/              # Student dashboards and workflows
│   ├── office/               # Office admin and counselor workflows
│   ├── admin/                # Campus-admin workflows
│   ├── super_admin/          # System-wide administration
│   ├── mobile/               # Mobile client API routes
│   ├── websockets/           # Chat, counseling, dashboard, and presence events
│   ├── models.py             # SQLAlchemy models
│   ├── extensions.py         # Database, Socket.IO, migration, and mail extensions
│   └── __init__.py           # Flask application factory
├── templates/                # Jinja templates grouped by role
├── static/                   # CSS, images, uploads, sounds, and web fonts
├── migrations/               # Flask-Migrate/Alembic configuration and revisions
├── deploy/                   # Nginx, Gunicorn, and systemd deployment files
├── scripts/                  # Maintenance, email, and regression utilities
├── config.py                 # Environment-backed application configuration
├── run.py                    # Local development entry point
├── requirements.txt          # Python dependencies
├── package.json              # Tailwind CSS scripts and dependency
└── .env.example              # Environment variable template
```

</details>

## 🔗 Related Repositories

- **[PiyuGuide Mobile Application](https://github.com/Eraal/PiyuGuide---Mobile-Application)** — React Native/Expo student client.

The web and mobile applications connect to the same Flask backend, PostgreSQL database, Socket.IO events, and WebRTC counseling flows. This repository contains the original browser-based capstone platform; the mobile repository provides a focused student experience for phones.

## 📍 Project Status

PiyuGuide is a portfolio and capstone project with deployment configuration for an Ubuntu server. The public demo backend may be offline or unavailable at times, so authentication, chat, notifications, email, and video sessions are not guaranteed to be continuously available. The companion mobile application is not currently published on the Google Play Store. A repository license file has not been specified yet.

## 👤 Author

**Gerald Pandaan** — BS Information Technology graduate, Cum Laude  
GitHub: [@Eraal](https://github.com/Eraal) · [LinkedIn](https://linkedin.com/in/gerald-pandaan-27b53b2a9/) · [Portfolio](https://my-portfolio-livid-tau-gerald.vercel.app) · [Email](mailto:geraldnazpandaan1@gmail.com)
