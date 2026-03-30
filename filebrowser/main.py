import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from filebrowser.config import settings
from filebrowser.routes import auth, files, locations

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)
# Suppress noisy third-party DEBUG output that floods the journal when our
# log level is set to debug.  We only want debug detail from our own code.
logging.getLogger("python_multipart").setLevel(logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Filebrowser starting (log_level=%s)", settings.log_level)

app = FastAPI(title="File Browser", docs_url=None, redoc_url=None)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a JSON 500 response for any unhandled exception."""
    logger.exception("Unhandled exception for %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
    )


app.include_router(auth.router)
app.include_router(files.router)
app.include_router(locations.router)

if settings.terminal_enabled:
    from filebrowser.routes import terminal

    app.include_router(terminal.router)

static_dir = Path(__file__).parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
