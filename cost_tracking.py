"""Cost tracking and estimation for LinkedIn Research Pipeline
=========================================================
Handles API cost tracking, estimation, and management.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict
import pandas as pd
from litellm import token_counter
from prompts import get_email_prompt, get_research_prompt


class CostTracker:
    """Handles cost tracking for API calls."""
    
    def __init__(self):
        self.reset_tracking()
        
    def reset_tracking(self):
        """Reset cost tracking data."""
        self.cost_data = {
            "perplexity": {"calls": 0, "tokens": 0, "cost": 0.0},
            "openai": {"calls": 0, "tokens": 0, "cost": 0.0},
        }
        self.total_cost = 0.0
    
    def track_cost(self, kwargs, response, *_):
        """Callback function for tracking API costs."""
        provider = "perplexity" if "perplexity" in kwargs.get("model", "").lower() else "openai"
        cost = response.usage.get("cost", 0)
        tokens = response.usage.get("prompt_tokens", 0) + response.usage.get("completion_tokens", 0)
        
        self.cost_data[provider]["calls"] += 1
        self.cost_data[provider]["tokens"] += tokens
        self.cost_data[provider]["cost"] += cost
        self.total_cost += cost
    
    def get_summary(self) -> Dict:
        """Get cost tracking summary."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_cost": self.total_cost,
            "providers": self.cost_data,
        }
    
    def save_summary(self, additional_data: Dict = None):
        """Save cost summary to file."""
        summary = self.get_summary()
        if additional_data:
            summary.update(additional_data)
        Path("api_cost_summary.json").write_text(json.dumps(summary, indent=2))


class CostEstimator:
    """Provides upfront cost estimation for API calls before processing."""
    
    def __init__(self, config):
        self.config = config
        # Model pricing constants (updated as of 2024)
        # Based on litellm pricing and current API pricing
        self.model_configs = {
            "perplexity/sonar": {
                "input_cost_per_token": 0.000001,  # $1 per million tokens
                "output_cost_per_token": 0.000001,  # $1 per million tokens
                "cost_per_request": 0.005,  # $5 per 1000 requests (base rate)
            },
            "openai/gpt-4o-mini": {
                "input_cost_per_token": 0.00000015,  # $0.15 per million tokens  
                "output_cost_per_token": 0.0000006,  # $0.6 per million tokens
                "cost_per_request": 0.0,  # No additional per-request cost
            }
        }
        
        # Estimated output token ratios (based on typical prompt responses)
        self.output_token_ratios = {
            "research": 3.0,  # Research responses are typically 3x longer than prompts
            "email": 0.5,     # Email responses are typically 0.5x the prompt length
        }
    
    def estimate_tokens(self, profile: Dict, task_type: str) -> Dict[str, int]:
        """Estimate input and output tokens for a profile and task type."""
        try:
            if task_type == "research":
                prompt = get_research_prompt(profile)
                messages = [
                    {"role": "system", "content": "You are a helpful research assistant."},
                    {"role": "user", "content": prompt},
                ]
                model = "perplexity/sonar"
            elif task_type == "email":
                prompt = get_email_prompt(profile)
                messages = [
                    {"role": "system", "content": "You draft personalized outreach emails."},
                    {"role": "user", "content": prompt},
                ]
                model = "openai/gpt-4o-mini"
            else:
                raise ValueError(f"Unknown task type: {task_type}")
            
            # Count input tokens
            input_tokens = token_counter(model=model, messages=messages)
            
            # Estimate output tokens based on typical ratios
            output_tokens = int(input_tokens * self.output_token_ratios[task_type])
            
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens
            }
            
        except Exception as e:
            # Fallback estimation if token counting fails
            base_tokens = 1000 if task_type == "research" else 300
            return {
                "input_tokens": base_tokens,
                "output_tokens": int(base_tokens * self.output_token_ratios[task_type]),
                "total_tokens": int(base_tokens * (1 + self.output_token_ratios[task_type]))
            }
    
    def estimate_profile_cost(self, profile: Dict, config: Dict) -> Dict:
        """Estimate the cost for processing a single profile."""
        costs = {
            "research": {"tokens": 0, "cost": 0.0, "requests": 0},
            "email": {"tokens": 0, "cost": 0.0, "requests": 0},
            "total": 0.0
        }
        
        # Only estimate costs for tasks that need to be done
        needs_research = not profile.get("research", "")
        needs_email = not profile.get("draft", "") or needs_research  # Email needs research first
        
        if needs_research:
            # Research cost estimation
            research_tokens = self.estimate_tokens(profile, "research")
            research_config = self.model_configs["perplexity/sonar"]
            
            input_cost = research_tokens["input_tokens"] * research_config["input_cost_per_token"]
            output_cost = min(research_tokens["output_tokens"], config["research_max_tokens"]) * research_config["output_cost_per_token"]
            request_cost = research_config["cost_per_request"]
            
            costs["research"] = {
                "tokens": research_tokens["total_tokens"],
                "cost": input_cost + output_cost + request_cost,
                "requests": 1,
                "input_tokens": research_tokens["input_tokens"],
                "output_tokens": min(research_tokens["output_tokens"], config["research_max_tokens"]),
                "breakdown": {
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "request_cost": request_cost
                }
            }
            costs["total"] += costs["research"]["cost"]
        
        if needs_email:
            # Email cost estimation
            email_tokens = self.estimate_tokens(profile, "email")
            email_config = self.model_configs["openai/gpt-4o-mini"]
            
            input_cost = email_tokens["input_tokens"] * email_config["input_cost_per_token"]
            output_cost = min(email_tokens["output_tokens"], config["email_max_tokens"]) * email_config["output_cost_per_token"]
            request_cost = email_config["cost_per_request"]
            
            costs["email"] = {
                "tokens": email_tokens["total_tokens"],
                "cost": input_cost + output_cost + request_cost,
                "requests": 1,
                "input_tokens": email_tokens["input_tokens"],
                "output_tokens": min(email_tokens["output_tokens"], config["email_max_tokens"]),
                "breakdown": {
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "request_cost": request_cost
                }
            }
            costs["total"] += costs["email"]["cost"]
        
        return costs
    
    def estimate_batch_cost(self, df: pd.DataFrame, config: Dict) -> Dict:
        """Estimate the total cost for processing a batch of profiles."""
        total_costs = {
            "research": {"tokens": 0, "cost": 0.0, "requests": 0, "profiles": 0},
            "email": {"tokens": 0, "cost": 0.0, "requests": 0, "profiles": 0},
            "total_cost": 0.0,
            "total_profiles": len(df),
            "breakdown": []
        }
        
        for _, row in df.iterrows():
            profile_costs = self.estimate_profile_cost(row.to_dict(), config)
            
            # Aggregate costs
            for task in ["research", "email"]:
                if profile_costs[task]["cost"] > 0:
                    total_costs[task]["tokens"] += profile_costs[task]["tokens"]
                    total_costs[task]["cost"] += profile_costs[task]["cost"]
                    total_costs[task]["requests"] += profile_costs[task]["requests"]
                    total_costs[task]["profiles"] += 1
            
            total_costs["total_cost"] += profile_costs["total"]
            
            # Store individual profile breakdown for detailed view
            total_costs["breakdown"].append({
                "profile": row.get("name", "Unknown"),
                "research_cost": profile_costs["research"]["cost"],
                "email_cost": profile_costs["email"]["cost"],
                "total_cost": profile_costs["total"]
            })
        
        return total_costs 