# Bank Fraud Detection System

A full-stack financial fraud detection prototype combining a FastAPI backend, SQLAlchemy SQLite persistence, real transaction scoring with machine learning, and a React dashboard.

## Features

- React + Vite dashboard with pages for overview, transactions, alerts, customer analysis, ML comparison, blockchain audit, and dataset research.
- FastAPI backend with SQLite database and hashed audit trail.
- Real model training using a bank fraud dataset stored in `Dataset/Fraud Detection Dataset.csv`.
- Logistic Regression, Random Forest, XGBoost, and Isolation Forest evaluation.
- Manual transaction entry and CSV import.
- Blockchain-style integrity verification and tamper demonstration.

## Folder structure

- `backend/` – FastAPI app, database models, and ML pipeline.
- `frontend/` – Vite React application.
- `Dataset/` – Input dataset used for training and scoring.

## Setup

### 1) Backend

From the project root:

```bash
cd bank-fraud-detection-system
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 2) Frontend

```bash
cd frontend
npm install
```

### 3) Run the application

Terminal 1:

```bash
cd bank-fraud-detection-system
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal 2:

```bash
cd bank-fraud-detection-system\frontend
npm run dev
```

Then open the local Vite URL shown in the terminal, usually `http://localhost:5173`.

## Notes

- The backend initializes SQLite automatically on start.
- If model artifacts do not exist yet, the app trains the prediction models on the dataset and saves metrics to `backend/artifacts/`.
- The blockchain layer is a local hash-linked audit chain designed for demonstration and integrity verification, not a public Ethereum network.
