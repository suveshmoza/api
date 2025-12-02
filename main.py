import asyncio
import os
from typing import Dict, Any, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Breathe Backend (v1 - US AQI)")

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

###### US AQI CALCULATION LOGIC ######

AQI_BREAKPOINTS = {
    "pm2_5": [
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 350.4, 301, 400),
        (350.5, 500.4, 401, 500),
    ],
    "pm10": [
        (0, 54, 0, 50),
        (55, 154, 51, 100),
        (155, 254, 101, 150),
        (255, 354, 151, 200),
        (355, 424, 201, 300),
        (425, 504, 301, 400),
        (505, 604, 401, 500),
    ],
    "co": [
        (0.0, 4.4, 0, 50),
        (4.5, 9.4, 51, 100),
        (9.5, 12.4, 101, 150),
        (12.5, 15.4, 151, 200),
        (15.5, 30.4, 201, 300),
        (30.5, 40.4, 301, 400),
        (40.5, 50.4, 401, 500),
    ],
    "no2": [
        (0, 53, 0, 50),
        (54, 100, 51, 100),
        (101, 360, 101, 150),
        (361, 649, 151, 200),
        (650, 1249, 201, 300),
        (1250, 1649, 301, 400),
        (1650, 2049, 401, 500),
    ],
    "so2": [
        (0, 35, 0, 50),
        (36, 75, 51, 100),
        (76, 185, 101, 150),
        (186, 304, 151, 200),
        (305, 604, 201, 300),
        (605, 804, 301, 400),
        (805, 1004, 401, 500),
    ],
    "o3": [
        (0, 54, 0, 50),
        (55, 70, 51, 100),
        (71, 85, 101, 150),
        (86, 105, 151, 200),
        (106, 200, 201, 300),
        (201, 604, 301, 500),
    ]
}

def linear_interpolate(c: float, bp: Tuple[float, float, int, int]) -> int:
    c_lo, c_hi, i_lo, i_hi = bp
    if c_hi - c_lo == 0:
        return i_lo
    val = ((i_hi - i_lo) / (c_hi - c_lo)) * (c - c_lo) + i_lo
    return int(round(val))

def get_single_pollutant_aqi(pollutant: str, conc: float) -> Optional[int]:
    if pollutant not in AQI_BREAKPOINTS:
        return None
    
    # handle bounds
    bps = AQI_BREAKPOINTS[pollutant]
    if conc < bps[0][0]: 
        return 0
    
    for bp in bps:
        if bp[0] <= conc <= bp[1]:
            return linear_interpolate(conc, bp)
            
    last_bp = bps[-1]
    if conc > last_bp[1]:
        return last_bp[3]
        
    return None

def convert_to_us_units(pollutant: str, val_ugm3: float) -> float:
    if pollutant == "co":
        return val_ugm3 / 1145.0
    elif pollutant == "no2":
        return val_ugm3 / 1.88
    elif pollutant == "so2":
        return val_ugm3 / 2.62
    elif pollutant == "o3":
        return val_ugm3 / 1.96
    return val_ugm3

def calculate_overall_aqi(pollutants_ugm3: Dict[str, float]) -> Dict[str, Any]:
    aqi_details = {}
    concentrations_formatted = {}

    key_map = {
        "pm2.5": "pm2_5", "pm2_5": "pm2_5", "pm25": "pm2_5",
        "pm10": "pm10",
        "co": "co",
        "no2": "no2",
        "so2": "so2",
        "o3": "o3", "ozone": "o3"
    }

    for raw_key, val in pollutants_ugm3.items():
        k = raw_key.lower()
        if k in key_map:
            internal_key = key_map[k]

            converted_val = convert_to_us_units(internal_key, val)
            concentrations_formatted[internal_key] = round(converted_val, 2)

            aqi_val = get_single_pollutant_aqi(internal_key, converted_val)
            if aqi_val is not None:
                aqi_details[internal_key] = aqi_val

    overall_aqi = 0
    main_pollutant = "n/a"
    
    if aqi_details:
        main_pollutant = max(aqi_details, key=aqi_details.get)
        overall_aqi = aqi_details[main_pollutant]

    return {
        "us_aqi": overall_aqi,
        "main_pollutant": main_pollutant,
        "aqi_breakdown": aqi_details,
        "concentrations_us_units": concentrations_formatted,
        "concentrations_raw_ugm3": pollutants_ugm3
    }

###### ENDPOINTS ######

@app.get("/zones")
def list_zones() -> Dict[str, Any]:
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

async def fetch_srinagar_gov() -> Dict[str, Any]:
    if not DATA_GOV_API_KEY:
        raise HTTPException(status_code=500, detail="DATA_GOV_API_KEY not configured")

    resource_id = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
    params = {
        "api-key": DATA_GOV_API_KEY,
        "format": "json",
        "limit": 100,
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

    # extract raw pollutants
    raw_pollutants = {}
    last_update = None
    lat = None
    lon = None

    for rec in records:
        p_id = rec.get("pollutant_id")
        avg_value = rec.get("avg_value")
        
        if p_id and avg_value not in (None, "NA"):
            try:
                raw_pollutants[p_id] = float(avg_value)
            except ValueError:
                pass

        last_update = rec.get("last_update", last_update)
        lat = float(rec.get("latitude")) if rec.get("latitude") else lat
        lon = float(rec.get("longitude")) if rec.get("longitude") else lon

    # Calculate US AQI
    aqi_data = calculate_overall_aqi(raw_pollutants)

    return {
        "zone_id": "srinagar_gov",
        "zone_name": "Srinagar (Rajbagh - JKSPCB)",
        "source": "CPCB (data.gov.in)",
        "last_update": last_update,
        "coordinates": {"lat": lat, "lon": lon},
        **aqi_data
    }

async def fetch_jammu_openweather(lat: float, lon: float) -> Dict[str, Any]:
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
    dt = entry.get("dt")
    
    # keys: co, no, no2, o3, so2, pm2_5, pm10, nh3
    raw_comps = entry.get("components", {})
    
    # calculate US AQI
    aqi_data = calculate_overall_aqi(raw_comps)

    return {
        "zone_id": "jammu_gandhinagar",
        "zone_name": "Gandhi Nagar / Trikuta Nagar, Jammu",
        "source": "OpenWeather Air Pollution API",
        "timestamp_unix": dt,
        "coordinates": {"lat": lat, "lon": lon},
        **aqi_data
    }

@app.get("/aqi/srinagar")
async def get_srinagar_aqi():
    return await fetch_srinagar_gov()

@app.get("/aqi/jammu-gandhinagar")
async def get_jammu_aqi():
    z = ZONES["jammu_gandhinagar"]
    return await fetch_jammu_openweather(z["lat"], z["lon"])