import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from routes import register_zone_routes
from fetchers import update_all_zones_background

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(periodic_updates())
    yield
    task.cancel()

async def periodic_updates():
    while True:
        try:
            await update_all_zones_background()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"CRITICAL: Background loop error: {e}")
        
        # Wait 15 minutes
        await asyncio.sleep(900)

app = FastAPI(title="breathe backend", lifespan=lifespan)

register_zone_routes(app)