#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QC AI Analyzer Module
AI-powered analysis engine for FastQC results using Claude API
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

# Configure logging
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


class QCAIAnalyzer:
    """FastQC result analyzer using AI model wrapper"""

    def __init__(self, user_id: Optional[int] = None):
        """
        Initialize the AI analyzer using AIModelWrapper

        Args:
            user_id: User ID for AI settings (required for background processes)
        """
        from .ai_model_wrapper import AIModelWrapper
        self.ai_wrapper = AIModelWrapper(user_id=user_id)

        if not self.ai_wrapper.is_available():
            logger.warning("AI wrapper not available. AI analysis will be disabled.")
        else:
            logger.info("AI analyzer initialized successfully using wrapper")

    def analyze_qc_results(
        self,
        fastqc_data: Dict[str, Any],
        sample_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze FastQC results using AI

        Args:
            fastqc_data: Parsed FastQC modules data
            sample_metadata: Sample information (name, group, experiment_type)

        Returns:
            AI analysis results dictionary
        """
        if not self.ai_wrapper.is_available():
            logger.warning("AI analyzer not available. Returning default analysis.")
            return self._get_default_analysis()

        try:
            logger.info("Starting QC analysis with AI...")

            # Calculate statistics for the prompt
            from backend.utils.fastqc_parser import calculate_module_statistics
            statistics = calculate_module_statistics(fastqc_data)
            logger.info(f"Statistics calculated: {statistics}")

            # Build the analysis prompt
            from .qc_analysis_prompts import build_analysis_prompt
            prompt = build_analysis_prompt(fastqc_data, sample_metadata, statistics)
            logger.info(f"Prompt length: {len(prompt)} characters")
            logger.debug(f"Full prompt:\n{prompt}")

            # Call AI API through wrapper
            start_time = time.time()

            # Use AIModelWrapper to generate response
            response_result = self.ai_wrapper.generate_response(prompt)
            processing_time = time.time() - start_time

            # Check if AI wrapper response is successful
            if not response_result['success']:
                logger.error(f"AI wrapper failed: {response_result.get('error', 'Unknown error')}")
                return self._get_error_analysis(response_result.get('error', 'AI response failed'))

            # Get response text from wrapper result
            response_text = response_result.get('response_text', '')

            logger.debug(f"Raw AI response (first 200 chars): {response_text[:200]}")

            # Clean response text (remove any markdown formatting)
            logger.debug(f"Original response text: {repr(response_text)}")

            # Remove markdown code blocks more thoroughly
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            elif response_text.startswith("```"):
                response_text = response_text[3:]

            if response_text.endswith("```"):
                response_text = response_text[:-3]

            response_text = response_text.strip()

            # Remove any remaining newlines at the beginning
            while response_text.startswith('\n'):
                response_text = response_text[1:]

            logger.debug(f"Cleaned response text: {repr(response_text)}")

            # Validate response before JSON parsing
            if not response_text:
                logger.error("Empty response from Gemini")
                return self._get_error_analysis("Empty response from AI")

            if not response_text.startswith('{'):
                logger.error(f"Response doesn't start with '{{': {response_text[:100]}")
                return self._get_error_analysis("Invalid JSON format - missing opening brace")

            if not response_text.endswith('}'):
                logger.error(f"Response doesn't end with '}}': ...{response_text[-100:]}")

                return self._get_error_analysis("Invalid JSON format - incomplete response")

            # Try to parse JSON with better error handling
            try:
                logger.debug("Attempting to parse JSON...")
                analysis = json.loads(response_text)
                logger.debug(f"JSON parsing successful. Keys found: {list(analysis.keys())}")

                # Validate required fields
                required_fields = ['overall_assessment', 'confidence_score', 'quality_evaluation', 'recommendations', 'expected_outcomes']
                missing_fields = [field for field in required_fields if field not in analysis]

                if missing_fields:
                    logger.error(f"Missing required fields in AI response: {missing_fields}")
                    logger.error(f"Available fields: {list(analysis.keys())}")
                    logger.error(f"Full parsed JSON: {analysis}")
                    return self._get_error_analysis(f"Incomplete response - missing: {', '.join(missing_fields)}")

                analysis['processing_time'] = processing_time
                logger.info(f"AI analysis completed successfully in {processing_time:.2f} seconds")
                return analysis

            except json.JSONDecodeError as json_error:
                logger.error(f"JSON parsing failed: {json_error}")
                logger.error(f"Problematic JSON: {response_text}")
                return self._get_error_analysis(f"JSON parsing error: {str(json_error)}")

        except Exception as e:
            # Handle AI wrapper errors
            error_msg = str(e)
            if "quota" in error_msg.lower() or "limit" in error_msg.lower():
                logger.error(f"AI API quota/rate limit exceeded: {e}")
                return self._get_error_analysis("API quota exceeded")
            elif "safety" in error_msg.lower():
                logger.error(f"AI safety filter triggered: {e}")
                return self._get_error_analysis("Content filtered by safety system")
            elif "blocked" in error_msg.lower():
                logger.error(f"Content blocked by AI: {e}")
                return self._get_error_analysis("Content blocked")
            else:
                # Log more details for debugging
                logger.error(f"AI analysis failed: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                if hasattr(e, '__dict__'):
                    logger.error(f"Error details: {e.__dict__}")

                # Check if it's an incomplete response error
                error_str = str(e)
                if "overall_assessment" in error_str or "{" in error_str:
                    logger.error("Appears to be incomplete JSON response from AI")
                    return self._get_error_analysis("Incomplete JSON response - API may have hit token limit")

                return self._get_error_analysis(str(e))

    def _get_default_analysis(self) -> Dict[str, Any]:
        """
        Get default analysis when AI is not available

        Returns:
            Default analysis structure
        """
        return {
            "overall_assessment": "AI analysis not available. Please review FastQC results manually.",
            "confidence_score": 0.0,
            "experiment_type": "unknown",
            "quality_evaluation": {
                "usability": "unknown",
                "notes": ["AI analysis unavailable"],
                "strengths": []
            },
            "recommendations": {
                "immediate_actions": ["Manual review required"],
                "preprocessing": [],
                "downstream_considerations": []
            },
            "expected_outcomes": {
                "alignment_rate": "Unknown",
                "sequence_quality": "Unknown",
                "coverage_uniformity": "Unknown"
            }
        }

    def _get_error_analysis(self, error_message: str) -> Dict[str, Any]:
        """
        Get error analysis structure

        Args:
            error_message: Error description

        Returns:
            Error analysis structure
        """
        return {
            "overall_assessment": f"AI analysis failed: {error_message}",
            "confidence_score": 0.0,
            "experiment_type": "unknown",
            "quality_evaluation": {
                "usability": "unknown",
                "notes": [f"Analysis error: {error_message}"],
                "strengths": []
            },
            "recommendations": {
                "immediate_actions": ["Retry analysis or review manually"],
                "preprocessing": [],
                "downstream_considerations": []
            },
            "expected_outcomes": {
                "alignment_rate": "Unknown",
                "sequence_quality": "Unknown",
                "coverage_uniformity": "Unknown"
            },
            "error": error_message
        }


def save_ai_analysis_result(
    workbench_id: int,
    sample_info: Dict[str, Any],
    ai_analysis: Dict[str, Any],
    fastqc_result_path: str
) -> str:
    """
    Save AI analysis result in the same directory as FastQC results

    Args:
        workbench_id: Workbench identifier
        sample_info: Sample information
        ai_analysis: AI analysis results
        fastqc_result_path: Path to FastQC result directory

    Returns:
        Path to saved file
    """
    try:
        # AI analysis file path (same directory as FastQC results)
        ai_analysis_file = os.path.join(fastqc_result_path, 'ai_analysis.json')

        # Create complete result structure
        result = {
            "sample_info": sample_info,
            "analysis_metadata": {
                "ai_model": "AI Model Wrapper",
                "ai_provider": "Configurable AI Provider",
                "analyzer_version": "2.0.0",
                "experiment_type": sample_info.get('experiment_type', 'RNA-seq'),
                "analysis_timestamp": datetime.now().isoformat(),
                "fastqc_result_path": fastqc_result_path,
                "workbench_id": workbench_id
            },
            "ai_analysis": ai_analysis
        }

        # Save to JSON file
        with open(ai_analysis_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        logger.info(f"AI analysis saved: {ai_analysis_file}")
        return ai_analysis_file

    except Exception as e:
        logger.error(f"Failed to save AI analysis: {e}")
        raise


def perform_post_fastqc_ai_analysis(
    sample_info: Dict[str, Any],
    fastqc_result_path: str,
    workbench_id: int,
    experiment_type: str = 'RNA-seq'
) -> Dict[str, Any]:
    """
    Perform AI analysis after FastQC completion

    Args:
        sample_info: Sample information
        fastqc_result_path: Path to FastQC result directory
        workbench_id: Workbench identifier
        experiment_type: Type of experiment

    Returns:
        Analysis result with status
    """
    try:
        from backend.utils.fastqc_parser import parse_fastqc_file

        # Parse FastQC data
        # FastQC creates files in {filename}_fastqc subdirectory
        fastqc_data_path = None

        # Find the _fastqc subdirectory
        if os.path.exists(fastqc_result_path):
            for item in os.listdir(fastqc_result_path):
                item_path = os.path.join(fastqc_result_path, item)
                if os.path.isdir(item_path) and item.endswith('_fastqc'):
                    potential_data_path = os.path.join(item_path, 'fastqc_data.txt')
                    if os.path.exists(potential_data_path):
                        fastqc_data_path = potential_data_path
                        break

        if not fastqc_data_path or not os.path.exists(fastqc_data_path):
            # List available files for debugging
            available_files = []
            if os.path.exists(fastqc_result_path):
                for root, dirs, files in os.walk(fastqc_result_path):
                    for file in files:
                        available_files.append(os.path.join(root, file))

            error_msg = f"FastQC data file not found in: {fastqc_result_path}"
            if available_files:
                error_msg += f"\nAvailable files: {available_files[:5]}"  # Show first 5 files
            raise FileNotFoundError(error_msg)

        # Parse the FastQC data
        parsed_data = parse_fastqc_file(fastqc_data_path)

        if not parsed_data:
            raise ValueError("Failed to parse FastQC data")

        # Prepare sample metadata for AI analysis
        sample_metadata = {
            'sample_name': sample_info.get('sample_name'),
            'group_name': sample_info.get('group_name'),
            'experiment_type': experiment_type,
            'workbench_id': workbench_id
        }

        # Get user_id from workbench for AI analysis
        user_id = None
        try:
            from backend.utils.database import get_user_by_workbench_id
            user_info = get_user_by_workbench_id(workbench_id)

            if user_info:
                user_id = user_info['id']
                logger.debug(f"Found user_id {user_id} for workbench {workbench_id}")
            else:
                logger.warning(f"No user found for workbench {workbench_id}")
        except Exception as e:
            logger.error(f"Failed to get user_id for workbench {workbench_id}: {e}")

        # Perform AI analysis
        analyzer = QCAIAnalyzer(user_id=user_id)
        analysis_result = analyzer.analyze_qc_results(
            fastqc_data=parsed_data,
            sample_metadata=sample_metadata
        )

        # Save the analysis result in the same directory as fastqc_data.txt
        fastqc_dir = os.path.dirname(fastqc_data_path)  # Get the _fastqc directory
        ai_file_path = save_ai_analysis_result(
            workbench_id=workbench_id,
            sample_info=sample_info,
            ai_analysis=analysis_result,
            fastqc_result_path=fastqc_dir  # Use the _fastqc directory
        )

        logger.info(f"AI analysis completed for {sample_info.get('sample_name', 'Unknown')}")

        return {
            'status': 'success',
            'analysis': analysis_result,
            'ai_file_path': ai_file_path,
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"AI analysis failed for {sample_info.get('sample_name', 'Unknown')}: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }