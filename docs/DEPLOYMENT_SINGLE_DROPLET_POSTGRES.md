# Single-Droplet Deployment: Flask + Socket.IO + PostgreSQL + Nginx (Ubuntu 22.04)

This guide deploys the app and PostgreSQL on one DigitalOcean droplet. You’ll manage the DB with pgAdmin from your Windows PC.

Prereqs
- Droplet: Ubuntu 22.04, 2 vCPU / 2 GB RAM / 90 GB disk
- Domain DNS A/AAAA pointing to the droplet (optional but recommended)
- Your Windows PC with pgAdmin 4 installed

1) SSH to the droplet
- From Windows (PowerShell):
  ssh root@YOUR_DROPLET_IP

2) System setup
  sudo apt update && sudo apt -y upgrade
  sudo apt -y install python3.12 python3.12-venv python3-pip git nginx certbot python3-certbot-nginx postgresql postgresql-contrib

3) Create the app directory and deploy files
  sudo mkdir -p /opt/piyuguide
  sudo chown -R $USER:$USER /opt/piyuguide
  cd /opt/piyuguide
  # Clone your repo or copy via scp
  git clone https://github.com/<you>/PiyuGuide.git .

4) Python environment and dependencies
  python3.12 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt

5) PostgreSQL: create DB and user (local on droplet)
  sudo -u postgres psql -c "CREATE USER piyu WITH PASSWORD 'ChangeThisDbPassword';"
  sudo -u postgres psql -c "CREATE DATABASE piyuguide OWNER piyu;"
  # Optional: enforce UTF8
  sudo -u postgres psql -d piyuguide -c "ALTER DATABASE piyuguide SET client_encoding TO 'UTF8';"

6) Initialize schema
- Copy schema.txt and run it:
  sudo -u postgres psql -d piyuguide -f /opt/piyuguide/schema.txt

7) App configuration
- Create environment file and secure it:
  sudo cp .env.example /etc/piyuguide.env
  sudo nano /etc/piyuguide.env
    - SECRET_KEY: set to a long random string
    - DATABASE_URL: postgresql+psycopg2://piyu:ChangeThisDbPassword@localhost/piyuguide
    - SOCKETIO_CORS_ALLOWED_ORIGINS: https://yourdomain.com (or your IP for testing)
    - SESSION_COOKIE_SECURE=true
  sudo chown root:root /etc/piyuguide.env && sudo chmod 600 /etc/piyuguide.env

8) Gunicorn (eventlet) via systemd
  sudo mkdir -p /var/log/piyuguide
  sudo chown www-data:www-data /var/log/piyuguide
  sudo cp deploy/gunicorn.conf.py /opt/piyuguide/gunicorn.conf.py
  sudo cp deploy/systemd/piyuguide.service /etc/systemd/system/piyuguide.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now piyuguide
  sudo systemctl status piyuguide --no-pager

9) Nginx + TLS (optional but recommended)
- Update deploy/nginx/piyuguide.conf with your domain; then
  sudo cp deploy/nginx/piyuguide.conf /etc/nginx/sites-available/piyuguide
  sudo ln -s /etc/nginx/sites-available/piyuguide /etc/nginx/sites-enabled/piyuguide
  sudo nginx -t && sudo systemctl reload nginx
  # TLS with certbot (replace example.com)
  sudo certbot --nginx -d example.com -d www.example.com

10) Static files
- Nginx serves /opt/piyuguide/static/
- Ensure that directory exists in your repo (it does). No extra step needed.

11) Firewall (UFW)
  sudo ufw allow OpenSSH
  sudo ufw allow 'Nginx Full'
  sudo ufw enable
  sudo ufw status

12) pgAdmin from Windows to your droplet PostgreSQL
- For security, don’t expose PostgreSQL (5432) to the internet. Use an SSH tunnel:
- In PowerShell (local PC):
  ssh -L 5433:localhost:5432 root@YOUR_DROPLET_IP
- Leave the tunnel running. In pgAdmin, add a new server:
  - Name: DO droplet
  - Host: localhost
  - Port: 5433
  - Maintenance DB: postgres
  - Username: piyu (or postgres if needed)
  - Password: ChangeThisDbPassword
- Alternatively, create a dedicated SSH Tunnel in pgAdmin connection settings and set local bind.

13) Health and logs
  journalctl -u piyuguide -f --no-pager
  sudo tail -f /var/log/piyuguide/error.log
  sudo tail -f /var/log/nginx/error.log

14) Upgrades and deployments
- Pull latest code and restart:
  cd /opt/piyuguide
  git pull --ff-only
  source venv/bin/activate && pip install -r requirements.txt
  sudo systemctl restart piyuguide

Notes
- WebRTC across NAT may require TURN; configure TURN_* or ICE_SERVERS_JSON in /etc/piyuguide.env
- For multiple workers, add Redis and set SOCKETIO_MESSAGE_QUEUE
- Keep your environment file secret (chmod 600)
