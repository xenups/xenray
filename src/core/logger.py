import os
import sys

from loguru import logger

from src.core.constants import TMPDIR

# Configure logger
logger.remove() # Remove default handler

# Add stderr handler only if available (not in windowed exe)
if sys.stderr:
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG"
    )

# Add file handler
log_file = os.path.join(TMPDIR, "xenray.log")
logger.add(
    log_file,
    rotation="1 MB",
    retention="10 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG"
)

def get_logger():
    return logger
