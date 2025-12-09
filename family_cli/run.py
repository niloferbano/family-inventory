import typer
import uvicorn
from app.core.configs.config import settings
app = typer.Typer(help="Run the Family Inventory server")


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
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level="info",
        access_log=False,
        workers=workers,
    )