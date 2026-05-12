# Import handlers for different websocket namespaces
from app.websockets import chat, counseling, dashboard, office, campus_admin, student
import logging

logger = logging.getLogger(__name__)

def init_websockets():
    """Initialize all websocket handlers"""
    logger.info("Initializing WebSocket handlers")
    logger.info("- Chat namespace (/chat) initialized")
    logger.info("- Video Counseling namespace (/video-counseling) initialized")
    logger.info("- Dashboard namespace (/dashboard) initialized")
    logger.info("- Office namespace (/office) initialized")
    logger.info("- Campus Admin namespace (/campus-admin) initialized")
    logger.info("- Student namespace (default) initialized")
    logger.info("All WebSocket namespaces initialized successfully") 