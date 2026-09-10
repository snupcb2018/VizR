from backend.pipeline.tools.qc.plugins import fastqc


class FakeRunner:
    results = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def map_unordered(self, _func, _args):
        yield from self.results

    def stop(self):
        pass


class FailingRunner(FakeRunner):
    def map_unordered(self, _func, _args):
        raise RuntimeError('worker pool unavailable')


def _result(name, successful, failed):
    total = successful + failed
    return {
        'sample_name': name,
        'success': failed == 0,
        'returncode': 0 if failed == 0 else 1,
        'stderr': 'validation failed' if failed else '',
        'file_results': [{} for _ in range(total)],
        'total_files': total,
        'successful_files': successful,
        'failed_files': failed,
        'displayable_files': successful,
        'validation_errors': ([{'report': name, 'errors': ['invalid report']}]
                              if failed else []),
    }


def _samples(count):
    return [
        {'sample_name': f'sample-{index}', 'files': {'SE': f'{index}.fastq'}}
        for index in range(count)
    ]


def test_partial_qc_continues_pipeline(monkeypatch):
    FakeRunner.results = [_result('good', 1, 0), _result('bad', 0, 1)]
    monkeypatch.setattr(fastqc, 'ProcessPoolRunner', FakeRunner)
    monkeypatch.setattr(fastqc.shared_state, 'get_worker_event', lambda _worker: None)

    result = fastqc.execute_fastqc_multi(_samples(2), {}, workbench_id=None)

    assert result['success'] is True
    assert result['result_status'] == 'partial'
    assert result['displayable_files'] == 1
    assert result['failed_files'] == 1


def test_qc_stops_when_no_report_is_displayable(monkeypatch):
    FakeRunner.results = [_result('bad-1', 0, 1), _result('bad-2', 0, 1)]
    monkeypatch.setattr(fastqc, 'ProcessPoolRunner', FakeRunner)
    monkeypatch.setattr(fastqc.shared_state, 'get_worker_event', lambda _worker: None)

    result = fastqc.execute_fastqc_multi(_samples(2), {}, workbench_id=None)

    assert result['success'] is False
    assert result['result_status'] == 'unavailable'
    assert result['displayable_files'] == 0
    assert result['failed_files'] == 2


def test_worker_pool_failure_marks_remaining_files_unavailable(monkeypatch):
    monkeypatch.setattr(fastqc, 'ProcessPoolRunner', FailingRunner)
    monkeypatch.setattr(fastqc.shared_state, 'get_worker_event', lambda _worker: None)

    result = fastqc.execute_fastqc_multi(_samples(2), {}, workbench_id=None)

    assert result['success'] is False
    assert result['result_status'] == 'unavailable'
    assert result['completed_files'] == 2
    assert result['failed_files'] == 2
    assert result['runner_error'] == 'worker pool unavailable'
