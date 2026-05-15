# Gunicorn config for PiyuGuide
import multiprocessing

bind = "127.0.0.1:8000"
# Use exactly 1 worker. Flask-SocketIO with eventlet REQUIRES 1 worker
# when no Redis message queue is configured. Multiple workers cause 
# 400 Bad Request errors because WebSocket handshakes hit different processes.
workers = 1
worker_class = "eventlet"
# threads has no effect with eventlet; cooperative concurrency comes from eventlet

# Timeouts (WebRTC sessions can be long-lived); also allow slower DB-heavy pages
timeout = 180
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "/var/log/piyuguide/access.log"
errorlog = "/var/log/piyuguide/error.log"
loglevel = "info"
capture_output = True

# Performance tuning
preload_app = False
# Recycle workers periodically to mitigate memory bloat/leaks
max_requests = 500
max_requests_jitter = 50
