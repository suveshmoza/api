import os
from typing import Dict, Any

import httpx
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Breathe Backend (v0)")

DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY")
OWM_API_KEY = os.getenv("OWM_API_KEY")

if not DATA_GOV_API_KEY:
    print("WARNING: DATA_GOV_API_KEY not set")
if not OWM_API_KEY:
    print("WARNING: OWM_API_KEY not set")

###### ZONE DEFINITIONS ######

ZONES = {
    "srinagar_gov": {
        "id": "srinagar_gov",
        "name": "Srinagar (Rajbagh - JKSPCB)",
        "provider": "cpcb_data_gov",
        "lat": 34.066206,
        "lon": 74.819820,
    },
    "jammu_gandhinagar": {
        "id": "jammu_gandhinagar",
        "name": "Gandhi Nagar / Trikuta Nagar, Jammu",
        "provider": "openweather",
        "lat": 32.7100,
        "lon": 74.8605,
    },
}

@app.get("/zones")
def listZones() -> Dict[str, Any]:
    """Return list of available zones (for UI)"""
    return {
        "zones": [
            {
                "id": z["id"],
                "name": z["name"],
                "provider": z["provider"],
                "lat": z["lat"],
                "lon": z["lon"],
            }
            for z in ZONES.values()
        ]
    }

async def fetchSrinagarGov() -> Dict[str, Any]:
    """
    Fetch raw pollutant data for Srinagar (Rajbagh) from data.gov.in CPCB API.
    We don't calculate NAQI yet, just return pollutants and metadata
    """
    if not DATA_GOV_API_KEY:
        raise HTTPException(status_code=500, detail="DATA_GOV_API_KEY not configured")

    resource_id = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"

    params = {
        "api-key": DATA_GOV_API_KEY,
        "format": "json",
        "limit": 100,
        "offset": 0,
        "filters[state]": "Jammu_and_Kashmir",
        "filters[city]": "Srinagar",
        "filters[station]": "Rajbagh, Srinagar - JKSPCB",
    }

    url = f"https://api.data.gov.in/resource/{resource_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="data.gov.in request failed")

    data = r.json()

    records = data.get("records", [])
    if not records:
        raise HTTPException(status_code=404, detail="No CPCB data for Srinagar found")

    # Build a pollutants dict
    pollutants = {}
    last_update = None
    lat = None
    lon = None

    for rec in records:
        pollutant_id = rec.get("pollutant_id")
        avg_value = rec.get("avg_value")
        if pollutant_id and avg_value not in (None, "NA"):
            try:
                pollutants[pollutant_id] = float(avg_value)
            except ValueError:
                pass

        last_update = rec.get("last_update", last_update)
        lat = float(rec.get("latitude")) if rec.get("latitude") else lat
        lon = float(rec.get("longitude")) if rec.get("longitude") else lon

    return {
        "zone_id": "srinagar_gov",
        "zone_name": "Srinagar (Rajbagh - JKSPCB)",
        "source": "CPCB (data.gov.in)",
        "last_update": last_update,
        "coordinates": {"lat": lat, "lon": lon},
        "pollutants": pollutants,
    }

async def fetchJammuOpenWeather(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fetch AQI and pollutant data for a Jammu subzone from OpenWeather Air Pollution API.
    """
    if not OWM_API_KEY:
        raise HTTPException(status_code=500, detail="OWM_API_KEY not configured")

    url = "https://api.openweathermap.org/data/2.5/air_pollution"
    params = {"lat": lat, "lon": lon, "appid": OWM_API_KEY}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="OpenWeather request failed")

    data = r.json()
    lst = data.get("list", [])
    if not lst:
        raise HTTPException(status_code=404, detail="No OpenWeather AQ data")

    entry = lst[0]
    main = entry.get("main", {})
    comps = entry.get("components", {})
    dt = entry.get("dt")

    return {
        "zone_id": "jammu_gandhinagar",
        "zone_name": "Gandhi Nagar / Trikuta Nagar, Jammu",
        "source": "OpenWeather Air Pollution API",
        "aqi_openweather_scale": main.get("aqi"),
        "timestamp_unix": dt,
        "coordinates": {"lat": lat, "lon": lon},
        "pollutants": comps,
    }

@app.get("/aqi/srinagar")
async def getSrinagarApi():
    """
    Returns official CPCB pollutants for Srinagar (Rajbagh).
    """
    return await fetchSrinagarGov()

@app.get("/aqi/jammu-gandhinagar")
async def getJammuApi():
    """
    Returns modelled AQI and pollutants for Gandhi Nagar / Trikuta Nagar zone.
    """
    z = ZONES["jammu_gandhinagar"]
    return await fetchJammuOpenWeather(z["lat"], z["lon"])