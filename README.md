# GEO Scorecard Generator

Flask web app for generating GEO scorecard and analysis PNGs from a target URL.

## Local Development

1. Create an `.env` file from `.env.example`
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Export environment variables and start the app:

```bash
set -a
source .env
set +a
python3 -m flask --app app run --host 0.0.0.0 --port 5001
```

## Render Deployment

This project includes a `render.yaml` Blueprint for a Render Web Service.

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
- Required environment variable: `ANTHROPIC_API_KEY`

After creating the service on Render, add `ANTHROPIC_API_KEY` in the Render dashboard before the first deploy.
