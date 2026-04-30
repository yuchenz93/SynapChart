# SynapChart

Visual pipeline builder for neuroscience data analysis.

Build EEG/LFP and spike train analysis pipelines by connecting blocks on a canvas — no coding required.

## Quickstart

```bash
pip install synapchart
synapchart
```

The browser opens automatically at `http://localhost:8000`.

## Development setup

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## Tech stack

- **Frontend:** React + React Flow
- **Backend:** FastAPI (Python 3.10+)
- **Data format:** NeuroData (numpy wrapper with metadata)
- **Visualization:** matplotlib (server-side PNG)

## License

MIT
