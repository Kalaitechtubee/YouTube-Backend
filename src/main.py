import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.database.connection import engine, Base
from src.workers.task_worker import start_worker_loop
from src.api.routes.media import router as media_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    # Create DB tables
    Base.metadata.create_all(bind=engine)
    
    # Launch worker queue processing loop in background
    worker_task = asyncio.create_task(start_worker_loop())
    
    yield
    
    # Shutdown actions
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Enterprise Media Downloader Platform",
    description="Clean Architecture, high-performance media parsing and merging platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include core media route handlers
app.include_router(media_router)

@app.get("/")
def read_root():
    return {
        "title": "Enterprise Media Downloader Platform API",
        "status": "online",
        "documentation": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=5000, reload=True)
