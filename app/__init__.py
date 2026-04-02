import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .utils import resource_path
from .config import load_config, initialize_download_dir
from .state import state
from . import routes

app = FastAPI()

static_dir = resource_path("static")
if not os.path.exists(static_dir):
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

saved_dir, _ = load_config()
state.download_dir = initialize_download_dir(saved_dir)

app.include_router(routes.router)
