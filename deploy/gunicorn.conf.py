# Gunicorn config for PiyuGuide
import multiprocessing

bind = "127.0.0.1:8000"
workers = 1  # Start with 1; scale with message_queue (Redis) if adding more
worker_class = "eventlet"
# threads has no effect with eventlet; cooperative concurrency comes from eventlet

# Timeouts (WebRTC sessions can be long-lived)
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "/var/log/piyuguide/access.log"
errorlog = "/var/log/piyuguide/error.log"
loglevel = "info"
capture_output = True

# Performance tuning
preload_app = False
