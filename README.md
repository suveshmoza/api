# Breathe backend
A modular FastAPI backend designed to retrieve and standardize air quality data across the Jammu & Kashmir region for the **Breathe** app. The system aggregates data from multiple providers: **OpenMeteo** for satellite-based estimates in most districts and the **Central Pollution Control Board** (CPCB) for ground station data in Srinagar.

## Structure
```breathe/
├─ api/
│  ├─ main.py
│  ├─ routes.py
│  ├─ fetchers.py
│  ├─ conversions.py
│  ├─ config.py
│  ├─ zones.json
│  ├─ aqi_breakpoints.json
│  └─ .env
```

## Main modules
- `main.py`
  Initializes the FastAPI application and starts a background scheduler. This scheduler runs every 15 minutes to fetch fresh data for all zones, ensuring the app serves cached data instantly without hitting API rate limits during user requests.
- `routes.py`
  Generates all `/aqi/<zone>` endpoints dynamically based on`zones.json`. Also exposes `/aqi/zone/{zone_id}`.
- `fetchers.py`
   contains data fetch logic.
   `fetch_openmeteo_live` queries the OpenMeteo Air Quality API for a precise real-time satellite-based pollutant data.
   `get_zone_data` implements the caching strategy. it checks the internal server memory (RAM) first. If data is missing or older than 15 minutes, it fetches fresh data from the provider and updates the cache.
- `conversions.py`
  Handles the mathematics of AQI calculation.
  - Converts Carbon Monoxide (CO) from µg/m³ to mg/m³ to match Indian standards.
  - Maps raw concentrations to the official Indian CPCB sub-indices.
  - Determines the final AQI based on the dominant pollutant.
- `config.py`
  loads environment variables, zones.json, and aqi_breakpoints.json.
- `zones.json`
  contains all zone definitions with fixed ids, names, providers, and coordinates.
- `aqi_breakpoints.json`
  contains all us epa breakpoint tables for pm2.5, pm10, co, no2, so2, and o3.

## Requirements
- python ≥ 3.10
- fastapi
- httpx
- python-dotenv
- uvicorn

## Environment variables
set in `.env`:

```
DATA_GOV_API_KEY=your_key
```

## Running
From the `api` directory:
`uvicorn main:app --reload`

## Endpoints
- Zone-Specific Data: Access data for a specific zone using its ID (defined in `zones.json`):
`GET /aqi/<zone_id>`

- Srinagar Special Endpoint:
`GET /aqi/srinagar`

- Generic Lookup:
`GET /aqi/zone/{zone_id}`

- List All Zones:
`GET /zones`

## How the AQI is Calculated

`[1]` The system fetches raw pollutant concentrations (PM2.5, PM10, NO2, SO2, CO, O3) in µg/m³ from the relevant provider.

`[2]` While most pollutants remain in µg/m³, Carbon Monoxide (CO) is divided by 1000 to convert it to mg/m³, as required by the Indian AQI standard.

`[3]` The standardized values are compared against the CPCB breakpoint tables loaded from aqi_breakpoints.json. Linear interpolation is used to calculate the sub-index for each pollutant.

`[4]` The overall AQI is determined by the highest (worst) sub-index among the available pollutants.

## Development
The project is designed to be data-driven. Adding a new town or district does not require changing Python code; you simply add a new entry to `zones.json`. Similarly, if government standards change, updating `aqi_breakpoints.json` will instantly update the calculation logic across the entire application.