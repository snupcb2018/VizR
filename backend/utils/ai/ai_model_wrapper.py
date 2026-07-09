#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Model Wrapper Module
Provides unified interface for all AI providers
"""

import logging
from typing import Dict, Any, Optional, Union
from flask import session

# Configure logging
from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

class AIModelWrapper:
    """Unified wrapper for all AI providers"""

    def __init__(self, user_id: Optional[int] = None):
        """
        Initialize the AI wrapper and load user settings

        Args:
            user_id: User ID for direct access (for background processes)
        """
        self._client = None
        self._user_id = user_id
        self._provider = None
        self._model = None
        self._analysis_enabled = None
        self._api_key = None

        # Load user settings and create client during initialization
        try:
            # Import here to avoid circular imports
            from backend.blueprints.settings import UserSettings

            # user_id must be provided via constructor
            if not self._user_id:
                logger.warning("No user_id provided to AIModelWrapper. Cannot load AI settings.")
                return

            logger.info(f"Loading AI settings for user_id: {self._user_id}")

            # Get AI settings
            ai_settings = UserSettings.get_values(self._user_id, [
                'ai.provider',
                'ai.model',
                'ai.analysis_enabled',
                'ai.api_key'
            ])

            self._provider = ai_settings.get('ai.provider')
            self._model = ai_settings.get('ai.model')
            self._analysis_enabled = ai_settings.get('ai.analysis_enabled', True)
            self._api_key = ai_settings.get('ai.api_key')

            logger.info(f"Parsed settings - user_id: {self._user_id}, provider: {self._provider}, model: {self._model}, enabled: {self._analysis_enabled}, has_api_key: {bool(self._api_key)}")

            # Create AI client immediately if all conditions are met
            if self._analysis_enabled and self._provider and self._model and self._api_key:
                try:
                    if self._provider == 'google':
                        from .ai_model_google import GoogleAIClient
                        self._client = GoogleAIClient(user_id=self._user_id, api_key=self._api_key, model_name=self._model)
                    elif self._provider == 'openai':
                        from .ai_model_openai import OpenAIClient
                        self._client = OpenAIClient(user_id=self._user_id, api_key=self._api_key, model_name=self._model)
                    elif self._provider == 'anthropic':
                        from .ai_model_anthropy import AnthropicClient
                        self._client = AnthropicClient(user_id=self._user_id, api_key=self._api_key, model_name=self._model)
                    else:
                        logger.error(f"Unsupported AI provider: {self._provider}")

                    if self._client:
                        logger.info(f"AI client created: {self._provider} - {self._model} for user {self._user_id}")

                except Exception as client_error:
                    logger.error(f"Failed to create AI client: {client_error}")
                    self._client = None

        except Exception as e:
            logger.error(f"Failed to load user settings: {e}")


    def generate_response(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate AI response using configured provider

        Args:
            prompt: Input prompt text
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            Dictionary containing response data and metadata
        """
        try:
            # Check if user_id is available
            if not self._user_id:
                return {
                    'success': False,
                    'error': 'No user_id available',
                    'response_text': '',
                    'processing_time': 0.0
                }

            if not self._analysis_enabled:
                logger.warning(f"AI analysis disabled for user {self._user_id}, cannot generate response")
                return {
                    'success': False,
                    'error': 'AI analysis is disabled. Please enable it in settings.',
                    'response_text': '',
                    'processing_time': 0.0
                }

            if not self._client:
                return {
                    'success': False,
                    'error': 'AI client not available',
                    'response_text': '',
                    'processing_time': 0.0
                }

            # Call generate_response with provider-specific parameters
            logger.info(f"Generating AI response for user {self._user_id} using {self._provider}/{self._model}")

            # Set provider-specific default parameters
            if self._provider == 'google':
                # Google Gemini parameters
                params = {
                    'max_output_tokens': kwargs.get('max_output_tokens', 8000),
                    'temperature': kwargs.get('temperature', 0.1),
                    'top_p': kwargs.get('top_p', 0.8),
                    'top_k': kwargs.get('top_k', 10)
                }
            elif self._provider == 'openai':
                # OpenAI parameters with model-specific token limits
                default_tokens = 8000
                if 'gpt-3.5-turbo' in self._model.lower():
                    default_tokens = 3000  # Safe margin for GPT-3.5-turbo (4096 limit)
                elif 'gpt-4' in self._model.lower():
                    default_tokens = 8000  # GPT-4 supports higher limits

                # Apply model limit to any provided token count
                requested_tokens = kwargs.get('max_tokens', kwargs.get('max_output_tokens', default_tokens))
                safe_tokens = min(requested_tokens, default_tokens)  # Ensure we don't exceed model limits

                params = {
                    'max_tokens': safe_tokens,
                    'temperature': kwargs.get('temperature', 0.1),
                    'top_p': kwargs.get('top_p', 0.8),
                    'frequency_penalty': kwargs.get('frequency_penalty', 0.0),
                    'presence_penalty': kwargs.get('presence_penalty', 0.0)
                }
            elif self._provider == 'anthropic':
                # Anthropic Claude parameters
                params = {
                    'max_tokens': kwargs.get('max_tokens', kwargs.get('max_output_tokens', 8000)),
                    'temperature': kwargs.get('temperature', 0.1),
                    'top_p': kwargs.get('top_p', 0.8),
                    'top_k': kwargs.get('top_k', 10)
                }
            else:
                # Fallback to kwargs
                params = kwargs

            return self._client.generate_response(prompt, **params)

        except Exception as e:
            logger.error(f"Failed to generate AI response: {e}")
            return {
                'success': False,
                'error': str(e),
                'response_text': '',
                'processing_time': 0.0
            }

    def test_connection(self, provider: str = None, model: str = None, api_key: str = None) -> Dict[str, Any]:
        """
        Test AI connection with provided or current user settings

        Args:
            provider: AI provider to test (optional, uses user settings if not provided)
            model: Model name to test (optional, uses user settings if not provided)
            api_key: API key to test (optional, uses user settings if not provided)

        Returns:
            Dictionary with test results
        """
        try:
            # If parameters provided, use them for testing (for Test Connection button)
            if provider and model and api_key:
                logger.info(f"Testing AI connection with provided credentials: {provider}/{model}")

                # Create appropriate client based on provider and test with provided API key
                if provider == 'google':
                    from .ai_model_google import GoogleAIClient
                    # Create temporary client with provided credentials
                    temp_client = GoogleAIClient(user_id=self._user_id, api_key=api_key, model_name=model)
                    return temp_client.test_connection()
                elif provider == 'openai':
                    from .ai_model_openai import OpenAIClient
                    # Create temporary client with provided credentials
                    temp_client = OpenAIClient(user_id=self._user_id, api_key=api_key, model_name=model)
                    return temp_client.test_connection()
                elif provider == 'anthropic':
                    from .ai_model_anthropy import AnthropicClient
                    # Create temporary client with provided credentials
                    temp_client = AnthropicClient(user_id=self._user_id, api_key=api_key, model_name=model)
                    return temp_client.test_connection()
                else:
                    return {
                        'success': False,
                        'error': f'Unsupported provider: {provider}'
                    }

            # Otherwise, use current user settings
            if not self._user_id:
                return {
                    'success': False,
                    'error': 'No user_id available'
                }

            if not self._analysis_enabled:
                return {
                    'success': False,
                    'error': 'AI analysis is disabled. Please enable it in settings.'
                }

            if not self._client:
                return {
                    'success': False,
                    'error': 'AI client not available'
                }

            logger.info(f"Testing AI connection for user {self._user_id} using {self._provider}/{self._model}")
            return self._client.test_connection()

        except Exception as e:
            logger.error(f"Failed to test AI connection: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def is_available(self) -> bool:
        """
        Check if AI analysis is available for current user

        Returns:
            True if AI is available, False otherwise
        """
        try:
            # Check if user_id is available
            if not self._user_id:
                return False

            # First check: is AI analysis enabled?
            if not self._analysis_enabled:
                logger.debug(f"AI analysis disabled for user {self._user_id}")
                return False

            # Second check: can we get a working client?
            is_available = self._client is not None and self._client.is_available()

            if is_available:
                logger.debug(f"AI available for user {self._user_id}: {self._provider}/{self._model}")
            else:
                logger.debug(f"AI not available for user {self._user_id}")

            return is_available
        except Exception as e:
            logger.error(f"Error checking AI availability: {e}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get current AI model information

        Returns:
            Dictionary with model information
        """
        try:
            if not self._client:
                return {
                    'provider': self._provider,
                    'model': self._model,
                    'user_id': self._user_id,
                    'analysis_enabled': self._analysis_enabled,
                    'client_available': False
                }

            model_info = self._client.get_model_info()
            model_info['provider'] = self._provider
            model_info['analysis_enabled'] = self._analysis_enabled
            return model_info

        except Exception as e:
            logger.error(f"Failed to get model info: {e}")
            return {
                'error': str(e),
                'client_available': False
            }

