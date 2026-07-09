#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAI API Client Module
Provides a unified interface for interacting with OpenAI Chat Completions API
"""

import os
import time
import logging
from typing import Dict, Any, Optional
from flask import session

# Configure logging
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

class OpenAIClient:
    """OpenAI Chat Completions API client"""

    def __init__(self, user_id: int, api_key: str, model_name: str = "gpt-4o"):
        """
        Initialize the OpenAI client

        Args:
            user_id: User ID for this client
            api_key: OpenAI API key
            model_name: Model name to use (default: gpt-4o)
        """
        self.user_id = user_id
        self.api_key = api_key
        self.model_name = model_name
        self.client = None

        if not self.api_key:
            logger.warning(f"No OpenAI API key found for user {self.user_id}. Client will not be functional.")
        else:
            try:
                from openai import OpenAI
                import httpx

                # httpx 클라이언트를 명시적으로 생성하여 프록시 관련 충돌 방지
                http_client = httpx.Client(timeout=60.0)

                # OpenAI 클라이언트 생성 시 명시적 http_client 사용
                self.client = OpenAI(
                    api_key=self.api_key,
                    http_client=http_client
                )
                logger.info(f"OpenAI client initialized with model: {self.model_name} for user {self.user_id}")
            except ImportError:
                logger.error("OpenAI library not installed. Run: pip install openai")
                raise ImportError("openai package is required")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                raise

    def generate_response(
        self,
        prompt: str,
        max_tokens: int = 8000,
        temperature: float = 0.1,
        top_p: float = 0.8,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0
    ) -> Dict[str, Any]:
        """
        Generate response using OpenAI Chat Completions API

        Args:
            prompt: Input prompt text
            max_tokens: Maximum tokens in response (default: 8000)
            temperature: Randomness control (0.0-2.0, default: 0.1)
            top_p: Nucleus sampling parameter (default: 0.8)
            frequency_penalty: Frequency penalty (-2.0 to 2.0, default: 0.0)
            presence_penalty: Presence penalty (-2.0 to 2.0, default: 0.0)

        Returns:
            Dictionary containing response data and metadata
        """
        if not self.client:
            raise RuntimeError("OpenAI client not initialized properly")

        try:
            logger.info("Generating response with OpenAI...")
            start_time = time.time()

            # Prepare messages for Chat Completions API
            messages = [
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            # Make API call
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty
            )

            processing_time = time.time() - start_time

            # Extract response content
            if not response.choices or len(response.choices) == 0:
                logger.error("No choices returned from OpenAI API")
                return {
                    'success': False,
                    'error': 'No response choices from API',
                    'response_text': '',
                    'processing_time': processing_time
                }

            choice = response.choices[0]

            # Check finish reason
            if choice.finish_reason == 'content_filter':
                logger.error("Content filtered by OpenAI safety system")
                return {
                    'success': False,
                    'error': 'Content blocked by safety filters',
                    'response_text': '',
                    'processing_time': processing_time
                }

            response_text = choice.message.content if choice.message.content else ""

            # Clean response text (remove markdown formatting if present)
            cleaned_text = self._clean_response_text(response_text)

            # Log usage information (but don't include in return for format consistency)
            if response.usage:
                logger.info(f"Token usage - Prompt: {response.usage.prompt_tokens}, "
                           f"Completion: {response.usage.completion_tokens}, "
                           f"Total: {response.usage.total_tokens}")

            logger.info(f"Response generated successfully in {processing_time:.2f} seconds")

            # Generation config for consistency
            generation_config = {
                'max_tokens': max_tokens,
                'temperature': temperature,
                'top_p': top_p,
                'frequency_penalty': frequency_penalty,
                'presence_penalty': presence_penalty
            }

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

            # Handle specific OpenAI API errors
            if "quota" in error_msg.lower() or "billing" in error_msg.lower():
                logger.error(f"OpenAI API quota/billing issue: {e}")
                error_type = "quota_exceeded"
            elif "rate_limit" in error_msg.lower() or "rate limit" in error_msg.lower():
                logger.error(f"OpenAI API rate limit exceeded: {e}")
                error_type = "rate_limit"
            elif "invalid_api_key" in error_msg.lower() or "unauthorized" in error_msg.lower():
                logger.error(f"OpenAI API authentication failed: {e}")
                error_type = "auth_error"
            elif "content_policy" in error_msg.lower() or "safety" in error_msg.lower():
                logger.error(f"Content filtered by OpenAI safety system: {e}")
                error_type = "content_blocked"
            else:
                logger.error(f"OpenAI API error: {e}")
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
        return self.client is not None

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
        Test the connection to OpenAI API with a simple request

        Returns:
            Dictionary with test results
        """
        try:
            # Initialize OpenAI client for testing
            if not self.api_key:
                return {
                    'success': False,
                    'error': 'API key not provided'
                }

            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            except Exception as e:
                return {'success': False, 'error': f'Failed to initialize OpenAI client: {str(e)}'}

            test_response = self.generate_response(
                prompt="Hello, respond with just 'OK'",
                max_tokens=10,
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