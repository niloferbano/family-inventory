# # cli/user.py
# import asyncio
# import typer
# from app.apis.users.service import create_user
# from app.core.database.session import get_session
# from app.apis.users.schema import UserCreate

# app = typer.Typer(help="User management commands")


# @app.command("create")
# def create_user_command(
#     username: str = typer.Option(..., prompt=True),
#     email: str = typer.Option(..., prompt=True),
#     password: str = typer.Option(..., prompt=True, hide_input=True),
# ):
#     """Create a user from CLI."""
#     async def run():
#         async for session in get_session():
#             user_data = UserCreate(username=username, email=email, password=password)
#             user = await create_user(session, user_data)
#             print(f"✔ User created: {user.id} ({user.username})")

#     asyncio.run(run())
