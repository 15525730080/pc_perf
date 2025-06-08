from logging import getLogger, INFO, StreamHandler, Formatter
from concurrent_log_handler import ConcurrentRotatingFileHandler
import os

log = getLogger(__name__)
# Use an absolute path to prevent file rotation trouble.
logfile = os.path.abspath("log.log")
# Rotate log after reaching 512K, keep 5 old copies.
rotateHandler = ConcurrentRotatingFileHandler(logfile, "a", 512 * 1024 * 1024, 1)
log.addHandler(rotateHandler)
log.setLevel(INFO)
streamHandler = StreamHandler()
streamHandler.setLevel(INFO)
streamHandler.setFormatter(Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'  # 日志格式
))
log.addHandler(streamHandler)
