# Local Scale

Local-first scale app for OKOK-compatible Bluetooth body scales. The codebase is split into a Python backend and a React frontend so development can happen on one machine while Bluetooth capture happens on a separate MiniPC target.

## Layout

- `backend/`: FastAPI app, SQLite storage, replay/live scale adapters, tests
- `frontend/`: React + Vite UI with remembered profile selection and charts
- `fixtures/`: replay measurements and sample imports for local development
- `deploy/`: systemd service and environment templates for the MiniPC
- `docs/`: deployment and protocol notes

## Development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:create_app --factory --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The backend defaults to `replay` adapter mode in `dev`, so you can exercise the full weigh-in flow without live Bluetooth hardware.

## Target Deployment

Build the frontend, then run the backend as a single service on the MiniPC guest:

```bash
cd frontend
npm install
npm run build

cd ../backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8040
```

For a Proxmox guest setup, see [docs/minipc-deploy.md](/Users/tansukahyaoglu/Development/local-scale/docs/minipc-deploy.md).
