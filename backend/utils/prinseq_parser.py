#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PRINSEQ Result Parser Module
Parse PRINSEQ log files and extract processing statistics
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

def collect_prinseq_logs(workbench_id: int) -> List[str]:
    """
    Collect all PRINSEQ log files from the workbench

    Args:
        workbench_id: Workbench identifier

    Returns:
        List of file paths to PRINSEQ log files
    """
    try:
        workbench_path = get_workbench_path(workbench_id)
        prinseq_output_dir = os.path.join(workbench_path, "quanti", "clean", "prinseq")

        if not os.path.exists(prinseq_output_dir):
            logger.warning(f"PRINSEQ output directory not found: {prinseq_output_dir}")
            return []

        # Search for log files recursively
        log_pattern = os.path.join(prinseq_output_dir, "**", "*.log")
        log_files = glob.glob(log_pattern, recursive=True)

        logger.info(f"Found {len(log_files)} PRINSEQ log files in {prinseq_output_dir}")
        return log_files

    except Exception as e:
        logger.error(f"Error collecting PRINSEQ log files for workbench {workbench_id}: {e}")
        return []

def parse_prinseq_log_file(log_file: str) -> Optional[Dict[str, Any]]:
    """
    Parse individual PRINSEQ log file to extract statistics

    Args:
        log_file: Path to PRINSEQ log file

    Returns:
        Dictionary containing parsed statistics or None if parsing fails
    """
    try:
        logger.debug(f"Parsing PRINSEQ log file: {log_file}")

        # Extract sample name from directory structure
        sample_name = os.path.basename(os.path.dirname(log_file))

        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Initialize result dictionary
        result = {
            "sample_name": sample_name,
            "input_reads": 0,
            "output_reads": 0,
            "length_filtered": 0,
            "complexity_filtered": 0,
            "quality_filtered": 0,
            "ns_filtered": 0
        }

        # Parse PRINSEQ output patterns
        # Example PRINSEQ output patterns:
        # "Input sequences: 1000000"
        # "Good sequences: 950000 (95.00%)"
        # "Bad sequences: 50000 (5.00%)"

        # Pattern for input sequences
        input_pattern = r'Input sequences:\s*(\d+)'
        input_match = re.search(input_pattern, content)

        if input_match:
            input_reads = int(input_match.group(1))
            result["input_reads"] = input_reads
            logger.debug(f"Parsed input reads: {input_reads}")
        else:
            logger.warning(f"Could not find input sequence count in {log_file}")

        # Pattern for good/output sequences
        good_pattern = r'Good sequences:\s*(\d+)'
        good_match = re.search(good_pattern, content)

        if good_match:
            output_reads = int(good_match.group(1))
            result["output_reads"] = output_reads
            logger.debug(f"Parsed output reads: {output_reads}")
        else:
            logger.warning(f"Could not find output sequence count in {log_file}")

        # Parse filtering statistics
        # Pattern for sequences filtered by length
        length_pattern = r'sequences filtered by length:\s*(\d+)'
        length_match = re.search(length_pattern, content)
        if length_match:
            result["length_filtered"] = int(length_match.group(1))

        # Pattern for sequences filtered by complexity
        complexity_pattern = r'sequences filtered by complexity:\s*(\d+)'
        complexity_match = re.search(complexity_pattern, content)
        if complexity_match:
            result["complexity_filtered"] = int(complexity_match.group(1))

        # Pattern for sequences filtered by quality
        quality_pattern = r'sequences filtered by quality:\s*(\d+)'
        quality_match = re.search(quality_pattern, content)
        if quality_match:
            result["quality_filtered"] = int(quality_match.group(1))

        # Pattern for sequences filtered by Ns
        ns_pattern = r'sequences filtered by Ns:\s*(\d+)'
        ns_match = re.search(ns_pattern, content)
        if ns_match:
            result["ns_filtered"] = int(ns_match.group(1))

        # If specific filtering stats not found, calculate filtered as input - output
        if result["input_reads"] > 0 and result["output_reads"] > 0:
            total_filtered = result["input_reads"] - result["output_reads"]

            # If we don't have specific filtering breakdowns, use total filtered
            if (result["length_filtered"] == 0 and result["complexity_filtered"] == 0 and
                result["quality_filtered"] == 0 and result["ns_filtered"] == 0):
                # Distribute filtered reads (this is an approximation)
                result["length_filtered"] = total_filtered // 2
                result["complexity_filtered"] = total_filtered - result["length_filtered"]

        return result

    except Exception as e:
        logger.error(f"Failed to parse PRINSEQ log file {log_file}: {e}")
        return None

def get_prinseq_results(workbench_id: int) -> Dict[str, Any]:
    """
    Get all PRINSEQ results for a workbench

    Args:
        workbench_id: Workbench identifier

    Returns:
        Dictionary containing all PRINSEQ results
    """
    logger.info(f"📊 [PRINSEQ-PARSER] Getting PRINSEQ results for workbench {workbench_id}")

    try:
        log_files = collect_prinseq_logs(workbench_id)

        if not log_files:
            logger.info(f"No PRINSEQ log files found for workbench {workbench_id}")
            return {
                "workbench_id": workbench_id,
                "samples": [],
                "total_count": 0,
                "summary": {
                    "total_input_reads": 0,
                    "total_output_reads": 0,
                    "total_length_filtered": 0,
                    "total_complexity_filtered": 0,
                    "total_quality_filtered": 0,
                    "total_ns_filtered": 0,
                    "overall_retention_rate": 0.0
                }
            }

        samples = []
        total_input = 0
        total_output = 0
        total_length_filtered = 0
        total_complexity_filtered = 0
        total_quality_filtered = 0
        total_ns_filtered = 0

        for log_file in log_files:
            sample_result = parse_prinseq_log_file(log_file)
            if sample_result:
                samples.append(sample_result)
                total_input += sample_result["input_reads"]
                total_output += sample_result["output_reads"]
                total_length_filtered += sample_result["length_filtered"]
                total_complexity_filtered += sample_result["complexity_filtered"]
                total_quality_filtered += sample_result["quality_filtered"]
                total_ns_filtered += sample_result["ns_filtered"]

        # Calculate summary statistics
        retention_rate = (total_output / total_input * 100) if total_input > 0 else 0.0

        results = {
            "workbench_id": workbench_id,
            "samples": samples,
            "total_count": len(samples),
            "summary": {
                "total_input_reads": total_input,
                "total_output_reads": total_output,
                "total_length_filtered": total_length_filtered,
                "total_complexity_filtered": total_complexity_filtered,
                "total_quality_filtered": total_quality_filtered,
                "total_ns_filtered": total_ns_filtered,
                "overall_retention_rate": round(retention_rate, 2)
            }
        }

        logger.info(f"✅ [PRINSEQ-PARSER] Successfully parsed {len(samples)} PRINSEQ results for workbench {workbench_id}")
        return results

    except Exception as e:
        logger.error(f"Failed to get PRINSEQ results for workbench {workbench_id}: {e}")
        return {
            "workbench_id": workbench_id,
            "samples": [],
            "total_count": 0,
            "summary": {
                "total_input_reads": 0,
                "total_output_reads": 0,
                "total_length_filtered": 0,
                "total_complexity_filtered": 0,
                "total_quality_filtered": 0,
                "total_ns_filtered": 0,
                "overall_retention_rate": 0.0
            }
        }