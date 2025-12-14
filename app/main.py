import uvicorn
from fastapi import FastAPI

from app.apis.homes.router import router as homes_router
from app.apis.homeuser.router import router as home_user_router
from app.apis.inventory.router import router as inventory_router
from app.apis.users.router import router as users_router
from app.core.exception_handlers import register_exception_handlers

app = FastAPI(title="Family-Inventory")
app.include_router(router=users_router)
app.include_router(router=homes_router)
app.include_router(router=home_user_router)
app.include_router(router=inventory_router)

register_exception_handlers(app)


@app.get("/")
async def read_root():
    return {"message": "Hello from Family Inventory API!"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=5000, log_level="info")
