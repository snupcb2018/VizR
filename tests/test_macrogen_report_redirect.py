import io
import zipfile
from unittest.mock import Mock, patch

from flask import Flask

from backend.blueprints.macrogen import macrogen_bp


REPORT_URL = 'https://datadownload.macrogen.com/download?file=UmVwb3J0LnppcA=='
STORAGE_URL = (
    'https://stratus-gds-apn2.s3.ap-northeast-2.amazonaws.com/reports/Report.zip'
    '?X-Amz-Signature=example'
)


def _client():
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.register_blueprint(macrogen_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 1
    return client


def _report_zip():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as report:
        report.writestr(
            'report/samples_md5sum_downloadlink.txt',
            'sample_1.fastq.gz\t100\tchecksum\thttps://example.com/sample_1.fastq.gz\n',
        )
    return output.getvalue()


def _response(status, *, location=None, content=b''):
    response = Mock(status_code=status, headers={}, content=content)
    if location:
        response.headers['Location'] = location
    if status >= 400:
        response.raise_for_status.side_effect = RuntimeError('HTTP error')
    return response


def test_macrogen_s3_report_redirect_is_parsed():
    redirect = _response(303, location=STORAGE_URL)
    report = _response(200, content=_report_zip())
    with patch('requests.get', side_effect=[redirect, report]) as get:
        response = _client().post('/api/macrogen/fetch-file-list', json={'report_url': REPORT_URL})

    assert response.status_code == 200
    assert response.json['total_files'] == 1
    assert response.json['files'][0]['name'] == 'sample_1.fastq.gz'
    assert [call.args[0] for call in get.call_args_list] == [REPORT_URL, STORAGE_URL]
    assert all(call.kwargs['allow_redirects'] is False for call in get.call_args_list)
    assert redirect.close.called and report.close.called


def test_jumpto_link_can_redirect_through_macrogen_to_storage():
    short_url = 'https://l.jumpto.es/l/report'
    redirects = [_response(302, location=REPORT_URL), _response(303, location=STORAGE_URL)]
    with patch('requests.get', side_effect=[*redirects, _response(200, content=_report_zip())]) as get:
        response = _client().post('/api/macrogen/fetch-file-list', json={'report_url': short_url})

    assert response.status_code == 200
    assert [call.args[0] for call in get.call_args_list] == [short_url, REPORT_URL, STORAGE_URL]


def test_untrusted_redirect_is_rejected_before_request():
    redirect = _response(302, location='http://127.0.0.1/private.zip')
    with patch('requests.get', return_value=redirect) as get:
        response = _client().post('/api/macrogen/fetch-file-list', json={'report_url': REPORT_URL})

    assert response.status_code == 400
    assert get.call_count == 1
    assert redirect.close.called


def test_unsigned_storage_redirect_is_rejected():
    redirect = _response(303, location=STORAGE_URL.split('?')[0])
    with patch('requests.get', return_value=redirect) as get:
        response = _client().post('/api/macrogen/fetch-file-list', json={'report_url': REPORT_URL})

    assert response.status_code == 400
    assert get.call_count == 1


def test_storage_url_cannot_be_submitted_directly():
    with patch('requests.get') as get:
        response = _client().post('/api/macrogen/fetch-file-list', json={'report_url': STORAGE_URL})

    assert response.status_code == 400
    get.assert_not_called()


def test_lookalike_macrogen_domain_is_rejected():
    with patch('requests.get') as get:
        response = _client().post(
            '/api/macrogen/fetch-file-list',
            json={'report_url': 'https://fake-macrogen.com/Report.zip'},
        )

    assert response.status_code == 400
    get.assert_not_called()
