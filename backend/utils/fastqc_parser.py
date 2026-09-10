#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastQC Data Parser Module
Parse FastQC result files and transform to chart-ready format
"""

import os
import glob
import logging
import re
import json
import zipfile
from typing import List, Dict, Optional, Any
from pathlib import Path

# Configure logging
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

FASTQC_DATA_NAME = 'fastqc_data.txt'
FASTQC_REQUIRED_STATISTICS = {'Total Sequences', 'Sequence length'}
FASTQC_REQUIRED_MODULE = 'Per base sequence quality'


def _parse_fastqc_text(text: str) -> Dict[str, Any]:
    """Parse FastQC text content into modules."""
    modules = {}
    current_module = None

    for line in text.splitlines():
        if line.startswith('>>'):
            if line.startswith('>>END_MODULE'):
                current_module = None
            else:
                parts = line[2:].split('\t')
                current_module = parts[0]
                modules[current_module] = {
                    'status': parts[1] if len(parts) > 1 else 'unknown',
                    'data': [],
                    'headers': []
                }
        elif current_module and line.startswith('#'):
            if line != '#' and '\t' in line:
                modules[current_module]['headers'] = line[1:].split('\t')
        elif current_module and line and not line.startswith('#'):
            modules[current_module]['data'].append(line.split('\t'))

    return modules


def _read_fastqc_zip(zip_path: str) -> tuple[Optional[str], Optional[str]]:
    """Read the single FastQC data member without extracting the archive."""
    try:
        if not zip_path or not os.path.isfile(zip_path) or os.path.getsize(zip_path) == 0:
            return None, 'FastQC ZIP is missing or empty'
        with zipfile.ZipFile(zip_path) as archive:
            members = [
                name for name in archive.namelist()
                if not name.endswith('/') and Path(name).name == FASTQC_DATA_NAME
            ]
            if len(members) != 1:
                return None, f'FastQC ZIP must contain exactly one {FASTQC_DATA_NAME}'
            return archive.read(members[0]).decode('utf-8'), None
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        return None, f'Unable to read FastQC ZIP: {exc}'


def _validate_fastqc_text(text: str) -> tuple[Dict[str, Any], List[str]]:
    """Validate the FastQC content needed by the VizR parser and charts."""
    errors = []
    if not text.startswith('##FastQC'):
        errors.append('FastQC header is missing')

    modules = _parse_fastqc_text(text)
    basic = modules.get('Basic Statistics')
    if not basic:
        errors.append('Basic Statistics module is missing')
    else:
        statistics = {row[0]: row[1] for row in basic.get('data', []) if len(row) >= 2}
        missing_statistics = sorted(FASTQC_REQUIRED_STATISTICS - statistics.keys())
        if missing_statistics:
            errors.append(f"Required statistics missing: {', '.join(missing_statistics)}")
        else:
            try:
                int(str(statistics['Total Sequences']).replace(',', ''))
                [int(part) for part in str(statistics['Sequence length']).split('-')]
            except (TypeError, ValueError):
                errors.append('Required FastQC statistics are not numeric')

    quality_module = modules.get(FASTQC_REQUIRED_MODULE)
    if not quality_module or not quality_module.get('data'):
        errors.append(f'{FASTQC_REQUIRED_MODULE} module is missing or empty')
    else:
        try:
            first_row = quality_module['data'][0]
            if len(first_row) < 2:
                raise ValueError
            float(first_row[1])
        except (TypeError, ValueError, IndexError):
            errors.append(f'{FASTQC_REQUIRED_MODULE} module is malformed')

    return modules, errors


def validate_fastqc_report(
    data_path: Optional[str],
    zip_path: Optional[str],
    html_path: Optional[str],
    recover: bool = False,
) -> Dict[str, Any]:
    """Validate that one FastQC report is usable by the VizR results UI."""
    errors = []
    warnings = []
    recovered = False
    source = None
    text = None
    modules = {}
    extracted_errors = []

    if not html_path or not os.path.isfile(html_path) or os.path.getsize(html_path) == 0:
        errors.append('FastQC HTML report is missing or empty')

    if data_path and os.path.isfile(data_path) and os.path.getsize(data_path) > 0:
        try:
            extracted_text = Path(data_path).read_text(encoding='utf-8')
            extracted_modules, extracted_errors = _validate_fastqc_text(extracted_text)
            if not extracted_errors:
                text = extracted_text
                modules = extracted_modules
                source = 'extracted'
        except (OSError, UnicodeDecodeError) as exc:
            extracted_errors = [f'Unable to read extracted {FASTQC_DATA_NAME}: {exc}']

    if text is None:
        zip_text, zip_error = _read_fastqc_zip(zip_path)
        if zip_error:
            errors.append(zip_error)
            errors.extend(extracted_errors)
        elif zip_text is not None:
            zip_modules, zip_validation_errors = _validate_fastqc_text(zip_text)
            if zip_validation_errors:
                errors.extend(zip_validation_errors)
                errors.extend(extracted_errors)
            else:
                text = zip_text
                modules = zip_modules
                source = 'zip'
                if extracted_errors:
                    warnings.append(
                        f"Extracted {FASTQC_DATA_NAME} was unusable; used ZIP instead: "
                        + '; '.join(extracted_errors)
                    )
                if recover and data_path:
                    try:
                        Path(data_path).parent.mkdir(parents=True, exist_ok=True)
                        Path(data_path).write_text(zip_text, encoding='utf-8')
                        source = 'recovered'
                        recovered = True
                    except OSError as exc:
                        warnings.append(f'Unable to recover {FASTQC_DATA_NAME}: {exc}')

    return {
        'valid': not errors,
        'errors': errors,
        'warnings': warnings,
        'modules': modules,
        'source': source,
        'recovered': recovered,
        'data_path': data_path,
        'zip_path': zip_path,
        'html_path': html_path,
    }

def get_workbench_path(workbench_id: int) -> str:
    """Get the workbench directory path using workbench schema (user-based path separation)"""
    try:
        from backend.utils.database import get_vizr_workbench_by_id
        from backend.blueprints.workbench_utils import get_workbench_schema

        # Get workbench info from database
        workbench = get_vizr_workbench_by_id(workbench_id)
        if not workbench:
            raise ValueError(f"Workbench with ID {workbench_id} not found in database")

        # Get workbench schema with user-based path separation
        workbench_name = workbench['name'].replace(' ', '_').replace('/', '_').replace('\\', '_')
        user_id = workbench['user_id']
        schema = get_workbench_schema(workbench_name, user_id)

        return schema['base']

    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        raise ImportError("Required modules not available for workbench path resolution") from e

def collect_fastqc_files(workbench_id: int) -> List[str]:
    """
    Collect all fastqc_data.txt file paths from the workbench

    Args:
        workbench_id: Workbench identifier

    Returns:
        List of file paths to fastqc_data.txt files
    """
    try:
        workbench_path = get_workbench_path(workbench_id)
        # Pattern to find all fastqc_data.txt files
        # Path structure: {workbench}/quanti/qc/fastqc/{group}/{sample}/{filename}/fastqc_data.txt
        fastqc_pattern = os.path.join(workbench_path, 'quanti', 'qc', 'fastqc', '**', 'fastqc_data.txt')

        files = glob.glob(fastqc_pattern, recursive=True)
        logger.info(f"Found {len(files)} FastQC result files for workbench {workbench_id}")

        return files

    except Exception as e:
        logger.error(f"Error collecting FastQC files for workbench {workbench_id}: {e}")
        return []


def collect_fastqc_reports(workbench_id: int) -> List[Dict[str, Optional[str]]]:
    """Collect extracted and ZIP-only FastQC reports without double counting."""
    workbench_path = get_workbench_path(workbench_id)
    root = os.path.join(workbench_path, 'quanti', 'qc', 'fastqc')
    reports: Dict[str, Dict[str, Optional[str]]] = {}

    for data_path in glob.glob(os.path.join(root, '**', FASTQC_DATA_NAME), recursive=True):
        report_base = os.path.dirname(data_path)
        reports.setdefault(report_base, {})['data_path'] = data_path

    for zip_path in glob.glob(os.path.join(root, '**', '*_fastqc.zip'), recursive=True):
        report_base = zip_path[:-4]
        reports.setdefault(report_base, {})['zip_path'] = zip_path

    for html_path in glob.glob(os.path.join(root, '**', '*_fastqc.html'), recursive=True):
        report_base = html_path[:-5]
        reports.setdefault(report_base, {})['html_path'] = html_path

    collected = []
    for report_base in sorted(reports):
        report = reports[report_base]
        collected.append({
            'report_base': report_base,
            'data_path': report.get('data_path') or os.path.join(report_base, FASTQC_DATA_NAME),
            'zip_path': report.get('zip_path') or f'{report_base}.zip',
            'html_path': report.get('html_path') or f'{report_base}.html',
        })
    return collected

def parse_fastqc_file(file_path: str) -> Dict[str, Any]:
    """
    Parse a fastqc_data.txt file and extract structured data

    Args:
        file_path: Path to the fastqc_data.txt file

    Returns:
        Dictionary containing parsed modules with their status and data
    """
    try:
        text = Path(file_path).read_text(encoding='utf-8')
        modules = _parse_fastqc_text(text)
        logger.debug(f"Successfully parsed {len(modules)} modules from {file_path}")
        return modules

    except Exception as e:
        logger.error(f"Error parsing FastQC file {file_path}: {e}")
        return {}

def extract_sample_info_from_path(file_path: str) -> Dict[str, str]:
    """
    Extract sample information from the file path

    Args:
        file_path: Path to the fastqc_data.txt file

    Returns:
        Dictionary containing sample_id, sample_name, and group_name
    """
    try:
        # Path structure: .../fastqc/{group}/{sample}/{filename}/fastqc_data.txt
        path_parts = Path(file_path).parts

        # Find the index of 'fastqc' directory
        fastqc_idx = path_parts.index('fastqc')

        if fastqc_idx + 3 < len(path_parts):
            group_name = path_parts[fastqc_idx + 1]
            sample_name = path_parts[fastqc_idx + 2]
            filename = path_parts[fastqc_idx + 3]

            # Generate sample ID (combine group, sample name, and filename for uniqueness)
            # Include filename to ensure uniqueness for paired-end data (_1 and _2 files)
            sample_id = f"{group_name}_{sample_name}_{filename}"

            return {
                'sample_id': sample_id,
                'sample_name': sample_name,
                'group_name': group_name,
                'filename': filename
            }
    except (ValueError, IndexError) as e:
        logger.warning(f"Could not extract sample info from path {file_path}: {e}")

    # Fallback: use filename as sample name
    filename = os.path.basename(os.path.dirname(file_path))

    return {
        'sample_id': filename,
        'sample_name': filename,
        'group_name': 'unknown',
        'filename': filename
    }

def extract_summary(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract summary information from Basic Statistics module

    Args:
        parsed_data: Parsed FastQC data

    Returns:
        Dictionary containing filename, totalSequences, avgLength, avgQuality
    """
    summary = {
        'filename': 'N/A',
        'totalSequences': 'N/A',
        'avgLength': 0,
        'avgQuality': 0.0
    }

    try:
        # Extract from Basic Statistics module
        if 'Basic Statistics' in parsed_data:
            basic_stats = parsed_data['Basic Statistics']['data']

            for row in basic_stats:
                if len(row) >= 2:
                    metric_name = row[0]
                    metric_value = row[1]

                    if metric_name == 'Filename':
                        summary['filename'] = metric_value
                    elif metric_name == 'Total Sequences':
                        summary['totalSequences'] = metric_value
                    elif metric_name == 'Sequence length':
                        # Handle range (e.g., "35-76") or single value
                        if '-' in metric_value:
                            lengths = metric_value.split('-')
                            summary['avgLength'] = int((int(lengths[0]) + int(lengths[1])) / 2)
                        else:
                            summary['avgLength'] = int(metric_value)

        # Calculate average quality from Per base sequence quality
        if 'Per base sequence quality' in parsed_data:
            quality_data = parsed_data['Per base sequence quality']['data']

            if quality_data:
                total_quality = 0
                count = 0

                for row in quality_data:
                    if len(row) >= 2:  # Must have at least position and mean
                        try:
                            mean_quality = float(row[1])  # Mean is typically in the second column
                            total_quality += mean_quality
                            count += 1
                        except (ValueError, IndexError):
                            continue

                if count > 0:
                    summary['avgQuality'] = round(total_quality / count, 1)

    except Exception as e:
        logger.warning(f"Error extracting summary: {e}")

    return summary

def transform_to_chart_data(parsed_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Transform parsed FastQC data to frontend chart format

    Args:
        parsed_data: Parsed FastQC data

    Returns:
        Dictionary containing chart-ready data for each metric
    """
    metrics = {}

    try:
        # Per base sequence quality
        if 'Per base sequence quality' in parsed_data:
            quality_data = []
            for row in parsed_data['Per base sequence quality']['data']:
                if len(row) >= 7:
                    quality_data.append({
                        'position': row[0],
                        'mean': float(row[1]),
                        'median': float(row[2]),
                        'q25': float(row[3]),  # Lower Quartile
                        'q75': float(row[4]),  # Upper Quartile
                        'p10': float(row[5]),  # 10th Percentile
                        'p90': float(row[6])   # 90th Percentile
                    })
            metrics['per_base_quality'] = quality_data

        # Per sequence quality scores
        if 'Per sequence quality scores' in parsed_data:
            quality_scores = []
            for row in parsed_data['Per sequence quality scores']['data']:
                if len(row) >= 2:
                    quality_scores.append({
                        'value': int(row[0]),
                        'count': float(row[1])
                    })
            metrics['per_sequence_quality'] = quality_scores

        # Per base sequence content
        if 'Per base sequence content' in parsed_data:
            content_data = []
            for row in parsed_data['Per base sequence content']['data']:
                if len(row) >= 5:
                    content_data.append({
                        'position': row[0],
                        'G': float(row[1]),
                        'A': float(row[2]),
                        'T': float(row[3]),
                        'C': float(row[4])
                    })
            metrics['per_base_sequence_content'] = content_data

        # Per sequence GC content
        if 'Per sequence GC content' in parsed_data:
            gc_content = []
            for row in parsed_data['Per sequence GC content']['data']:
                if len(row) >= 2:
                    gc_content.append({
                        'value': int(row[0]),
                        'count': float(row[1])
                    })
            metrics['per_sequence_gc_content'] = gc_content

        # Per base N content
        if 'Per base N content' in parsed_data:
            n_content = []
            for row in parsed_data['Per base N content']['data']:
                if len(row) >= 2:
                    n_content.append({
                        'name': row[0],  # Position
                        'value': float(row[1])
                    })
            metrics['per_base_n_content'] = n_content

        # Sequence Length Distribution
        if 'Sequence Length Distribution' in parsed_data:
            length_dist = []
            for row in parsed_data['Sequence Length Distribution']['data']:
                if len(row) >= 2:
                    # Handle range (e.g., "35-36") or single value
                    length_value = row[0]
                    if '-' in length_value:
                        parts = length_value.split('-')
                        avg_length = (int(parts[0]) + int(parts[1])) / 2
                    else:
                        avg_length = int(length_value)

                    length_dist.append({
                        'value': avg_length,
                        'count': float(row[1])
                    })
            metrics['sequence_length_distribution'] = length_dist

        # Adapter Content
        if 'Adapter Content' in parsed_data:
            adapter_content = []
            data = parsed_data['Adapter Content']['data']
            headers = parsed_data['Adapter Content']['headers']

            # Find adapter column indices (skip Position column)
            adapter_columns = [i for i, h in enumerate(headers) if i > 0]

            for row in data:
                if len(row) > 1:
                    # Sum all adapter percentages for simplicity
                    total_adapter = 0
                    for col_idx in adapter_columns:
                        if col_idx < len(row):
                            try:
                                total_adapter += float(row[col_idx])
                            except (ValueError, IndexError):
                                pass

                    adapter_content.append({
                        'name': row[0],  # Position
                        'value': total_adapter
                    })
            metrics['adapter_content'] = adapter_content

        # Sequence Duplication Levels
        if 'Sequence Duplication Levels' in parsed_data:
            duplication = []
            for row in parsed_data['Sequence Duplication Levels']['data']:
                if len(row) >= 2:
                    duplication.append({
                        'name': row[0],  # Duplication level
                        'value': float(row[1])  # Percentage
                    })
            metrics['duplication_levels'] = duplication

    except Exception as e:
        logger.error(f"Error transforming data to chart format: {e}")

    return metrics

def calculate_module_statistics(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate module statistics without determining overall status

    Args:
        parsed_data: Parsed FastQC data

    Returns:
        Dictionary containing pass/warn/fail counts and module details
    """
    statistics = {
        'pass_count': 0,
        'warn_count': 0,
        'fail_count': 0,
        'total_modules': 0,
        'module_details': {},
        'failed_modules': [],
        'warned_modules': []
    }

    for module_name, module_data in parsed_data.items():
        status = module_data.get('status', '').lower()
        statistics['total_modules'] += 1
        statistics['module_details'][module_name] = {'status': status}

        if status == 'pass':
            statistics['pass_count'] += 1
        elif status == 'warn':
            statistics['warn_count'] += 1
            statistics['warned_modules'].append(module_name)
        elif status == 'fail':
            statistics['fail_count'] += 1
            statistics['failed_modules'].append(module_name)

    logger.debug(f"Module statistics: Pass={statistics['pass_count']}, Warn={statistics['warn_count']}, Fail={statistics['fail_count']}")
    return statistics

def calculate_sample_qc_status(statistics: Dict[str, Any]) -> str:
    """
    Calculate overall QC status for a sample based on module statistics

    Args:
        statistics: Module statistics from calculate_module_statistics

    Returns:
        Overall QC status: 'passed', 'warning', or 'failed'
        - 'failed': One or more modules failed
        - 'warning': No failures but one or more warnings
        - 'passed': All modules passed
    """
    fail_count = statistics.get('fail_count', 0)
    warn_count = statistics.get('warn_count', 0)
    pass_count = statistics.get('pass_count', 0)

    # Log detailed statistics for debugging
    logger.debug(f"QC Status Calculation - Pass: {pass_count}, Warn: {warn_count}, Fail: {fail_count}")

    if fail_count > 0:
        status = 'failed'
    elif warn_count > 0:
        status = 'warning'
    else:
        status = 'passed'

    logger.debug(f"Final QC Status: {status}")
    return status

def calculate_module_level_statistics(samples: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Calculate module-level statistics by aggregating individual FastQC module results
    across all samples.

    Args:
        samples: List of sample dictionaries containing 'statistics' field

    Returns:
        Dictionary with aggregated module statistics:
        - total_samples: Number of samples processed
        - total_modules: Total number of FastQC modules across all samples
        - passed_modules: Total number of passed modules
        - warning_modules: Total number of warning modules
        - failed_modules: Total number of failed modules
    """
    total_samples = len(samples)
    total_passed = 0
    total_warnings = 0
    total_failed = 0

    for sample in samples:
        if 'statistics' in sample:
            stats = sample['statistics']
            total_passed += stats.get('pass_count', 0)
            total_warnings += stats.get('warn_count', 0)
            total_failed += stats.get('fail_count', 0)

    total_modules = total_passed + total_warnings + total_failed

    module_stats = {
        'total_samples': total_samples,
        'total_modules': total_modules,
        'passed_modules': total_passed,
        'warning_modules': total_warnings,
        'failed_modules': total_failed
    }

    logger.info(f"Module-level Statistics:")
    logger.info(f"  Total Samples: {total_samples}")
    logger.info(f"  Total Modules: {total_modules}")
    logger.info(f"  Passed Modules: {total_passed}")
    logger.info(f"  Warning Modules: {total_warnings}")
    logger.info(f"  Failed Modules: {total_failed}")

    return module_stats

def load_ai_analysis_result(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Load AI analysis result from the same directory as FastQC data

    Args:
        file_path: Path to fastqc_data.txt file

    Returns:
        AI analysis dictionary or None if not found
    """
    try:
        # AI analysis file is in the same directory as fastqc_data.txt
        fastqc_dir = os.path.dirname(file_path)
        ai_analysis_file = os.path.join(fastqc_dir, 'ai_analysis.json')

        if not os.path.exists(ai_analysis_file):
            logger.info(f"[AI-ANALYSIS-PARSER] AI analysis file not found: {ai_analysis_file}")
            return None

        with open(ai_analysis_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        logger.info(f"[AI-ANALYSIS-PARSER] Loaded AI analysis from {ai_analysis_file}")
        logger.info(f"[AI-ANALYSIS-PARSER] Data content: status={data.get('ai_analysis_status')}, reason={data.get('ai_analysis_reason')}")
        return data  # Return full data including status and reason

    except Exception as e:
        logger.warning(f"Could not load AI analysis for {file_path}: {e}")
        return None

def process_fastqc_for_sample(
    file_path: str,
    validation: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Process a single FastQC file and return sample data

    Args:
        file_path: Path to fastqc_data.txt file

    Returns:
        Sample dictionary with all required fields or None if error
    """
    try:
        # Extract sample information from path
        sample_info = extract_sample_info_from_path(file_path)

        # Use the shared validation result so execution and display agree.
        parsed_data = validation['modules'] if validation else parse_fastqc_file(file_path)

        if not parsed_data:
            logger.warning(f"No data parsed from {file_path}")
            return None

        # Transform to chart data
        chart_data = transform_to_chart_data(parsed_data)

        # Calculate statistics and overall QC status
        statistics = calculate_module_statistics(parsed_data)
        qc_status = calculate_sample_qc_status(statistics)

        # Load AI analysis result if exists
        ai_analysis_result = load_ai_analysis_result(file_path)

        # Extract AI analysis components
        ai_analysis = None
        ai_analysis_status = None
        ai_analysis_reason = None

        if ai_analysis_result:
            ai_analysis = ai_analysis_result.get('ai_analysis')
            ai_analysis_status = ai_analysis_result.get('ai_analysis_status')
            ai_analysis_reason = ai_analysis_result.get('ai_analysis_reason')

        # Create sample object
        # _sample_name and _filename are internal fields used by get_all_qc_results()
        # to determine the final display name (SE vs PE) after all samples are collected.
        sample = {
            'id': sample_info['sample_id'],
            'name': sample_info['sample_name'],          # temporary; overwritten in get_all_qc_results()
            '_sample_name': sample_info['sample_name'],  # user-defined sample name (internal)
            '_filename': sample_info['filename'],        # FastQC output dir name for PE R1/R2 ordering (internal)
            'group': sample_info['group_name'],
            'qc_status': qc_status,  # Overall QC status: passed/warning/failed
            'statistics': statistics,  # Module statistics
            'summary': extract_summary(parsed_data),
            'metrics': chart_data,
            'file_path': file_path,
            'ai_analysis': ai_analysis,  # AI analysis result if available
            'ai_analysis_status': ai_analysis_status,  # AI analysis status
            'ai_analysis_reason': ai_analysis_reason   # AI analysis reason
        }

        logger.debug(f"Successfully processed sample: {sample['_sample_name']} ({sample['_filename']}) with {statistics['pass_count']} passes, {statistics['warn_count']} warnings, {statistics['fail_count']} failures")
        return sample

    except Exception as e:
        logger.error(f"Error processing FastQC file {file_path}: {e}")
        return None


def _get_expected_qc_file_count(workbench_id: int) -> int:
    """Read the latest expected file count while remaining compatible with old jobs."""
    try:
        from backend.utils.database import get_db_connection
        with get_db_connection() as conn:
            row = conn.execute('''
                SELECT progress_detail
                FROM pipeline_job_steps
                WHERE workbench_id = ? AND step_name = 'qc'
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (workbench_id,)).fetchone()
        if row and row['progress_detail']:
            progress = json.loads(row['progress_detail'])
            return max(0, int(progress.get('total_files', 0)))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Unable to determine expected QC file count for {workbench_id}: {exc}")
    return 0

def get_all_qc_results(workbench_id: int) -> Dict[str, Any]:
    """
    Get all QC results for a workbench

    Args:
        workbench_id: Workbench identifier

    Returns:
        Dictionary containing workbench_id, samples list, and total count
    """
    try:
        reports = collect_fastqc_reports(workbench_id)
        expected_count = _get_expected_qc_file_count(workbench_id) or len(reports)

        if not reports:
            return {
                'workbench_id': workbench_id,
                'samples': [],
                'total_count': 0,
                'expected_count': expected_count,
                'parsed_count': 0,
                'failed_count': expected_count,
                'result_status': 'unavailable',
                'errors': [{'report': None, 'errors': ['No FastQC result artifacts were found']}],
                'message': 'No displayable FastQC results found'
            }

        # Process each file
        samples = []
        validation_errors = []
        for report in reports:
            validation = validate_fastqc_report(
                report['data_path'], report['zip_path'], report['html_path'], recover=False
            )
            if not validation['valid']:
                validation_errors.append({
                    'report': os.path.basename(report['report_base']),
                    'errors': validation['errors'],
                })
                continue
            sample = process_fastqc_for_sample(report['data_path'], validation)
            if sample:
                samples.append(sample)
            else:
                validation_errors.append({
                    'report': os.path.basename(report['report_base']),
                    'errors': ['FastQC report could not be transformed for display'],
                })

        missing_count = max(expected_count - len(reports), 0)
        if missing_count:
            validation_errors.append({
                'report': None,
                'errors': [f'{missing_count} expected FastQC report(s) were not found'],
            })

        # Sort samples by name (temporary, will re-sort after final name assignment)
        samples.sort(key=lambda x: x['name'])

        # Determine final display name: use user-defined sample_name,
        # appending _1/_2 suffix for PE samples.
        from collections import defaultdict
        pe_groups = defaultdict(list)
        for sample in samples:
            key = (sample['group'], sample['_sample_name'])
            pe_groups[key].append(sample)

        for key, group_samples in pe_groups.items():
            sample_name = key[1]
            if len(group_samples) == 1:
                # SE: show user-defined sample name as-is
                group_samples[0]['name'] = sample_name
            else:
                # PE: sort by filename (_1 before _2) then assign _1/_2 suffix
                group_samples.sort(key=lambda s: s['_filename'])
                for idx, s in enumerate(group_samples, start=1):
                    s['name'] = f"{sample_name}_{idx}"

        # Remove internal temporary fields before returning
        for sample in samples:
            sample.pop('_sample_name', None)
            sample.pop('_filename', None)

        # Re-sort by final display name
        samples.sort(key=lambda x: x['name'])

        # Calculate sample-level QC statistics
        total_samples = len(samples)
        passed_samples = len([s for s in samples if s['qc_status'] == 'passed'])
        warning_samples = len([s for s in samples if s['qc_status'] == 'warning'])
        failed_samples = len([s for s in samples if s['qc_status'] == 'failed'])

        sample_stats = {
            'total_samples': total_samples,
            'passed_samples': passed_samples,
            'warning_samples': warning_samples,
            'failed_samples': failed_samples
        }

        logger.info(f"Workbench {workbench_id} Sample-level QC Statistics:")
        logger.info(f"  Total Samples: {total_samples}")
        logger.info(f"  Passed: {passed_samples}")
        logger.info(f"  Warnings: {warning_samples}")
        logger.info(f"  Failed: {failed_samples}")

        # Calculate module-level statistics
        module_stats = calculate_module_level_statistics(samples)

        parsed_count = len(samples)
        failed_count = max(expected_count - parsed_count, len(validation_errors))
        if parsed_count == 0:
            result_status = 'unavailable'
        elif failed_count > 0:
            result_status = 'partial'
        else:
            result_status = 'ready'

        return {
            'workbench_id': workbench_id,
            'samples': samples,
            'total_count': parsed_count,
            'expected_count': expected_count,
            'parsed_count': parsed_count,
            'failed_count': failed_count,
            'result_status': result_status,
            'errors': validation_errors,
            'sample_statistics': sample_stats,
            'module_statistics': module_stats,
            'message': 'Success' if result_status == 'ready' else 'Some FastQC results are unavailable'
        }

    except Exception as e:
        logger.error(f"Error getting QC results for workbench {workbench_id}: {e}")
        return {
            'workbench_id': workbench_id,
            'samples': [],
            'total_count': 0,
            'expected_count': 0,
            'parsed_count': 0,
            'failed_count': 0,
            'result_status': 'unavailable',
            'errors': [{'report': None, 'errors': [str(e)]}],
            'message': f'Error: {str(e)}'
        }
