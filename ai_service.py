"""AI Service for LinkedIn Research Pipeline
========================================
Handles all AI API calls for research and email generation using various providers.
"""

import json
import time
import asyncio
from datetime import datetime
from typing import Dict
from collections import deque
import streamlit as st
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential, before_sleep_log)
import litellm
from litellm import completion
from prompts import get_email_prompt, get_research_prompt
import logging


class RateLimiter:
    """Rate limiter for API calls with different limits per provider."""
    
    def __init__(self, openai_rpm_limit: int):
        # OpenAI rate limits (adjust based on your tier)
        # Tier 1: 500 RPM, 200,000 TPM
        # Tier 2: 5,000 RPM, 2,000,000 TPM  
        # Tier 3: 10,000 RPM, 4,000,000 TPM
        self.openai_rpm_limit = openai_rpm_limit
        self.openai_request_times = deque()
        
        # Perplexity is generally more lenient
        self.perplexity_rpm_limit = 1000  # Requests per minute
        self.perplexity_request_times = deque()
        
        self.logger = logging.getLogger("rate_limiter")
    
    def can_make_request(self, provider: str) -> bool:
        """Check if we can make a request without hitting rate limits."""
        current_time = time.time()
        
        if provider == "openai":
            request_times = self.openai_request_times
            rpm_limit = self.openai_rpm_limit
        else:  # perplexity
            request_times = self.perplexity_request_times
            rpm_limit = self.perplexity_rpm_limit
        
        # Remove requests older than 1 minute
        while request_times and current_time - request_times[0] > 60:
            request_times.popleft()
        
        return len(request_times) < rpm_limit
    
    def wait_for_rate_limit(self, provider: str):
        """Wait until we can make a request within rate limits."""
        while not self.can_make_request(provider):
            self.logger.info(f"Rate limit reached for {provider}, waiting 1 second...")
            time.sleep(1)
    
    def record_request(self, provider: str):
        """Record that a request was made."""
        current_time = time.time()
        
        if provider == "openai":
            self.openai_request_times.append(current_time)
        else:  # perplexity
            self.perplexity_request_times.append(current_time)


class AIService:
    """Handles AI API calls for research and email generation."""
    
    def __init__(self, config):
        self.config = config
        # Initialize rate limiter with configurable OpenAI RPM limit
        openai_rpm_limit = getattr(config, 'openai_rpm_limit', 500)  # Default to 500 if not provided
        self.rate_limiter = RateLimiter(openai_rpm_limit=openai_rpm_limit)
        self.logger = logging.getLogger("ai_service")
    
    def update_rate_limit(self, openai_rpm_limit: int):
        """Update the OpenAI rate limit configuration."""
        self.rate_limiter.openai_rpm_limit = openai_rpm_limit
        self.logger.info(f"Updated OpenAI rate limit to {openai_rpm_limit} RPM")
    
    def save_api_response(self, provider: str, profile_name: str, payload: Dict):
        """Save API response to file."""
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        safe_name = (profile_name or "unknown").replace("/", "-")
        path = self.config.responses_dir / provider / f"{safe_name}_{ts}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
    
    def _is_rate_limit_error(self, exception):
        """Check if the exception is a rate limit error."""
        error_str = str(exception).lower()
        return any(phrase in error_str for phrase in [
            'rate limit', 'too many requests', '429', 'quota exceeded',
            'requests per minute', 'rpm', 'rate_limit_exceeded'
        ])
    
    def _log_retry_attempt(self, retry_state):
        """Log retry attempts for debugging."""
        self.logger.warning(f"Retrying API call (attempt {retry_state.attempt_number}): {retry_state.outcome.exception()}")
    
    @retry(
        stop=stop_after_attempt(5),  # Increased retry attempts
        wait=wait_exponential(multiplier=2, min=4, max=60),  # Longer waits for rate limits
        retry=retry_if_exception_type((Exception,)),
        before_sleep=before_sleep_log(logging.getLogger("ai_service"), logging.WARNING),
        reraise=True
    )
    def research_call(self, profile: Dict, api_key: str, max_tokens: int, timeout: int) -> str:
        """Make research API call with rate limiting."""
        # Wait for rate limit if necessary
        self.rate_limiter.wait_for_rate_limit("perplexity")
        
        query = get_research_prompt(profile)
        messages = [
            {"role": "system", "content": "You are a helpful research assistant."},
            {"role": "user", "content": query},
        ]
        
        try:
            # Record the request
            self.rate_limiter.record_request("perplexity")
            
            resp = completion(
                model="perplexity/sonar",
                messages=messages,
                temperature=0.7,
                max_tokens=max_tokens,
                api_key=api_key,
                timeout=timeout,
            )
            
            self.save_api_response("perplexity", profile.get("name", ""), resp.to_dict())
            return resp.choices[0].message.content
            
        except Exception as e:
            if self._is_rate_limit_error(e):
                self.logger.warning(f"Rate limit hit for Perplexity: {e}")
                # Extra wait for rate limit errors
                time.sleep(5)
            raise e
    
    @retry(
        stop=stop_after_attempt(5),  # Increased retry attempts
        wait=wait_exponential(multiplier=2, min=4, max=60),  # Longer waits for rate limits
        retry=retry_if_exception_type((Exception,)),
        before_sleep=before_sleep_log(logging.getLogger("ai_service"), logging.WARNING),
        reraise=True
    )
    def email_call(self, profile: Dict, api_key: str, max_tokens: int, timeout: int) -> str:
        """Make email generation API call with rate limiting."""
        # Wait for rate limit if necessary
        self.rate_limiter.wait_for_rate_limit("openai")
        
        # Get custom prompt from session state if enabled
        custom_prompt = None
        if hasattr(st, 'session_state') and st.session_state.get('use_custom_prompt', False):
            custom_prompt = st.session_state.get('custom_email_prompt')
        
        prompt = get_email_prompt(profile, custom_prompt)
        messages = [
            {"role": "system", "content": "You draft personalized outreach emails."},
            {"role": "user", "content": prompt},
        ]
        
        try:
            # Record the request
            self.rate_limiter.record_request("openai")
            
            resp = completion(
                model="openai/gpt-4o-mini",  # Using gpt-4o-mini for better rate limits
                messages=messages,
                temperature=0.7,
                max_tokens=max_tokens,
                api_key=api_key,
                timeout=timeout,
            )
            
            self.save_api_response("openai", profile.get("name", ""), resp.to_dict())
            return resp.choices[0].message.content
            
        except Exception as e:
            if self._is_rate_limit_error(e):
                self.logger.warning(f"Rate limit hit for OpenAI: {e}")
                # Extra wait for rate limit errors
                time.sleep(10)  # Longer wait for OpenAI rate limits
            raise e 