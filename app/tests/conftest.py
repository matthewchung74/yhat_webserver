from pathlib import Path
from dotenv import load_dotenv

# setup test env here
dotenv_path: Path = Path(__file__).parents[2] / ".env.test"
foo = load_dotenv(dotenv_path=dotenv_path, override=True)

from app.service.builder_server import builder_server
from multiprocessing import Process
import pytest

my_storage: dict = {}

# needs to be below dotenv, do not autoformat


@pytest.fixture(scope="module")
def storage():
    return my_storage


@pytest.fixture(scope="module")
def builder_job():
    proc = Process(target=builder_server.start, args=(), daemon=False, name="rabbit")
    proc.start()
    yield
    proc.terminate()
