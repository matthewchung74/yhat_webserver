import logging
import sys
from pathlib import Path
from typing import cast
import os

c_handler = None
f_handler = None


def get_log(file: str = "log.txt", name: str = __file__):
    path = Path(name)
    name = path.name.replace(".py", "")
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    global c_handler
    global f_handler

    if c_handler == None:
        c_handler = logging.StreamHandler(sys.stderr)

    c_handler = cast(logging.StreamHandler, c_handler)
    c_handler.setLevel(logging.DEBUG)
    c_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    c_handler.setFormatter(c_format)
    logger.addHandler(c_handler)

    if "local" not in os.getenv("PARAM_STORE"):
        return logger

    if f_handler == None:
        f_handler = logging.FileHandler(file)

    f_handler = cast(logging.FileHandler, f_handler)

    f_handler.setLevel(logging.DEBUG)

    f_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    f_handler.setFormatter(f_format)
    logger.addHandler(f_handler)
    return logger
