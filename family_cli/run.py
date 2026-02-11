import typer
import uvicorn
from uvicorn.config import LOGGING_CONFIG

from app.core.configs.config import settings

app = typer.Typer(help="Run the Family Inventory server")


def make_uvicorn_log_config():
    cfg = dict(LOGGING_CONFIG)  # shallow copy is fine; we’ll only tweak dict values
    cfg["loggers"] = dict(cfg.get("loggers", {}))

    # Disable HTTP access log
    cfg["loggers"]["uvicorn.access"] = {
        "handlers": ["access"],
        "level": "WARNING",
        "propagate": False,
    }

    # Silence websocket connect/disconnect noise
    cfg["loggers"]["uvicorn.error"] = {
        "handlers": ["default"],
        "level": "WARNING",
        "propagate": False,
    }
    cfg["loggers"]["websockets"] = {
        "handlers": ["default"],
        "level": "WARNING",
        "propagate": False,
    }
    cfg["loggers"]["websockets.server"] = {
        "handlers": ["default"],
        "level": "WARNING",
        "propagate": False,
    }
    cfg["loggers"]["websockets.protocol"] = {
        "handlers": ["default"],
        "level": "WARNING",
        "propagate": False,
    }

    return cfg


@app.command("server")
def run_server(
    host: str = settings.HOST,
    port: int = settings.PORT,
    reload: bool = settings.DEBUG,
    workers: int = settings.WORKERS,
):
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level="info",  # keep your app logs
        access_log=False,  # still good to keep
        log_config=make_uvicorn_log_config(),
    )
