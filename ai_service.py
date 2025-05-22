"""AI Service for LinkedIn Research Pipeline
========================================
Handles all AI API calls for research and email generation using various providers.
"""

import json
from datetime import datetime
from typing import Dict
import streamlit as st
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)
import litellm
from litellm import completion
from prompts import get_email_prompt, get_research_prompt


class AIService:
    """Handles AI API calls for research and email generation."""
    
    def __init__(self, config):
        self.config = config
    
    def save_api_response(self, provider: str, profile_name: str, payload: Dict):
        """Save API response to file."""
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        safe_name = (profile_name or "unknown").replace("/", "-")
        path = self.config.responses_dir / provider / f"{safe_name}_{ts}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
    
    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(min=2, max=10),
           retry=retry_if_exception_type(Exception), reraise=True)
    def research_call(self, profile: Dict, api_key: str, max_tokens: int, timeout: int) -> str:
        """Make research API call."""
        query = get_research_prompt(profile)
        messages = [
            {"role": "system", "content": "You are a helpful research assistant."},
            {"role": "user", "content": query},
        ]
        
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
    
    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(min=2, max=10),
           retry=retry_if_exception_type(Exception), reraise=True)
    def email_call(self, profile: Dict, api_key: str, max_tokens: int, timeout: int) -> str:
        """Make email generation API call."""
        # Get custom prompt from session state if enabled
        custom_prompt = None
        if hasattr(st, 'session_state') and st.session_state.get('use_custom_prompt', False):
            custom_prompt = st.session_state.get('custom_email_prompt')
        
        prompt = get_email_prompt(profile, custom_prompt)
        messages = [
            {"role": "system", "content": "You draft personalized outreach emails."},
            {"role": "user", "content": prompt},
        ]
        
        resp = completion(
            model="openai/gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=max_tokens,
            api_key=api_key,
            timeout=timeout,
        )
        
        self.save_api_response("openai", profile.get("name", ""), resp.to_dict())
        return resp.choices[0].message.content 