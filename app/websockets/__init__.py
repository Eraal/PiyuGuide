# Import handlers for different websocket namespaces
from app.websockets import chat, counseling, dashboard
import logging

logger = logging.getLogger(__name__)

def init_websockets():
    """Initialize all websocket handlers"""
    logger.info("Initializing WebSocket handlers")
    logger.info("- Chat namespace (/chat) initialized")
    logger.info("- Video Counseling namespace (/video-counseling) initialized")
    logger.info("- Dashboard namespace (/dashboard) initialized")
    logger.info("All WebSocket namespaces initialized successfully") 