# Remediscent

AI-powered smart medicine management, safety and reorder prediction system.

## Features (MVP)
- User auth + family members
- Medicine inventory with expiry tracking
- Consumption tracking
- ML-based reorder prediction (Random Forest vs moving average baseline)
- Alerts + notifications
- Dashboard

## Local Run

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # edit SECRET_KEY
flask --app app seed-demo      # optional demo data
python app.py
```

Open http://localhost:5000
Demo login (after seeding): **demo@remediscent.app / demo1234**

## Deploy on Render (free tier friendly)

1. Push repo to GitHub.
2. On [Render](https://render.com): **New → Web Service** → connect repo.
3. Settings:
   - **Environment:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`
4. Add environment variables:
   - `SECRET_KEY` = long random string
   - `DATABASE_URL` = your Postgres URL (Render → New → PostgreSQL → copy *Internal Database URL*)
   - `FLASK_DEBUG` = `0`
5. Deploy. First boot creates tables automatically.

## Deploy on Railway
1. Push repo to GitHub.
2. New Project → Deploy from GitHub.
3. Add **PostgreSQL** plugin → Railway sets `DATABASE_URL` automatically.
4. Add `SECRET_KEY` variable.
5. Railway auto-detects the `Procfile`.

## Deploy with Docker (anywhere)

```bash
docker build -t remediscent .
docker run -p 8000:8000 -e SECRET_KEY=change-me -e DATABASE_URL=sqlite:///data.db remediscent
```

## API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/predict/<medicine_id>` | Returns run-out + reorder prediction (JSON) |
| GET | `/health` | Health check |

## Honest Limitations
- Pill identification and OCR are **not** included in this deployment (documented as future work — they require heavy models and are treated separately in the project report).
- Prediction quality depends on consumption history; with <5 records, a rule-based fallback is used.
- Prototype for household use only. Not a medical device.