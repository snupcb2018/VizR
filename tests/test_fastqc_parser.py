import zipfile

from backend.utils.fastqc_parser import validate_fastqc_report


FASTQC_TEXT = """##FastQC\t0.12.1
>>Basic Statistics\tpass
#Measure\tValue
Filename\tsample.fastq.gz
Total Sequences\t10
Sequence length\t4
%GC\t50
>>END_MODULE
>>Per base sequence quality\tfail
#Base\tMean\tMedian\tLower Quartile\tUpper Quartile\t10th Percentile\t90th Percentile
1\t30\t31\t29\t32\t28\t33
>>END_MODULE
"""


def _write_html(path):
    path.write_text('<html>FastQC</html>', encoding='utf-8')


def test_valid_extracted_report_accepts_biological_module_failure(tmp_path):
    report_dir = tmp_path / 'sample_fastqc'
    report_dir.mkdir()
    data_path = report_dir / 'fastqc_data.txt'
    html_path = tmp_path / 'sample_fastqc.html'
    data_path.write_text(FASTQC_TEXT, encoding='utf-8')
    _write_html(html_path)

    result = validate_fastqc_report(str(data_path), None, str(html_path))

    assert result['valid'] is True
    assert result['source'] == 'extracted'
    assert result['modules']['Per base sequence quality']['status'] == 'fail'


def test_zip_only_report_is_recovered_for_ui(tmp_path):
    report_dir = tmp_path / 'sample_fastqc'
    data_path = report_dir / 'fastqc_data.txt'
    zip_path = tmp_path / 'sample_fastqc.zip'
    html_path = tmp_path / 'sample_fastqc.html'
    _write_html(html_path)
    with zipfile.ZipFile(zip_path, 'w') as archive:
        archive.writestr('sample_fastqc/fastqc_data.txt', FASTQC_TEXT)

    result = validate_fastqc_report(
        str(data_path), str(zip_path), str(html_path), recover=True
    )

    assert result['valid'] is True
    assert result['source'] == 'recovered'
    assert result['recovered'] is True
    assert data_path.read_text(encoding='utf-8') == FASTQC_TEXT


def test_valid_zip_replaces_malformed_extracted_data(tmp_path):
    report_dir = tmp_path / 'sample_fastqc'
    report_dir.mkdir()
    data_path = report_dir / 'fastqc_data.txt'
    zip_path = tmp_path / 'sample_fastqc.zip'
    html_path = tmp_path / 'sample_fastqc.html'
    data_path.write_text('damaged extracted output', encoding='ascii')
    _write_html(html_path)
    with zipfile.ZipFile(zip_path, 'w') as archive:
        archive.writestr('sample_fastqc/fastqc_data.txt', FASTQC_TEXT)

    result = validate_fastqc_report(
        str(data_path), str(zip_path), str(html_path), recover=True
    )

    assert result['valid'] is True
    assert result['source'] == 'recovered'
    assert result['warnings']
    assert data_path.read_text(encoding='utf-8') == FASTQC_TEXT


def test_missing_or_empty_artifacts_are_rejected(tmp_path):
    data_path = tmp_path / 'sample_fastqc' / 'fastqc_data.txt'
    html_path = tmp_path / 'sample_fastqc.html'
    html_path.touch()

    result = validate_fastqc_report(str(data_path), None, str(html_path))

    assert result['valid'] is False
    assert 'FastQC HTML report is missing or empty' in result['errors']
    assert 'FastQC ZIP is missing or empty' in result['errors']


def test_corrupt_zip_is_rejected(tmp_path):
    zip_path = tmp_path / 'sample_fastqc.zip'
    html_path = tmp_path / 'sample_fastqc.html'
    zip_path.write_text('not a zip', encoding='ascii')
    _write_html(html_path)

    result = validate_fastqc_report(
        str(tmp_path / 'sample_fastqc' / 'fastqc_data.txt'),
        str(zip_path),
        str(html_path),
    )

    assert result['valid'] is False
    assert any('Unable to read FastQC ZIP' in error for error in result['errors'])


def test_malformed_fastqc_data_is_rejected(tmp_path):
    report_dir = tmp_path / 'sample_fastqc'
    report_dir.mkdir()
    data_path = report_dir / 'fastqc_data.txt'
    html_path = tmp_path / 'sample_fastqc.html'
    data_path.write_text('not FastQC output', encoding='ascii')
    _write_html(html_path)

    result = validate_fastqc_report(str(data_path), None, str(html_path))

    assert result['valid'] is False
    assert 'FastQC header is missing' in result['errors']
    assert 'Basic Statistics module is missing' in result['errors']
