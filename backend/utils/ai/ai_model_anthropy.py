#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anthropic API Client Module
Provides a unified interface for interacting with Anthropic Claude API
"""

import os
import time
import logging
from typing import Dict, Any, Optional
from flask import session

# Configure logging
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

class AnthropicClient:
    """Anthropic Claude API client"""

    def __init__(self, user_id: int, api_key: str, model_name: str = "claude-3-7-sonnet-20250219"):
        """
        Initialize the Anthropic client

        Args:
            user_id: User ID for this client
            api_key: Anthropic API key
            model_name: Model name to use (default: claude-3-5-sonnet-20241022)
        """
        self.user_id = user_id
        self.api_key = api_key
        self.model_name = model_name
        self.client = None

        if not self.api_key:
            logger.warning(f"No Anthropic API key found for user {self.user_id}. Client will not be functional.")
        else:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
                logger.info(f"Anthropic client initialized with model: {self.model_name} for user {self.user_id}")
            except ImportError:
                logger.error("Anthropic library not installed. Run: pip install anthropic")
                raise ImportError("anthropic package is required")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {e}")
                raise

    def generate_response(
        self,
        prompt: str,
        max_tokens: int = 8000,
        temperature: float = 0.1,
        top_p: float = 0.8,
        top_k: int = 10
    ) -> Dict[str, Any]:
        """
        Generate response using Anthropic Claude API

        Args:
            prompt: Input prompt text
            max_tokens: Maximum tokens in response (default: 8000)
            temperature: Randomness control (0.0-1.0, default: 0.1)
            top_p: Nucleus sampling parameter (default: 0.8)
            top_k: Top-k sampling parameter (default: 10)

        Returns:
            Dictionary containing response data and metadata
        """
        if not self.client:
            raise RuntimeError("Anthropic client not initialized properly")

        try:
            logger.info("Generating response with Anthropic Claude...")
            start_time = time.time()

            # Create message for Claude API
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            processing_time = time.time() - start_time

            # Extract response content
            if not response.content or len(response.content) == 0:
                logger.error("No content returned from Anthropic API")
                return {
                    'success': False,
                    'error': 'No response content from API',
                    'response_text': '',
                    'processing_time': processing_time
                }

            # Get the text content from the response
            response_text = ""
            for content in response.content:
                if hasattr(content, 'text'):
                    response_text += content.text

            if not response_text:
                logger.error("No text content in Anthropic API response")
                return {
                    'success': False,
                    'error': 'No text content in response',
                    'response_text': '',
                    'processing_time': processing_time
                }

            # Clean response text (remove markdown formatting if present)
            cleaned_text = self._clean_response_text(response_text)

            # Log usage information (if available)
            if hasattr(response, 'usage'):
                logger.info(f"Token usage - Input: {response.usage.input_tokens}, "
                           f"Output: {response.usage.output_tokens}")

            logger.info(f"Response generated successfully in {processing_time:.2f} seconds")

            # Generation config for consistency
            generation_config = {
                'max_tokens': max_tokens,
                'temperature': temperature,
                'top_p': top_p,
                'top_k': top_k
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

            # Handle specific Anthropic API errors
            if "rate_limit" in error_msg.lower() or "rate limit" in error_msg.lower():
                logger.error(f"Anthropic API rate limit exceeded: {e}")
                error_type = "rate_limit"
            elif "invalid_api_key" in error_msg.lower() or "unauthorized" in error_msg.lower():
                logger.error(f"Anthropic API authentication failed: {e}")
                error_type = "auth_error"
            elif "quota" in error_msg.lower() or "billing" in error_msg.lower():
                logger.error(f"Anthropic API quota/billing issue: {e}")
                error_type = "quota_exceeded"
            elif "content_policy" in error_msg.lower() or "safety" in error_msg.lower():
                logger.error(f"Content filtered by Anthropic safety system: {e}")
                error_type = "content_blocked"
            else:
                logger.error(f"Anthropic API error: {e}")
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
        Test the connection to Anthropic API with a simple request

        Returns:
            Dictionary with test results
        """
        try:
            # Initialize Anthropic client for testing
            if not self.api_key:
                return {
                    'success': False,
                    'error': 'API key not provided'
                }

            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                return {'success': False, 'error': f'Failed to initialize Anthropic client: {str(e)}'}

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