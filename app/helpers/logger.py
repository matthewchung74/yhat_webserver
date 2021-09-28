import logging
import sys
from pathlib import Path
from typing import cast

c_handler = None
f_handler = None


def get_log(file: str = "log.txt", name: str = __file__):
    path = Path(name)
    name = path.name.replace(".py", "")
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    global c_handler
    # global f_handler

    if c_handler == None:
        c_handler = logging.StreamHandler(sys.stdout)
    # if f_handler == None:
    #     f_handler = logging.FileHandler(file)

    c_handler = cast(logging.StreamHandler, c_handler)
    # f_handler = cast(logging.FileHandler, f_handler)

    c_handler.setLevel(logging.DEBUG)
    # f_handler.setLevel(logging.DEBUG)

    c_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    f_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    c_handler.setFormatter(c_format)
    # f_handler.setFormatter(f_format)

    logger.addHandler(c_handler)
    # logger.addHandler(f_handler)
    return logger
