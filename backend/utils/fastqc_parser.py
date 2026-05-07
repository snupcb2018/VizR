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
from typing import List, Dict, Optional, Any
from pathlib import Path

# Configure logging
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

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

def parse_fastqc_file(file_path: str) -> Dict[str, Any]:
    """
    Parse a fastqc_data.txt file and extract structured data

    Args:
        file_path: Path to the fastqc_data.txt file

    Returns:
        Dictionary containing parsed modules with their status and data
    """
    modules = {}
    current_module = None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n')

                if line.startswith('>>'):
                    if line.startswith('>>END_MODULE'):
                        current_module = None
                    else:
                        # Parse module header: >>Module Name\tstatus
                        parts = line[2:].split('\t')  # Remove >> prefix
                        module_name = parts[0]
                        module_status = parts[1] if len(parts) > 1 else 'unknown'

                        current_module = module_name
                        modules[current_module] = {
                            'status': module_status,
                            'data': [],
                            'headers': []
                        }

                elif current_module and line.startswith('#'):
                    # Header line - extract column names
                    if line != '#' and '\t' in line:
                        headers = line[1:].split('\t')  # Remove # prefix
                        modules[current_module]['headers'] = headers

                elif current_module and line and not line.startswith('#'):
                    # Data line
                    modules[current_module]['data'].append(line.split('\t'))

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

def process_fastqc_for_sample(file_path: str) -> Optional[Dict[str, Any]]:
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

        # Parse FastQC data
        parsed_data = parse_fastqc_file(file_path)

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

def get_all_qc_results(workbench_id: int) -> Dict[str, Any]:
    """
    Get all QC results for a workbench

    Args:
        workbench_id: Workbench identifier

    Returns:
        Dictionary containing workbench_id, samples list, and total count
    """
    try:
        # Collect all FastQC files
        fastqc_files = collect_fastqc_files(workbench_id)

        if not fastqc_files:
            return {
                'workbench_id': workbench_id,
                'samples': [],
                'total_count': 0,
                'message': 'No FastQC results found'
            }

        # Process each file
        samples = []
        for file_path in fastqc_files:
            sample = process_fastqc_for_sample(file_path)
            if sample:
                samples.append(sample)

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

        return {
            'workbench_id': workbench_id,
            'samples': samples,
            'total_count': len(samples),
            'sample_statistics': sample_stats,
            'module_statistics': module_stats,
            'message': 'Success'
        }

    except Exception as e:
        logger.error(f"Error getting QC results for workbench {workbench_id}: {e}")
        return {
            'workbench_id': workbench_id,
            'samples': [],
            'total_count': 0,
            'message': f'Error: {str(e)}'
        }