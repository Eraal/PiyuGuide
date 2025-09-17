# PiyuGuide Production Deployment (DigitalOcean)

This guide deploys the Flask + Flask-SocketIO + WebRTC app behind Nginx with TLS, running Gunicorn (eventlet), and optional TURN via coturn.

## 1) Provision a Droplet
- Ubuntu 22.04+ LTS, 2GB RAM minimum.
- Point your domain DNS A/AAAA to the droplet.

## 2) System packages
```bash
sudo apt update && sudo apt -y install python3.12 python3.12-venv python3-pip nginx certbot python3-certbot-nginx git
```

## 3) App layout on server
```bash
sudo mkdir -p /opt/piyuguide
sudo chown -R $USER:$USER /opt/piyuguide
cd /opt/piyuguide
# Copy project here (git clone or scp)
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example /etc/piyuguide.env
sudo chown root:root /etc/piyuguide.env && sudo chmod 600 /etc/piyuguide.env
```

Edit `/etc/piyuguide.env` with strong values and your DATABASE_URL.

## 4) Gunicorn (eventlet) via systemd
```bash
sudo mkdir -p /var/log/piyuguide
sudo chown www-data:www-data /var/log/piyuguide
sudo cp deploy/gunicorn.conf.py /opt/piyuguide/gunicorn.conf.py
sudo cp deploy/systemd/piyuguide.service /etc/systemd/system/piyuguide.service
sudo systemctl daemon-reload
sudo systemctl enable --now piyuguide
sudo systemctl status piyuguide --no-pager
```

## 5) Nginx + TLS
```bash
sudo cp deploy/nginx/piyuguide.conf /etc/nginx/sites-available/piyuguide
sudo ln -s /etc/nginx/sites-available/piyuguide /etc/nginx/sites-enabled/piyuguide
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d example.com -d www.example.com
```

- Replace `example.com` in the config and certbot command.
- Ensure `/opt/piyuguide/static/` exists (copy from repo or symlink).
- To allow image/file uploads when creating campuses, set a higher body size. The provided Nginx config includes:
  
	`client_max_body_size 20M;`
  
	in both the port 80 and 443 server blocks. After editing, run `sudo nginx -t && sudo systemctl reload nginx`.

Optional (Flask app limit): Flask also enforces `MAX_CONTENT_LENGTH` (default 16MB in `app/__init__.py`). If your uploads exceed 16MB, raise it to match Nginx (e.g., 20MB) and redeploy.

## 6) Flask-SocketIO scaling (optional)
When you scale Gunicorn workers or instances, configure a message queue (Redis):
```bash
# Example
export SOCKETIO_MESSAGE_QUEUE=redis://localhost:6379/0
```
Set it in `/etc/piyuguide.env`, then `sudo systemctl restart piyuguide`.

## 7) WebRTC TURN server (recommended for NATs)
Use a managed TURN or install coturn on another droplet:
```bash
sudo apt -y install coturn
sudo sed -i 's/^#TURNSERVER_ENABLED=.*/TURNSERVER_ENABLED=1/' /etc/default/coturn
sudo bash -lc 'cat > /etc/turnserver.conf <<EOF
listening-port=3478
fingerprint
lt-cred-mech
realm=turn.example.com
user=turnuser:turnpassword
no-tlsv1
no-tlsv1_1
no-stdout-log
EOF'
sudo systemctl enable --now coturn
sudo ufw allow 3478/udp
```
Set in `/etc/piyuguide.env`:
```
TURN_URL=turn:turn.example.com:3478?transport=udp
TURN_USERNAME=turnuser
TURN_PASSWORD=turnpassword
```
Or provide a full `ICE_SERVERS_JSON` list.

## 8) Environment hardening
- Set `SOCKETIO_CORS_ALLOWED_ORIGINS` to your production origin(s).
- Set `SESSION_COOKIE_SECURE=true` and serve only over HTTPS.
- Rotate `SECRET_KEY` and any previously exposed credentials.

## 9) Logs and health
```bash
journalctl -u piyuguide -f --no-pager
sudo tail -f /var/log/piyuguide/error.log
```

If issues occur with WebRTC connectivity, verify:
- TLS is valid on your domain (wss requires https).
- TURN credentials and port 3478/udp reachability.
- Nginx forwards Upgrade/Connection headers on /socket.io/.

## 10) High-resolution profile images & caching

Profile uploads now generate responsive derivatives (128/256/512) plus a WebP and an original (max 1600px long edge, 85% quality). Filenames are timestamp+uuid based, allowing long-lived caching.

Nginx config adds for `/static/uploads/profile_pics/`:
```
add_header Cache-Control "public, max-age=2592000, immutable";
```
This lets browsers reuse images for 30 days; users who upload a new picture get a new filename (cache busting automatically).

## 11) Orphan profile image cleanup cron

A maintenance script `scripts/cleanup_profile_images.py` finds derivative sets no longer referenced by any user (older than 2 days by default) and deletes them.

Dry run (recommended first):
```bash
cd /opt/piyuguide
source venv/bin/activate
python scripts/cleanup_profile_images.py
```

Apply deletions:
```bash
python scripts/cleanup_profile_images.py --apply
```

Example cron (run daily 02:30):
```bash
sudo bash -lc 'cat > /etc/cron.d/piyuguide_profile_cleanup <<EOF
30 2 * * * root /opt/piyuguide/venv/bin/python /opt/piyuguide/scripts/cleanup_profile_images.py --apply >> /var/log/piyuguide/cleanup.log 2>&1
EOF'
sudo touch /var/log/piyuguide/cleanup.log
sudo chown www-data:www-data /var/log/piyuguide/cleanup.log || true
```

Log review:
```bash
tail -f /var/log/piyuguide/cleanup.log
```

Adjust `--days N` if you want faster reclamation or more conservative retention.

---
Keeping derivative sets lean reduces disk usage and backup size while preserving fast profile image loads for users.
