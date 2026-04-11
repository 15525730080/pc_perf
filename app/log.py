# coding: utf-8
import logging
import sys

_fmt = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_fmt)

log = logging.getLogger("client-perf")
log.setLevel(logging.INFO)
if not log.handlers:
    log.addHandler(_handler)
