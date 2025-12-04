import httpx
import asyncio
from datetime import datetime
from fastapi import HTTPException
from typing import Dict, Any

from config import ZONES
from conversions import calculate_overall_aqi

_RAM_CACHE = {}
CACHE_DURATION = 900  # 15 minutes


async def fetch_openmeteo_live(lat: float, lon: float) -> Dict[str, float]:
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm10,pm2_5,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide,ozone",
        "timezone": "auto",
        "timeformat": "unixtime",
        "past_days": 1 
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
        
        if r.status_code != 200:
            print(f"OpenMeteo Error: {r.text}")
            raise HTTPException(status_code=502, detail="openmeteo request failed")

        data = r.json()
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        
        if not times:
            raise HTTPException(status_code=404, detail="no openmeteo aq data found")

        # Get current UTC timestamp
        now_ts = datetime.now().timestamp()
        
        # Find the timestamp in the list that is closest to NOW
        closest_ts = min(times, key=lambda t: abs(t - now_ts))
        target_idx = times.index(closest_ts)

        raw_comps = {
            "pm10": hourly.get("pm10", [])[target_idx],
            "pm2_5": hourly.get("pm2_5", [])[target_idx],
            "no2": hourly.get("nitrogen_dioxide", [])[target_idx],
            "so2": hourly.get("sulphur_dioxide", [])[target_idx],
            "co": hourly.get("carbon_monoxide", [])[target_idx],
            "o3": hourly.get("ozone", [])[target_idx]
        }

        return {k: v for k, v in raw_comps.items() if v is not None}

async def get_zone_data(zone_id: str, zone_name: str, lat: float, lon: float, zone_type: str, force_refresh: bool = False):
    cached_data = _RAM_CACHE.get(zone_id)
    current_time = datetime.now().timestamp()

    if cached_data and not force_refresh:
        last_fetched = cached_data.get("timestamp_unix", 0)
        if current_time - last_fetched < CACHE_DURATION:
            return cached_data

    try:
        raw_comps = await fetch_openmeteo_live(lat, lon)
        
        aqi_data = calculate_overall_aqi(raw_comps, zone_type=zone_type)
        
        full_payload = {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "source": "openmeteo air pollution api",
            "timestamp_unix": current_time,
            "coordinates": {"lat": lat, "lon": lon},
            **aqi_data
        }

        _RAM_CACHE[zone_id] = full_payload
        
        return full_payload
        
    except Exception as e:
        print(f"Live fetch failed for {zone_id}: {e}")
        if cached_data:
            return cached_data
        raise e

async def start_background_loop():
    print("--- Background Scheduler Started ---")
    while True:
        try:
            await update_all_zones_background()
        except Exception as e:
            print(f"Error in background loop: {e}")

        await asyncio.sleep(CACHE_DURATION)

async def update_all_zones_background():
    print(f"--- Updating Zones at {datetime.now()} ---")
    for zone_id, z in ZONES.items():
        try:
            await get_zone_data(
                z["id"], 
                z["name"], 
                z["lat"], 
                z["lon"], 
                z.get("zone_type", "hills"),
                force_refresh=True 
            )
            print(f"Updated: {zone_id}")
            await asyncio.sleep(1) 
        except Exception as e:
            print(f"Failed to update {zone_id}: {e}")
    print("--- Update Cycle Complete ---")