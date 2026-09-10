import json
from contextlib import contextmanager

from flask import Flask

import backend.blueprints.workbench_detail_qc as qc_blueprint


class FakeConnection:
    def __init__(self, row):
        self.row = row

    def execute(self, *_args, **_kwargs):
        return self

    def fetchone(self):
        return self.row


def _client(monkeypatch, row):
    app = Flask(__name__)
    app.secret_key = 'test'
    app.register_blueprint(qc_blueprint.workbench_detail_qc_bp)

    @contextmanager
    def fake_connection():
        yield FakeConnection(row)

    monkeypatch.setattr(qc_blueprint, 'get_db_connection', fake_connection)
    monkeypatch.setattr(qc_blueprint, 'check_workbench_access', lambda *_args: (True, 'owner'))
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 1
    return client


def test_failed_db_status_is_not_overridden_by_full_progress(monkeypatch):
    progress = {
        'completed_files': 2,
        'total_files': 2,
        'progress_percent': 100,
        'result_status': 'unavailable',
    }
    client = _client(monkeypatch, {
        'progress_detail': json.dumps(progress),
        'status': 'failed',
        'updated_at': '2026-01-01',
    })

    response = client.get('/api/workbenches/1/qc-progress')

    assert response.status_code == 200
    assert response.get_json()['status'] == 'failed'
    assert response.get_json()['result_status'] == 'unavailable'


def test_validated_partial_progress_uses_completing_until_worker_finishes(monkeypatch):
    progress = {
        'completed_files': 2,
        'total_files': 2,
        'successful_files': 1,
        'failed_files': 1,
        'displayable_files': 1,
        'progress_percent': 100,
        'result_status': 'partial',
    }
    client = _client(monkeypatch, {
        'progress_detail': json.dumps(progress),
        'status': 'running',
        'updated_at': '2026-01-01',
    })

    response = client.get('/api/workbenches/1/qc-progress')

    assert response.status_code == 200
    assert response.get_json()['status'] == 'completing'
    assert response.get_json()['result_status'] == 'partial'
