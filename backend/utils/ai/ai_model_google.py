#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Generative AI API Client Module
Provides a unified interface for interacting with Google Gemini models
"""

import os
import time
import logging
from typing import Dict, Any, Optional
from flask import session

# Configure logging
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

class GoogleAIClient:
    """Google Generative AI API client for Gemini models"""

    def __init__(self, user_id: int, api_key: str, model_name: str = "gemini-2.5-pro"):
        """
        Initialize the Google AI client

        Args:
            user_id: User ID for this client
            api_key: Google API key
            model_name: Model name to use (default: gemini-2.5-pro)
        """
        self.user_id = user_id
        self.api_key = api_key
        self.model_name = model_name
        self.model = None

        if not self.api_key:
            logger.warning(f"No Google API key provided for user {self.user_id}. Client will not be functional.")
        else:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
                logger.info(f"Google AI client initialized with model: {self.model_name} for user {self.user_id}")
            except ImportError:
                logger.error("Google Generative AI library not installed. Run: pip install google-generativeai")
                raise ImportError("google-generativeai package is required")
            except Exception as e:
                logger.error(f"Failed to initialize Google AI client: {e}")
                raise

    def generate_response(
        self,
        prompt: str,
        max_output_tokens: int = 8000,
        temperature: float = 0.1,
        top_p: float = 0.8,
        top_k: int = 10
    ) -> Dict[str, Any]:
        """
        Generate response using Google Gemini model

        Args:
            prompt: Input prompt text
            max_output_tokens: Maximum tokens in response (default: 8000)
            temperature: Randomness control (0.0-1.0, default: 0.1)
            top_p: Nucleus sampling parameter (default: 0.8)
            top_k: Top-k sampling parameter (default: 10)

        Returns:
            Dictionary containing response data and metadata
        """
        if not self.model:
            raise RuntimeError("Google AI client not initialized properly")

        try:
            logger.info("Generating response with Google Gemini...")
            start_time = time.time()

            # Configure generation parameters
            generation_config = {
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k
            }

            # Safety settings to prevent content blocking (same as qc_ai_analyzer.py)
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]

            # Generate content
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config,
                safety_settings=safety_settings
            )

            processing_time = time.time() - start_time

            # Check for valid response object
            if not response:
                logger.error("No response object from Google Gemini API")
                return {
                    'success': False,
                    'error': 'No response from API',
                    'response_text': '',
                    'processing_time': processing_time
                }


            # Safe response text extraction with finish_reason check
            response_text = ""
            if hasattr(response, 'candidates') and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    if candidate.finish_reason == 1:  # STOP (normal completion)
                        try:
                            response_text = response.text if response.text else ""
                        except Exception:
                            response_text = ""
                    elif candidate.finish_reason == 2:  # MAX_TOKENS
                        logger.warning("Response truncated due to max_tokens limit")
                        try:
                            response_text = response.text if response.text else ""
                        except Exception:
                            # Even with truncation, consider it a successful connection test
                            return {
                                'success': True,
                                'response_text': 'Connection successful (response truncated)',
                                'raw_response_text': 'Connection successful',
                                'processing_time': processing_time,
                                'model_name': self.model_name,
                                'generation_config': generation_config
                            }
                    elif candidate.finish_reason == 3:  # SAFETY
                        logger.warning("Response blocked by safety filters")
                        return {
                            'success': False,
                            'error': 'Response blocked by safety filters',
                            'response_text': '',
                            'processing_time': processing_time
                        }
                    else:
                        logger.warning(f"Unexpected finish_reason: {candidate.finish_reason}")
                        try:
                            response_text = response.text if response.text else ""
                        except Exception:
                            response_text = ""
                else:
                    # No finish_reason, try to get text anyway
                    try:
                        response_text = response.text if response.text else ""
                    except Exception as text_error:
                        logger.error(f"Could not access response.text: {text_error}")
                        return {
                            'success': False,
                            'error': f'Could not access response text: {str(text_error)}',
                            'response_text': '',
                            'processing_time': processing_time
                        }
            else:
                logger.error("No candidates in response")
                return {
                    'success': False,
                    'error': 'No response candidates',
                    'response_text': '',
                    'processing_time': processing_time
                }

            # Clean response text (remove markdown formatting if present)
            cleaned_text = self._clean_response_text(response_text)

            logger.info(f"Response generated successfully in {processing_time:.2f} seconds")

            return {
                'success': True,
                'response_text': cleaned_text,
                'raw_response_text': response_text,
                'processing_time': processing_time,
                'model_name': self.model_name,
                'generation_config': generation_config
            }

        except Exception as e:
            error_msg = str(e)

            # Handle specific API errors
            if "quota" in error_msg.lower() or "limit" in error_msg.lower():
                logger.error(f"Google AI API quota/rate limit exceeded: {e}")
                error_type = "quota_exceeded"
            elif "safety" in error_msg.lower() or "blocked" in error_msg.lower():
                logger.error(f"Content filtered by safety system: {e}")
                error_type = "content_blocked"
            else:
                logger.error(f"Google AI API error: {e}")
                error_type = "api_error"

            return {
                'success': False,
                'error': error_msg,
                'error_type': error_type,
                'response_text': '',
                'processing_time': 0.0
            }

    def _clean_response_text(self, text: str) -> str:
        """
        Clean response text by removing markdown formatting

        Args:
            text: Raw response text

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        cleaned = text.strip()

        # Remove markdown code blocks
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        # Remove leading newlines
        while cleaned.startswith('\n'):
            cleaned = cleaned[1:]

        return cleaned.strip()

    def is_available(self) -> bool:
        """
        Check if the client is properly initialized and available

        Returns:
            True if client is available, False otherwise
        """
        return self.model is not None

    def get_model_info(self) -> Dict[str, str]:
        """
        Get information about the current model

        Returns:
            Dictionary with model information
        """
        return {
            'model_name': self.model_name,
            'api_key_configured': bool(self.api_key),
            'client_available': self.is_available(),
            'user_id': self.user_id
        }

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to Google Gemini API with a simple request

        Returns:
            Dictionary with test results
        """
        try:
            # Initialize Google client for testing
            if not self.api_key:
                return {
                    'success': False,
                    'error': 'API key not provided'
                }

            try:
                import google.generativeai as genai

                # Debug API key (FULL KEY - TEMPORARY)
                if self.api_key:
                    logger.info(f"Google AI client test_connection - FULL API key: '{self.api_key}' (length: {len(self.api_key)})")
                    # Clean API key (remove potential whitespace)
                    cleaned_api_key = self.api_key.strip()
                    if cleaned_api_key != self.api_key:
                        logger.warning(f"Google AI client - API key had whitespace, cleaned from '{self.api_key}' to '{cleaned_api_key}'")
                        self.api_key = cleaned_api_key
                else:
                    logger.error(f"Google AI client test_connection - API key is None or empty")

                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
                logger.info(f"Google AI client successfully initialized with model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize Google client: {str(e)}")
                return {'success': False, 'error': f'Failed to initialize Google client: {str(e)}'}

            test_response = self.generate_response(
                prompt="Test connection. Return: OK",
                max_output_tokens=100,
                temperature=0.0
            )

            if test_response['success']:
                return {
                    'success': True,
                    'message': 'Connection test successful',
                    'model': self.model_name,
                    'response_time': test_response['processing_time']
                }
            else:
                return {
                    'success': False,
                    'error': test_response['error']
                }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }