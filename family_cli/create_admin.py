# family_cli/user.py
import asyncio

import typer
from sqlalchemy import select

from app.apis.users.models import User
from app.core.database.session import get_db
from app.iam.password_service import PasswordService

app = typer.Typer(help="User management commands")


@app.command("create-admin")
def create_admin(
    username: str = typer.Option(..., prompt=True),
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, confirmation_prompt=True
    ),
):
    """
    Create a super admin user.
    """

    async def _run():
        db = get_db()

        async with db.sessionmaker() as session:
            stmt = select(User).where(
                (User.username == username) | (User.email == email)
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                typer.echo("❌ User with this username/email already exists.")
                return

            admin = User(
                username=username,
                email=email,
                hashed_password=PasswordService.hash(password),
                is_active=True,
                is_admin=True,
            )

            session.add(admin)
            await session.commit()
            await session.refresh(admin)

            typer.echo(f"✅ Admin created successfully (id={admin.id})")

    asyncio.run(_run())
