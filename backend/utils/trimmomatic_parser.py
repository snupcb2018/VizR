#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trimmomatic Result Parser Module
Parse Trimmomatic log files and extract processing statistics
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

def collect_trimmomatic_logs(workbench_id: int) -> List[str]:
    """
    Collect all Trimmomatic log files from the workbench

    Args:
        workbench_id: Workbench identifier

    Returns:
        List of file paths to Trimmomatic log files
    """
    try:
        workbench_path = get_workbench_path(workbench_id)
        trimmomatic_output_dir = os.path.join(workbench_path, "quanti", "clean", "trimmomatic")

        if not os.path.exists(trimmomatic_output_dir):
            logger.warning(f"Trimmomatic output directory not found: {trimmomatic_output_dir}")
            return []

        # Search for log files recursively
        log_pattern = os.path.join(trimmomatic_output_dir, "**", "*.log")
        log_files = glob.glob(log_pattern, recursive=True)

        logger.info(f"Found {len(log_files)} Trimmomatic log files in {trimmomatic_output_dir}")
        return log_files

    except Exception as e:
        logger.error(f"Error collecting Trimmomatic log files for workbench {workbench_id}: {e}")
        return []

def parse_trimmomatic_log_file(log_file: str) -> Optional[Dict[str, Any]]:
    """
    Parse individual Trimmomatic log file to extract statistics

    Args:
        log_file: Path to Trimmomatic log file

    Returns:
        Dictionary containing parsed statistics or None if parsing fails
    """
    try:
        logger.debug(f"Parsing Trimmomatic log file: {log_file}")

        # Extract sample name from directory structure
        sample_name = os.path.basename(os.path.dirname(log_file))

        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Initialize result dictionary
        result = {
            "sample_name": sample_name,
            "input_reads": 0,
            "surviving_reads": 0,
            "survival_rate": 0.0,
            "adapter_removed": 0,
            "quality_trimmed": 0
        }

        # Parse Trimmomatic output patterns
        # Example: "Input Read Pairs: 1000000 Both Surviving: 950000 (95.00%) Forward Only Surviving: 30000 (3.00%) Reverse Only Surviving: 15000 (1.50%) Dropped: 5000 (0.50%)"

        # Pattern for paired-end reads
        pe_pattern = r'Input Read Pairs:\s*(\d+)\s+Both Surviving:\s*(\d+)\s*\(([0-9.]+)%\)'
        pe_match = re.search(pe_pattern, content)

        if pe_match:
            input_pairs = int(pe_match.group(1))
            surviving_pairs = int(pe_match.group(2))
            survival_rate = float(pe_match.group(3))

            result["input_reads"] = input_pairs * 2  # Convert pairs to reads
            result["surviving_reads"] = surviving_pairs * 2
            result["survival_rate"] = survival_rate
            result["adapter_removed"] = (input_pairs - surviving_pairs) * 2

            logger.debug(f"Parsed PE data: {input_pairs} pairs -> {surviving_pairs} pairs ({survival_rate}%)")
        else:
            # Pattern for single-end reads
            se_pattern = r'Input Reads:\s*(\d+)\s+Surviving:\s*(\d+)\s*\(([0-9.]+)%\)'
            se_match = re.search(se_pattern, content)

            if se_match:
                input_reads = int(se_match.group(1))
                surviving_reads = int(se_match.group(2))
                survival_rate = float(se_match.group(3))

                result["input_reads"] = input_reads
                result["surviving_reads"] = surviving_reads
                result["survival_rate"] = survival_rate
                result["adapter_removed"] = input_reads - surviving_reads

                logger.debug(f"Parsed SE data: {input_reads} reads -> {surviving_reads} reads ({survival_rate}%)")
            else:
                logger.warning(f"Could not parse Trimmomatic statistics from {log_file}")
                return None

        return result

    except Exception as e:
        logger.error(f"Failed to parse Trimmomatic log file {log_file}: {e}")
        return None

def get_trimmomatic_results(workbench_id: int) -> Dict[str, Any]:
    """
    Get all Trimmomatic results for a workbench

    Args:
        workbench_id: Workbench identifier

    Returns:
        Dictionary containing all Trimmomatic results
    """
    logger.info(f"📊 [TRIMMOMATIC-PARSER] Getting Trimmomatic results for workbench {workbench_id}")

    try:
        log_files = collect_trimmomatic_logs(workbench_id)

        if not log_files:
            logger.info(f"No Trimmomatic log files found for workbench {workbench_id}")
            return {
                "workbench_id": workbench_id,
                "samples": [],
                "total_count": 0,
                "summary": {
                    "total_input_reads": 0,
                    "total_surviving_reads": 0,
                    "average_survival_rate": 0.0,
                    "total_removed": 0
                }
            }

        samples = []
        total_input = 0
        total_surviving = 0
        total_removed = 0

        for log_file in log_files:
            sample_result = parse_trimmomatic_log_file(log_file)
            if sample_result:
                samples.append(sample_result)
                total_input += sample_result["input_reads"]
                total_surviving += sample_result["surviving_reads"]
                total_removed += sample_result["adapter_removed"]

        # Calculate summary statistics
        average_survival_rate = (total_surviving / total_input * 100) if total_input > 0 else 0.0

        results = {
            "workbench_id": workbench_id,
            "samples": samples,
            "total_count": len(samples),
            "summary": {
                "total_input_reads": total_input,
                "total_surviving_reads": total_surviving,
                "average_survival_rate": round(average_survival_rate, 2),
                "total_removed": total_removed
            }
        }

        logger.info(f"✅ [TRIMMOMATIC-PARSER] Successfully parsed {len(samples)} Trimmomatic results for workbench {workbench_id}")
        return results

    except Exception as e:
        logger.error(f"Failed to get Trimmomatic results for workbench {workbench_id}: {e}")
        return {
            "workbench_id": workbench_id,
            "samples": [],
            "total_count": 0,
            "summary": {
                "total_input_reads": 0,
                "total_surviving_reads": 0,
                "average_survival_rate": 0.0,
                "total_removed": 0
            }
        }

def get_all_preprocessing_results(workbench_id: int) -> Dict[str, Any]:
    """
    Get comprehensive preprocessing results including both Trimmomatic and PRINSEQ

    Args:
        workbench_id: Workbench identifier

    Returns:
        Dictionary containing all preprocessing results
    """
    logger.info(f"📊 [PREPROCESSING-PARSER] Getting all preprocessing results for workbench {workbench_id}")

    try:
        trimmomatic_results = get_trimmomatic_results(workbench_id)

        # TODO: Add PRINSEQ results when parser is implemented
        prinseq_results = {
            "workbench_id": workbench_id,
            "samples": [],
            "total_count": 0,
            "summary": {
                "total_input_reads": 0,
                "total_output_reads": 0,
                "total_length_filtered": 0,
                "total_complexity_filtered": 0
            }
        }

        results = {
            "workbench_id": workbench_id,
            "trimmomatic_results": trimmomatic_results,
            "prinseq_results": prinseq_results
        }

        logger.info(f"✅ [PREPROCESSING-PARSER] Successfully compiled preprocessing results for workbench {workbench_id}")
        return results

    except Exception as e:
        logger.error(f"Failed to get preprocessing results for workbench {workbench_id}: {e}")
        return {
            "workbench_id": workbench_id,
            "trimmomatic_results": {"samples": [], "total_count": 0},
            "prinseq_results": {"samples": [], "total_count": 0}
        }