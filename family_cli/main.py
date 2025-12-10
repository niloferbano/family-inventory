import typer

from family_cli import create_admin, reset_db, run

app = typer.Typer(help="Family Inventory CLI")

print("Adding db typer...")
app.add_typer(reset_db.app, name="db")
app.add_typer(run.app, name="run")
app.add_typer(create_admin.app, name="user")


if __name__ == "__main__":
    app()
