# GEO Scorecard Generator

Flask web app for generating GEO scorecard and analysis PNGs from a target URL.

## Local Development

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start the app:

```bash
python3 -m flask --app app run --host 0.0.0.0 --port 5001
```

## Render Deployment

This project includes a `render.yaml` Blueprint for a Render Web Service.

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 180`
- No AI API key is required. Taiwan media search can optionally use `SERPAPI_KEY`.
