import asyncio

import typer

from app.core.configs.config import settings
from app.core.database.session import get_db


app = typer.Typer(help="Database commands")


@app.command("reset")
def reset_db():
    if not bool(getattr(settings, "DEBUG", False)):
        typer.echo("❌ Reset not allowed in production", err=True)
        raise typer.Exit(code=1)

    if not typer.confirm("Reset database (drop + create)?"):
        typer.echo("Cancelled.")
        raise typer.Exit(code=1)

    async def _run():
        # Import all model modules to ensure metadata is populated before DDL
        import app.apis.users.models  # noqa: F401

        db = get_db()
        try:
            await db.drop_tables()
            await db.create_tables()
        finally:
            await db.disconnect()

    asyncio.run(_run())
    typer.echo("✔ Database reset successfully!")
