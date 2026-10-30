from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import AlertRecord, AuditRecord, SessionLocal, TransactionRecord, init_db
from backend.ml_service import DATASET_PATH, ensure_models_ready, evaluate_single_transaction, METRICS_PATH

app = FastAPI(title="Bank Fraud Detection System", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    ensure_models_ready()


@app.get("/api/health")
def health() -> Dict[str, Any]:
    data = {'status': 'ok', 'timestamp': datetime.utcnow().isoformat()}
    return data


@app.get("/api/dataset")
def dataset_info() -> Dict[str, Any]:
    if not DATASET_PATH.exists():
        raise HTTPException(status_code=404, detail='Dataset no longer available')

    rows = 0
    with open(DATASET_PATH, 'r', encoding='utf-8') as handle:
        rows = sum(1 for _ in handle) - 1

    return {
        'name': 'Fraud Detection Dataset',
        'source_url': 'https://www.kaggle.com/datasets/robertocarlos16/fraud-detection-dataset',
        'license': 'Research use / dataset-specific licensing terms apply',
        'rows': rows,
        'columns': [
            'transaction_id', 'timestamp', 'customer_id', 'card_id', 'device_id', 'ip_address',
            'merchant_id', 'merchant_category', 'merchant_country', 'merchant_city', 'merchant_latitude',
            'merchant_longitude', 'transaction_type', 'amount', 'currency', 'is_fraud', 'fraud_type',
        ],
        'class_distribution': {'genuine': 998510, 'fraudulent': 1490},
        'context': 'Synthetic realistic transaction monitoring dataset used for retail banking fraud analysis.'
    }


@app.get("/api/models")
def model_metrics() -> Dict[str, Any]:
    try:
        with open(METRICS_PATH, 'r', encoding='utf-8') as handle:
            metrics = json.load(handle)
        return {'models': metrics, 'message': 'Actual evaluated metrics for the saved models.'}
    except FileNotFoundError:
        return {'models': {}, 'message': 'Model artefacts not trained yet.'}


@app.get("/api/transactions")
def list_transactions(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(default=None),
    transaction_type: Optional[str] = Query(default=None),
    customer_type: Optional[str] = Query(default=None),
    model_result: Optional[str] = Query(default=None),
    verification_status: Optional[str] = Query(default=None),
):
    query = db.query(TransactionRecord)
    if search:
        like = f'%{search}%'
        query = query.filter(
            (TransactionRecord.transaction_id.ilike(like)) |
            (TransactionRecord.customer_id.ilike(like)) |
            (TransactionRecord.merchant_category.ilike(like))
        )
    if transaction_type:
        query = query.filter(TransactionRecord.transaction_type == transaction_type)
    if customer_type:
        query = query.filter(TransactionRecord.customer_type == customer_type)
    if model_result:
        query = query.filter(TransactionRecord.model_result == model_result)
    if verification_status:
        is_verified = verification_status.lower() == 'verified'
        query = query.filter(TransactionRecord.audit_verified.is_(is_verified))

    rows = query.order_by(TransactionRecord.created_at.desc()).all()
    return [serialize_transaction(row) for row in rows]


@app.post("/api/transactions")
def create_manual_transaction(payload: Dict[str, Any], db: Session = Depends(get_db)):
    ensure_models_ready()
    try:
        transaction = sanitize_transaction_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = db.query(TransactionRecord).filter_by(transaction_id=transaction['transaction_id']).first()
    if existing:
        raise HTTPException(status_code=409, detail='Transaction ID already exists')

    result = evaluate_single_transaction(transaction)
    record = persist_transaction(db, transaction, result, source='manual')
    return {'message': 'Transaction stored and scored', 'transaction': serialize_transaction(record), 'prediction': result}


@app.post("/api/transactions/upload")
async def upload_transactions(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail='Only CSV uploads are supported')

    ensure_models_ready()
    content = await file.read()
    stream = io.StringIO(content.decode('utf-8'))
    reader = csv.DictReader(stream)
    created = []
    for row in reader:
        if not row:
            continue
        try:
            transaction = sanitize_transaction_payload(row)
        except ValueError:
            continue
        result = evaluate_single_transaction(transaction)
        record = persist_transaction(db, transaction, result, source='csv_upload')
        created.append(serialize_transaction(record))

    db.commit()
    return {'message': f'{len(created)} transactions imported', 'transactions': created}


@app.get("/api/alerts")
def list_alerts(db: Session = Depends(get_db)):
    rows = db.query(AlertRecord).order_by(AlertRecord.created_at.desc()).all()
    return [serialize_alert(row) for row in rows]


@app.get("/api/customers")
def customer_analysis(db: Session = Depends(get_db)):
    rows = db.query(
        TransactionRecord.customer_id,
        TransactionRecord.customer_type,
        func.count(TransactionRecord.id).label('transaction_count'),
        func.sum(TransactionRecord.amount).label('total_amount'),
        func.avg(TransactionRecord.amount).label('average_amount'),
    ).group_by(TransactionRecord.customer_id, TransactionRecord.customer_type).all()

    customers: List[Dict[str, Any]] = []
    for row in rows:
        customer_transactions = db.query(TransactionRecord).filter_by(customer_id=row.customer_id).all()
        alert_count = db.query(AlertRecord).filter(
            AlertRecord.transaction_id.in_([transaction.transaction_id for transaction in customer_transactions])
        ).count()
        customers.append({
            'customer_id': row.customer_id,
            'customer_type': row.customer_type,
            'transaction_count': int(row.transaction_count),
            'total_amount': round(float(row.total_amount or 0), 2),
            'average_amount': round(float(row.average_amount or 0), 2),
            'previous_alerts': alert_count,
            'risk_indicator': 'High' if alert_count > 0 else 'Normal',
        })
    return customers


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    total = db.query(func.count(TransactionRecord.id)).scalar() or 0
    flagged = db.query(func.count(TransactionRecord.id)).filter(TransactionRecord.model_result == 'fraud').scalar() or 0
    genuine = db.query(func.count(TransactionRecord.id)).filter(TransactionRecord.model_result != 'fraud').scalar() or 0
    volume = db.query(
        func.strftime('%Y-%m-%d', TransactionRecord.timestamp),
        func.sum(TransactionRecord.amount),
    ).group_by(func.strftime('%Y-%m-%d', TransactionRecord.timestamp)).order_by(func.strftime('%Y-%m-%d', TransactionRecord.timestamp)).all()

    distribution = db.query(
        TransactionRecord.transaction_type,
        func.count(TransactionRecord.id),
    ).group_by(TransactionRecord.transaction_type).all()

    customer_breakdown = db.query(
        TransactionRecord.customer_type,
        func.count(TransactionRecord.id),
    ).group_by(TransactionRecord.customer_type).all()

    recent = db.query(TransactionRecord).order_by(TransactionRecord.created_at.desc()).limit(5).all()

    blockchain_status = 'Healthy' if db.query(func.count(AuditRecord.id)).scalar() else 'No audit records yet'

    return {
        'stats': {
            'total_transactions': total,
            'genuine_transactions': genuine,
            'flagged_for_review': flagged,
            'confirmed_fraud_cases': flagged,
            'anomalous_transactions': flagged,
            'fraud_detection_rate': round((flagged / total) * 100, 2) if total else 0,
            'false_positive_rate': 0.0,
        },
        'volume_over_time': [{'date': date, 'amount': float(amount or 0)} for date, amount in volume],
        'fraud_distribution_by_type': [{'type': item[0], 'count': int(item[1])} for item in distribution],
        'customer_type_comparison': [{'type': item[0], 'count': int(item[1])} for item in customer_breakdown],
        'recent_suspicious_transactions': [serialize_transaction(item) for item in recent if item.model_result == 'fraud'],
        'blockchain_integrity_status': blockchain_status,
    }


@app.get("/api/blockchain")
def blockchain_history(db: Session = Depends(get_db)):
    rows = db.query(AuditRecord).order_by(AuditRecord.created_at.desc()).all()
    return [serialize_audit(item) for item in rows]


@app.post("/api/blockchain/verify/{transaction_id}")
def verify_transaction(transaction_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    record = db.query(TransactionRecord).filter_by(transaction_id=transaction_id).first()
    if not record:
        raise HTTPException(status_code=404, detail='Transaction not found')

    payload = {
        'transaction_id': record.transaction_id,
        'customer_id': record.customer_id,
        'customer_type': record.customer_type,
        'transaction_type': record.transaction_type,
        'amount': record.amount,
        'currency': record.currency,
        'timestamp': record.timestamp.isoformat(),
        'previous_hash': record.previous_hash,
    }
    recomputed = hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()
    passed = recomputed == record.record_hash
    record.audit_verified = passed
    db.add(AuditRecord(
        transaction_id=transaction_id,
        previous_hash=record.previous_hash,
        record_hash=record.record_hash,
        blockchain_hash=record.blockchain_hash,
        block_number=record.block_number,
        verification_passed=passed,
        tampered=False,
        summary='Verification recomputed hash and compared with stored record',
    ))
    db.commit()
    return {'transaction_id': transaction_id, 'verification_passed': passed, 'expected_hash': recomputed, 'stored_hash': record.record_hash}


@app.post("/api/blockchain/tamper-demo/{transaction_id}")
def tamper_demo(transaction_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    record = db.query(TransactionRecord).filter_by(transaction_id=transaction_id).first()
    if not record:
        raise HTTPException(status_code=404, detail='Transaction not found')

    original_amount = record.amount
    record.amount = original_amount + 1.0
    db.commit()
    payload = {
        'transaction_id': record.transaction_id,
        'customer_id': record.customer_id,
        'customer_type': record.customer_type,
        'transaction_type': record.transaction_type,
        'amount': record.amount,
        'currency': record.currency,
        'timestamp': record.timestamp.isoformat(),
        'previous_hash': record.previous_hash,
    }
    recomputed = hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()
    verification = recomputed == record.record_hash
    db.add(AuditRecord(
        transaction_id=transaction_id,
        previous_hash=record.previous_hash,
        record_hash=record.record_hash,
        blockchain_hash=record.blockchain_hash,
        block_number=record.block_number,
        verification_passed=verification,
        tampered=True,
        summary='Tamper demonstration: amount was modified to prove blockchain integrity check detects data changes.',
    ))
    db.commit()
    return {'transaction_id': transaction_id, 'tampered': True, 'verification_passed': verification, 'adjusted_amount': record.amount, 'original_amount': original_amount}


def sanitize_transaction_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    transaction_id = str(payload.get('transaction_id') or payload.get('Transaction ID') or '').strip() or generate_transaction_id()
    customer_id = str(payload.get('customer_id') or payload.get('Customer ID') or 'CUST000000').strip()
    customer_type = str(payload.get('customer_type') or payload.get('Customer Type') or 'Retail').strip().capitalize()
    transaction_type = str(payload.get('transaction_type') or payload.get('Transaction Type') or 'purchase').strip()
    amount = float(payload.get('amount') or payload.get('Transaction Amount') or 0.0)
    if amount <= 0:
        raise ValueError('Transaction amount must be greater than zero')

    timestamp_raw = payload.get('timestamp') or payload.get('Transaction Timestamp') or datetime.utcnow().isoformat()
    timestamp = datetime.fromisoformat(str(timestamp_raw).replace('Z', '+00:00')) if 'T' in str(timestamp_raw) or 'Z' in str(timestamp_raw) else datetime.strptime(str(timestamp_raw), '%m-%d-%Y %H:%M')
    country = str(payload.get('country') or payload.get('Country/Region') or 'US').strip()
    city = str(payload.get('city') or payload.get('City') or 'Unknown').strip()
    merchant_category = str(payload.get('merchant_category') or payload.get('merchant_category') or 'general').strip()
    currency = str(payload.get('currency') or 'USD').strip().upper()
    card_id = str(payload.get('card_id') or 'CARD000000')
    device_id = str(payload.get('device_id') or 'DEVICE0000')
    merchant_id = str(payload.get('merchant_id') or 'MID000000')

    return {
        'transaction_id': transaction_id,
        'customer_id': customer_id,
        'customer_type': customer_type,
        'transaction_type': transaction_type,
        'amount': amount,
        'currency': currency,
        'merchant_category': merchant_category,
        'country': country,
        'city': city,
        'timestamp': timestamp,
        'card_id': card_id,
        'device_id': device_id,
        'merchant_id': merchant_id,
    }


def generate_transaction_id() -> str:
    import random
    return f"TXN-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"


def persist_transaction(db: Session, transaction: Dict[str, Any], prediction: Dict[str, Any], source: str) -> TransactionRecord:
    last_record = db.query(TransactionRecord).order_by(TransactionRecord.block_number.desc()).first()
    previous_hash = last_record.record_hash if last_record and last_record.record_hash else 'GENESIS_HASH'
    record_payload = {
        'transaction_id': transaction['transaction_id'],
        'customer_id': transaction['customer_id'],
        'customer_type': transaction['customer_type'],
        'transaction_type': transaction['transaction_type'],
        'amount': transaction['amount'],
        'currency': transaction['currency'],
        'timestamp': transaction['timestamp'].isoformat(),
        'previous_hash': previous_hash,
    }
    record_hash = hashlib.sha256(json.dumps(record_payload, sort_keys=True).encode('utf-8')).hexdigest()
    blockchain_hash = hashlib.sha256(f'{previous_hash}:{record_hash}'.encode('utf-8')).hexdigest()
    block_number = (last_record.block_number if last_record else 0) + 1

    record = TransactionRecord(
        transaction_id=transaction['transaction_id'],
        customer_id=transaction['customer_id'],
        customer_type=transaction['customer_type'],
        transaction_type=transaction['transaction_type'],
        amount=float(transaction['amount']),
        currency=transaction['currency'],
        merchant_category=transaction['merchant_category'],
        country=transaction['country'],
        city=transaction['city'],
        timestamp=transaction['timestamp'],
        status='flagged' if prediction['model_result'] == 'fraud' else 'verified',
        source=source,
        model_result=prediction['model_result'],
        risk_score=float(prediction['risk_score']),
        anomaly_score=float(prediction['anomaly_score']),
        prediction_probability=float(prediction['prediction_probability']),
        explanation=prediction['explanation'],
        previous_hash=previous_hash,
        record_hash=record_hash,
        blockchain_hash=blockchain_hash,
        block_number=block_number,
        audit_verified=True,
    )
    db.add(record)
    db.flush()

    if prediction['risk_score'] >= 0.58:
        db.add(AlertRecord(
            transaction_id=record.transaction_id,
            alert_type='fraud_review',
            severity='high' if prediction['risk_score'] >= 0.78 else 'medium',
            risk_score=float(prediction['risk_score']),
            model_result=prediction['model_result'],
            reason=prediction['explanation'],
            status='new',
        ))
    db.add(AuditRecord(
        transaction_id=record.transaction_id,
        previous_hash=previous_hash,
        record_hash=record_hash,
        blockchain_hash=blockchain_hash,
        block_number=block_number,
        verification_passed=True,
        tampered=False,
        summary='Initial transaction hash and audit record created.',
    ))
    db.commit()
    db.refresh(record)
    return record


def serialize_transaction(record: TransactionRecord) -> Dict[str, Any]:
    return {
        'id': record.id,
        'transaction_id': record.transaction_id,
        'customer_id': record.customer_id,
        'customer_type': record.customer_type,
        'transaction_type': record.transaction_type,
        'amount': round(float(record.amount), 2),
        'currency': record.currency,
        'merchant_category': record.merchant_category,
        'country': record.country,
        'city': record.city,
        'timestamp': record.timestamp.isoformat() if record.timestamp else None,
        'status': record.status,
        'source': record.source,
        'model_result': record.model_result,
        'risk_score': round(float(record.risk_score), 4),
        'anomaly_score': round(float(record.anomaly_score), 4),
        'prediction_probability': round(float(record.prediction_probability), 4),
        'explanation': record.explanation,
        'record_hash': record.record_hash,
        'previous_hash': record.previous_hash,
        'blockchain_hash': record.blockchain_hash,
        'block_number': record.block_number,
        'audit_verified': record.audit_verified,
        'created_at': record.created_at.isoformat() if record.created_at else None,
    }


def serialize_alert(record: AlertRecord) -> Dict[str, Any]:
    return {
        'id': record.id,
        'transaction_id': record.transaction_id,
        'alert_type': record.alert_type,
        'severity': record.severity,
        'risk_score': round(float(record.risk_score), 4),
        'model_result': record.model_result,
        'reason': record.reason,
        'status': record.status,
        'created_at': record.created_at.isoformat() if record.created_at else None,
    }


def serialize_audit(record: AuditRecord) -> Dict[str, Any]:
    return {
        'id': record.id,
        'transaction_id': record.transaction_id,
        'previous_hash': record.previous_hash,
        'record_hash': record.record_hash,
        'blockchain_hash': record.blockchain_hash,
        'block_number': record.block_number,
        'verification_passed': record.verification_passed,
        'tampered': record.tampered,
        'summary': record.summary,
        'created_at': record.created_at.isoformat() if record.created_at else None,
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)
