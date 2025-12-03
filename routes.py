from fastapi import FastAPI, HTTPException
from typing import Callable, Any, Dict

from config import ZONES
from fetchers import fetch_srinagar_gov, get_zone_data

def register_zone_routes(app: FastAPI) -> None:
    def _make_zone_handler(z: Dict[str, Any]) -> Callable[[], Any]:
        provider = z.get("provider", "")
        z_type = z.get("zone_type", "hills") 
        
        if provider == "cpcb_data_gov":
            async def _handler():
                return await fetch_srinagar_gov()
        else:
            async def _handler():
                return await get_zone_data(
                    z["id"], 
                    z["name"], 
                    z["lat"], 
                    z["lon"],
                    z_type
                )
        return _handler

    for zid, z in ZONES.items():
        if zid == "srinagar_gov":
            path = "/aqi/srinagar"
        else:
            path = f"/aqi/{zid}"
        handler = _make_zone_handler(z)
        app.get(path)(handler)

    @app.get("/aqi/zone/{zone_id}")
    async def get_zone_aqi(zone_id: str):
        if zone_id not in ZONES:
            raise HTTPException(status_code=404, detail="zone not found")
        z = ZONES[zone_id]
        provider = z.get("provider", "")
        z_type = z.get("zone_type", "hills")

        if provider == "cpcb_data_gov":
            return await fetch_srinagar_gov()
        
        return await get_zone_data(
            z["id"], 
            z["name"], 
            z["lat"], 
            z["lon"], 
            z_type
        )

    @app.get("/zones")
    async def list_zones() -> dict:
        return {
            "zones": [
                {
                    "id": z["id"],
                    "name": z["name"],
                    "provider": z.get("provider"),
                    "lat": z.get("lat"),
                    "lon": z.get("lon"),
                    "zone_type": z.get("zone_type", "hills")
                }
                for z in ZONES.values()
            ]
        }