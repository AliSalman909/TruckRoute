# SafeHaul: weather-aware truck routing

React + Django app that compares three routes, samples the forecast at the truck's ETA every 10/25/50 miles, scores risk with load-aware rules, and recommends the safest route. Includes a 0–48 h corridor weather heatmap.

## Services used
| Service | Used for | Key |
|---|---|---|
| [FreeRoute](https://freeroute.org) | Routing (directions) and geocoding | **Yes**: `FREEROUTE_API_KEY` in `backend/.env` (free tier: 5,000 req/day, 60/min) |
| [Open-Meteo](https://open-meteo.com) | Hourly forecasts | No |
| [Photon](https://photon.komoot.io) | Type-ahead place suggestions (top-up; FreeRoute matches whole words only) | No. Disable with `AUTOCOMPLETE_FALLBACK_URL=` |
| [OpenFreeMap](https://openfreemap.org) | Map tiles (MapLibre GL) | No |

The frontend needs no keys; all FreeRoute calls go through Django.

## Prerequisites
Python 3.11+ (tested on 3.13), Node 20+ (tested on 24).

## Run

**Backend** (port 8000)
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set FREEROUTE_API_KEY
python manage.py runserver 8000
```
No migrations needed (the API has no database). Check it with `curl http://localhost:8000/api/v1/health/`.

**Frontend** (port 5173)
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. Vite proxies `/api` to the Django server.

## Test
```bash
cd backend && python -m pytest        # 99 tests
cd frontend && npm run build          # type-check + production build
```

## Quick API check
```bash
curl -X POST http://localhost:8000/api/v1/analyze-routes/ \
  -H "Content-Type: application/json" \
  -d '{"origin":"Chicago, IL","destination":"Denver, CO","departure_time":"2026-11-10T08:00:00Z","load_weight":45000,"interval_miles":25}'
```
