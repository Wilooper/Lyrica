import logging
from src.config import LOG_LEVEL

def get_logger(name="Lyrica"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(level)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(levelname)s] %(asctime)s [%(name)s] - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    # Gunicorn configures the root logger; without this every line is emitted
    # twice (once by our handler, once by the root handler).
    logger.propagate = False
    return logger
