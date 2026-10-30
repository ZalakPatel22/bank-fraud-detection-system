from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from joblib import dump, load
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, average_precision_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DATASET_PATH = next(
    (
        candidate
        for candidate in [
            PROJECT_ROOT / "Dataset" / "Fraud Detection Dataset.csv",
            WORKSPACE_ROOT / "Dataset" / "Fraud Detection Dataset.csv",
        ]
        if candidate.exists()
    ),
    PROJECT_ROOT / "Dataset" / "Fraud Detection Dataset.csv",
)
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True, parents=True)
MODEL_BUNDLE_PATH = ARTIFACT_DIR / "fraud_model_bundle.joblib"
METRICS_PATH = ARTIFACT_DIR / "model_metrics.json"

FEATURE_COLUMNS = [
    "transaction_type",
    "merchant_category",
    "currency",
    "amount",
    "merchant_country",
    "merchant_city",
    "customer_id",
    "card_id",
    "device_id",
    "merchant_id",
    "hour",
    "day_of_week",
    "amount_log",
]

LOW_CARDINALITY_CATEGORICAL = [
    'transaction_type',
    'merchant_category',
    'currency',
    'merchant_country',
]
HIGH_CARDINALITY_FEATURES = [
    'merchant_city',
    'customer_id',
    'card_id',
    'device_id',
    'merchant_id',
]
NUMERIC_FEATURES = ['amount', 'hour', 'day_of_week', 'amount_log'] + HIGH_CARDINALITY_FEATURES


def _hash_string(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_dataset(df: pd.DataFrame) -> pd.DataFrame:
    local = df.copy()
    local["timestamp"] = pd.to_datetime(local.get("timestamp", pd.NaT), errors="coerce")
    local["hour"] = local["timestamp"].dt.hour.fillna(0)
    local["day_of_week"] = local["timestamp"].dt.dayofweek.fillna(0)
    local["amount_log"] = np.log1p(local["amount"].fillna(0))
    local["merchant_category"] = local["merchant_category"].fillna("other")
    local["merchant_country"] = local["merchant_country"].fillna("US")
    local["currency"] = local["currency"].fillna("USD")
    local["transaction_type"] = local["transaction_type"].fillna("purchase")
    local["customer_id"] = local["customer_id"].astype(str)
    local["card_id"] = local["card_id"].astype(str)
    local["device_id"] = local["device_id"].astype(str)
    local["merchant_id"] = local["merchant_id"].astype(str)
    local["merchant_city"] = local["merchant_city"].fillna("unknown")
    return local


def _bucketize_high_cardinality(frame: pd.DataFrame) -> pd.DataFrame:
    transformed = frame.copy()
    for column in HIGH_CARDINALITY_FEATURES:
        transformed[column] = transformed[column].fillna('unknown').astype(str)
        transformed[column] = transformed[column].map(
            lambda value: int(int(_hash_string(str(value)), 16) % 128)
        )
    return transformed


def train_and_save_models() -> Dict[str, Any]:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found at {DATASET_PATH}")

    df = pd.read_csv(DATASET_PATH)
    sample_size = min(len(df), 150000)
    sampled = df.sample(n=sample_size, random_state=42, replace=False)
    local = _normalize_dataset(sampled)
    local = local[FEATURE_COLUMNS + ["is_fraud"]].dropna(subset=["amount"]).copy()

    X = _bucketize_high_cardinality(local[FEATURE_COLUMNS])
    y = local["is_fraud"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', Pipeline([('imputer', SimpleImputer(strategy='median')), ('scaler', StandardScaler())]), NUMERIC_FEATURES),
            ('low_cat', OneHotEncoder(handle_unknown='ignore', sparse_output=True), LOW_CARDINALITY_CATEGORICAL),
        ],
        remainder='drop',
        sparse_threshold=0.2,
    )

    models = {
        'logistic_regression': LogisticRegression(max_iter=1500, class_weight='balanced', random_state=42),
        'random_forest': RandomForestClassifier(n_estimators=200, max_depth=12, min_samples_leaf=3, random_state=42, class_weight='balanced', n_jobs=-1),
        'xgboost': XGBClassifier(
            n_estimators=150,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            objective='binary:logistic',
            random_state=42,
            eval_metric='logloss',
            n_jobs=-1,
        ),
    }

    metrics: Dict[str, Dict[str, Any]] = {}
    for name, model in models.items():
        pipeline = Pipeline([
            ('preprocessor', preprocessor),
            ('model', model),
        ])
        pipeline.fit(X_train, y_train)
        probs = pipeline.predict_proba(X_test)[:, 1]
        preds = (probs >= 0.5).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_test, preds, labels=[0, 1]).ravel()
        metrics[name] = {
            'accuracy': round(float(accuracy_score(y_test, preds)), 4),
            'precision': round(float(precision_score(y_test, preds, zero_division=0)), 4),
            'recall': round(float(recall_score(y_test, preds, zero_division=0)), 4),
            'f1_score': round(float(f1_score(y_test, preds, zero_division=0)), 4),
            'pr_auc': round(float(average_precision_score(y_test, probs)), 4),
            'roc_auc': round(float(roc_auc_score(y_test, probs)), 4),
            'false_positive_rate': round(float(fp / (fp + tn)) if (fp + tn) else 0.0, 4),
            'confusion_matrix': [int(tn), int(fp), int(fn), int(tp)],
            'trainable': True,
        }

    iso_model = IsolationForest(
        n_estimators=120,
        contamination=0.01,
        random_state=42,
    )
    iso_features = preprocessor.fit_transform(X_train)
    iso_model.fit(iso_features)

    bundle = {
        'preprocessor': preprocessor,
        'models': models,
        'isolation_forest': iso_model,
        'feature_columns': FEATURE_COLUMNS,
    }
    dump(bundle, MODEL_BUNDLE_PATH)
    with open(METRICS_PATH, 'w', encoding='utf-8') as handle:
        json.dump(metrics, handle, indent=2)

    return {'metrics': metrics, 'bundle_path': str(MODEL_BUNDLE_PATH), 'dataset_rows': int(len(local))}


def ensure_models_ready() -> Dict[str, Any]:
    if not MODEL_BUNDLE_PATH.exists() or not METRICS_PATH.exists():
        return train_and_save_models()
    return {'metrics': json.loads(METRICS_PATH.read_text(encoding='utf-8')), 'bundle_path': str(MODEL_BUNDLE_PATH), 'dataset_rows': 0}


def _feature_row_from_transaction(transaction: Dict[str, Any]) -> pd.DataFrame:
    timestamp = pd.to_datetime(transaction.get('timestamp') or '2025-01-01T00:00:00Z', errors='coerce')
    row = {
        'transaction_type': str(transaction.get('transaction_type') or 'purchase'),
        'merchant_category': str(transaction.get('merchant_category') or 'general'),
        'currency': str(transaction.get('currency') or 'USD'),
        'amount': float(transaction.get('amount') or 0.0),
        'merchant_country': str(transaction.get('merchant_country') or 'US'),
        'merchant_city': str(transaction.get('merchant_city') or 'unknown'),
        'customer_id': str(transaction.get('customer_id') or 'CUST000000'),
        'card_id': str(transaction.get('card_id') or 'CARD000000'),
        'device_id': str(transaction.get('device_id') or 'DEVICE0000'),
        'merchant_id': str(transaction.get('merchant_id') or 'MID000000'),
        'hour': timestamp.hour if pd.notna(timestamp) else 0,
        'day_of_week': timestamp.dayofweek if pd.notna(timestamp) else 0,
        'amount_log': np.log1p(float(transaction.get('amount') or 0.0)),
    }
    frame = pd.DataFrame([row], columns=FEATURE_COLUMNS)
    return _bucketize_high_cardinality(frame)


def evaluate_single_transaction(transaction: Dict[str, Any]) -> Dict[str, Any]:
    bundle = load(MODEL_BUNDLE_PATH)
    feature_frame = _feature_row_from_transaction(transaction)
    transformed = bundle['preprocessor'].transform(feature_frame)

    probabilities = {}
    for name, model in bundle['models'].items():
        probs = model.predict_proba(transformed)[:, 1]
        probabilities[name] = float(probs[0])

    iso_score = -float(bundle['isolation_forest'].score_samples(transformed)[0])
    anomaly_score = float(np.clip((iso_score + 2) / 6, 0, 1))
    risk_score = max(probabilities.values()) * 0.85 + anomaly_score * 0.15
    decision = 'fraud' if risk_score >= 0.58 else 'legitimate'

    top_importance = []
    rf_model = bundle['models']['random_forest']
    for feature_name, importance in sorted(
        zip(feature_frame.columns, rf_model.feature_importances_),
        key=lambda item: item[1],
        reverse=True,
    )[:4]:
        top_importance.append({'feature': feature_name, 'importance': round(float(importance), 4)})

    explanation = ' '.join(
        [f"{item['feature']}={feature_frame.iloc[0][item['feature']]}" for item in top_importance]
    )

    return {
        'model_result': decision,
        'risk_score': round(float(risk_score), 4),
        'anomaly_score': round(float(anomaly_score), 4),
        'prediction_probability': round(float(max(probabilities.values())), 4),
        'model_probabilities': {name: round(float(value), 4) for name, value in probabilities.items()},
        'explanation': explanation,
        'isolation_score': round(float(iso_score), 4),
    }
