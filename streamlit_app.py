"""LinkedIn Research Pipeline - Streamlit App
===========================================
Interactive web interface for bulk profile research and personalized email generation.
"""

import streamlit as st
import concurrent.futures as cf
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)
import litellm
from litellm import completion, token_counter, cost_per_token
from prompts import get_email_prompt, get_research_prompt, get_default_email_prompt_template
import base64
import email.mime.text
import email.mime.multipart


class ConfigManager:
    """Manages application configuration and environment variables."""
    
    def __init__(self):
        load_dotenv()
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging for the application."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            handlers=[
                logging.FileHandler("pipeline.log"),
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.logger = logging.getLogger("pipeline")
    
    @property
    def scopes(self) -> List[str]:
        return [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/gmail.modify"
        ]
    
    @property
    def responses_dir(self) -> Path:
        resp_dir = Path("responses")
        resp_dir.mkdir(exist_ok=True)
        return resp_dir


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
    
    def __init__(self, config: ConfigManager):
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
            self.config.logger.warning(f"Token counting failed for {task_type}: {e}. Using fallback estimation.")
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


class GoogleSheetsService:
    """Handles all Google Sheets operations."""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self._service = None
        self._credentials = None
    
    def authenticate_user(self) -> bool:
        """Authenticate user with Google Sheets OAuth flow."""
        try:
            # Check if we have stored credentials in session state
            if 'google_credentials' in st.session_state and st.session_state.google_credentials:
                creds_data = st.session_state.google_credentials
                self._credentials = Credentials.from_authorized_user_info(creds_data, self.config.scopes)
                
                # Refresh if expired
                if self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    st.session_state.google_credentials = json.loads(self._credentials.to_json())
                
                self._service = build("sheets", "v4", credentials=self._credentials)
                return True
            
            # Try to load from file if available
            token_path = "token.json"
            if os.path.exists(token_path):
                self._credentials = Credentials.from_authorized_user_file(token_path, self.config.scopes)
                
                if self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    Path(token_path).write_text(self._credentials.to_json())
                
                # Store in session state
                st.session_state.google_credentials = json.loads(self._credentials.to_json())
                self._service = build("sheets", "v4", credentials=self._credentials)
                return True
                
            return False
            
        except Exception as e:
            st.error(f"Authentication error: {str(e)}")
            return False
    
    def start_oauth_flow(self):
        """Start the OAuth flow for new authentication."""
        try:
            creds_path = os.getenv("CREDENTIALS_PATH", "credentials.json")
            if not os.path.exists(creds_path):
                st.error("❌ Google credentials file not found. Please add 'credentials.json' to your project directory.")
                st.info("📋 To get credentials: Go to Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client ID")
                return False
            
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, self.config.scopes)
            self._credentials = flow.run_local_server(port=0)
            
            # Save credentials
            Path("token.json").write_text(self._credentials.to_json())
            st.session_state.google_credentials = json.loads(self._credentials.to_json())
            
            self._service = build("sheets", "v4", credentials=self._credentials)
            return True
            
        except Exception as e:
            st.error(f"OAuth flow error: {str(e)}")
            return False
    
    def get_service(self):
        """Get Google Sheets service."""
        if not self._service:
            if not self.authenticate_user():
                return None
        return self._service
    
    def list_spreadsheets(self) -> List[Dict]:
        """List available spreadsheets for the authenticated user."""
        service = self.get_service()
        if not service:
            return []
        
        try:
            # Use Drive API to list spreadsheets
            drive_service = build("drive", "v3", credentials=self._credentials)
            results = drive_service.files().list(
                q="mimeType='application/vnd.google-apps.spreadsheet'",
                pageSize=100,
                fields="files(id, name, modifiedTime)"
            ).execute()
            
            items = results.get('files', [])
            return [{'id': item['id'], 'name': item['name'], 'modified': item['modifiedTime']} for item in items]
            
        except Exception as e:
            st.error(f"Error listing spreadsheets: {str(e)}")
            return []
    
    def list_sheets_in_spreadsheet(self, spreadsheet_id: str) -> List[Dict]:
        """List sheets within a specific spreadsheet."""
        service = self.get_service()
        if not service:
            return []
        
        try:
            meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = []
            for sheet in meta.get("sheets", []):
                properties = sheet["properties"]
                sheets.append({
                    "id": properties["sheetId"],
                    "name": properties["title"],
                    "index": properties["index"]
                })
            return sheets
        except Exception as e:
            st.error(f"Error listing sheets: {str(e)}")
            return []
    
    def get_sheet_id_by_name(self, spreadsheet_id: str, sheet_name: str) -> Optional[int]:
        """Get sheet ID by name within a spreadsheet."""
        sheets = self.list_sheets_in_spreadsheet(spreadsheet_id)
        for sheet in sheets:
            if sheet["name"] == sheet_name:
                return sheet["id"]
        return None
    
    def fetch_profiles(self, spreadsheet_id: str, sheet_name: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch profiles from specified Google Sheet."""
        service = self.get_service()
        if not service:
            return pd.DataFrame()
        
        try:
            resp = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, 
                range=f"{sheet_name}!A1:Z"
            ).execute()
            
            rows = resp.get("values", [])
            if not rows:
                return pd.DataFrame()

            header = rows[0]
            header_len = len(header)
            fixed_rows = []
            
            for r in rows[1:]:
                if len(r) < header_len:
                    r = r + [""] * (header_len - len(r))
                elif len(r) > header_len:
                    r = r[:header_len]
                fixed_rows.append(r)

            df = pd.DataFrame(fixed_rows, columns=header)
            if limit:
                df = df.head(limit)

            # Ensure mandatory columns exist
            for col in ["research", "draft"]:
                if col not in df.columns:
                    df[col] = ""
            return df
        except Exception as e:
            st.error(f"Error fetching profiles: {str(e)}")
            return pd.DataFrame()
    
    def batch_update_cells(self, spreadsheet_id: str, requests: List[Dict]):
        """Update Google Sheets with batch requests."""
        if requests:
            service = self.get_service()
            if service:
                try:
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=spreadsheet_id, 
                        body={"requests": requests}
                    ).execute()
                except Exception as e:
                    st.error(f"Error updating sheets: {str(e)}")


class GmailService:
    """Handles all Gmail operations for creating email drafts."""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self._service = None
        self._credentials = None
    
    def authenticate_user(self) -> bool:
        """Authenticate user with Gmail using existing Google credentials."""
        try:
            # Check if we have stored credentials in session state
            if 'google_credentials' in st.session_state and st.session_state.google_credentials:
                creds_data = st.session_state.google_credentials
                self._credentials = Credentials.from_authorized_user_info(creds_data, self.config.scopes)
                
                # Refresh if expired
                if self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    st.session_state.google_credentials = json.loads(self._credentials.to_json())
                
                # Check if Gmail scope is actually included
                if 'https://www.googleapis.com/auth/gmail.modify' not in self._credentials.scopes:
                    self.config.logger.warning("Gmail scope not found in stored credentials")
                    return False
                
                self._service = build("gmail", "v1", credentials=self._credentials)
                return True
            
            # Try to load from file if available
            token_path = "token.json"
            if os.path.exists(token_path):
                self._credentials = Credentials.from_authorized_user_file(token_path, self.config.scopes)
                
                if self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    Path(token_path).write_text(self._credentials.to_json())
                
                # Check if Gmail scope is actually included
                if 'https://www.googleapis.com/auth/gmail.modify' not in self._credentials.scopes:
                    self.config.logger.warning("Gmail scope not found in token file")
                    return False
                
                # Store in session state
                st.session_state.google_credentials = json.loads(self._credentials.to_json())
                self._service = build("gmail", "v1", credentials=self._credentials)
                return True
                
            return False
            
        except Exception as e:
            self.config.logger.error(f"Gmail authentication error: {str(e)}")
            return False
    
    def get_service(self):
        """Get Gmail service."""
        if not self._service:
            if not self.authenticate_user():
                return None
        return self._service
    
    def create_draft(self, profile: Dict, email_content: str, subject_prefix: str = "") -> Optional[str]:
        """Create a Gmail draft for the given profile and email content."""
        service = self.get_service()
        if not service:
            return None
        
        try:
            # Extract recipient email from profile data
            recipient_email = None
            # Try common email field names (case-insensitive)
            email_fields = ['email', 'Email', 'email_address', 'Email_Address', 'contact_email', 'work_email']
            for field in email_fields:
                if field in profile and profile[field] and str(profile[field]).strip():
                    recipient_email = str(profile[field]).strip()
                    break
            
            # If no email found, log warning but still create draft
            if not recipient_email:
                self.config.logger.warning(f"No email found for {profile.get('name', 'unknown')}. Draft will be created without recipient.")
            
            # Extract email subject from the email content if available
            lines = email_content.strip().split('\n')
            subject_line = None
            body_lines = []
            in_body = False
            
            for line in lines:
                if line.lower().startswith('subject:'):
                    subject_line = line[8:].strip()
                elif line.lower().startswith('dear ') or line.lower().startswith('hi ') or in_body:
                    in_body = True
                    body_lines.append(line)
                elif not line.strip() and not in_body:
                    continue
                elif in_body:
                    body_lines.append(line)
            
            # Fallback subject if not found in content
            if not subject_line:
                subject_line = f"Partnership Opportunity - {profile.get('company', 'Your Company')}"
            
            # Add prefix if provided
            if subject_prefix:
                subject_line = f"{subject_prefix}{subject_line}"
            
            # Join body content
            body = '\n'.join(body_lines) if body_lines else email_content
            
            # Create the email message
            message = email.mime.text.MIMEText(body)
            message['Subject'] = subject_line
            
            # Set recipient if email was found
            if recipient_email:
                message['To'] = recipient_email
            
            # Note: Gmail will automatically set the 'From' field when creating drafts
            
            # Create the draft
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            draft_body = {'message': {'raw': raw_message}}
            
            draft = service.users().drafts().create(userId='me', body=draft_body).execute()
            return draft.get('id')
            
        except Exception as e:
            self.config.logger.error(f"Error creating Gmail draft for {profile.get('name', 'unknown')}: {e}")
            return None
    
    def list_recent_drafts(self, max_results: int = 10) -> List[Dict]:
        """List recent drafts."""
        service = self.get_service()
        if not service:
            return []
        
        try:
            results = service.users().drafts().list(userId='me', maxResults=max_results).execute()
            drafts = results.get('drafts', [])
            
            # Get details for each draft
            detailed_drafts = []
            for draft in drafts[:5]:  # Limit to 5 for performance
                try:
                    draft_detail = service.users().drafts().get(userId='me', id=draft['id']).execute()
                    message = draft_detail.get('message', {})
                    headers = message.get('payload', {}).get('headers', [])
                    
                    subject = "No Subject"
                    for header in headers:
                        if header['name'] == 'Subject':
                            subject = header['value']
                            break
                    
                    detailed_drafts.append({
                        'id': draft['id'],
                        'subject': subject,
                        'snippet': message.get('snippet', '')[:100] + "..." if len(message.get('snippet', '')) > 100 else message.get('snippet', ''),
                        'created': draft_detail.get('message', {}).get('internalDate', '')
                    })
                except Exception as e:
                    self.config.logger.error(f"Error getting draft details: {e}")
                    continue
            
            return detailed_drafts
            
        except Exception as e:
            self.config.logger.error(f"Error listing drafts: {e}")
            return []


class AIService:
    """Handles AI API calls for research and email generation."""
    
    def __init__(self, config: ConfigManager):
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


class ProfileProcessor:
    """Handles the main profile processing logic."""
    
    def __init__(self, sheets_service: GoogleSheetsService, ai_service: AIService, cost_tracker: CostTracker):
        self.sheets_service = sheets_service
        self.ai_service = ai_service
        self.cost_tracker = cost_tracker
    
    def process_profiles(self, df: pd.DataFrame, config: Dict, 
                        progress_bar, status_text, results_container) -> pd.DataFrame:
        """Process profiles with real-time updates."""
        sheet_id = self.sheets_service.get_sheet_id_by_name(config['spreadsheet_id'], config['sheet_name'])
        research_col = df.columns.get_loc("research")
        draft_col = df.columns.get_loc("draft")
        update_requests = []
        
        total_profiles = len(df)
        processed = 0
        failed_tasks = 0
        
        with cf.ThreadPoolExecutor(max_workers=config['max_workers']) as executor:
            future_to_profile = {}
            
            # Submit research tasks for rows without research
            for idx, row in df.iterrows():
                if not row["research"]:
                    future = executor.submit(
                        self.ai_service.research_call, 
                        row.to_dict(), 
                        config['perplexity_api_key'],
                        config['research_max_tokens'],
                        config['timeout_seconds']
                    )
                    future_to_profile[future] = (idx, "research", row)
            
            # Submit email tasks for rows that already have research but no draft
            for idx, row in df.iterrows():
                if row["research"] and not row["draft"]:
                    future = executor.submit(
                        self.ai_service.email_call,
                        row.to_dict(),
                        config['openai_api_key'],
                        config['email_max_tokens'],
                        config['timeout_seconds']
                    )
                    future_to_profile[future] = (idx, "draft", row)
            
            # Process completed tasks with improved error handling
            while future_to_profile:
                try:
                    # Use a longer timeout to avoid frequent timeouts
                    done_futures = list(cf.as_completed(future_to_profile, timeout=5))
                    
                    for future in done_futures:
                        if future in future_to_profile:
                            idx, task_type, row = future_to_profile.pop(future)
                            try:
                                result = future.result()
                                df.at[idx, task_type] = result
                                
                                # Track newly processed items
                                st.session_state.newly_processed.add((idx, task_type))
                                
                                # Store session results
                                profile_name = row.get('name', f'Row {idx}')
                                result_entry = {
                                    'name': profile_name,
                                    'task': task_type,
                                    'content': result[:200] + "..." if len(result) > 200 else result,
                                    'timestamp': datetime.utcnow().strftime("%H:%M:%S")
                                }
                                st.session_state.session_results.append(result_entry)
                                
                                # Update Google Sheets
                                col_idx = research_col if task_type == "research" else draft_col
                                update_requests.append({
                                    "updateCells": {
                                        "range": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": idx + 1,
                                            "endRowIndex": idx + 2,
                                            "startColumnIndex": col_idx,
                                            "endColumnIndex": col_idx + 1,
                                        },
                                        "rows": [{"values": [{"userEnteredValue": {"stringValue": result}}]}],
                                        "fields": "userEnteredValue",
                                    }
                                })
                                
                                # Submit email task if research completed and no draft exists
                                if task_type == "research" and not df.at[idx, "draft"]:
                                    email_future = executor.submit(
                                        self.ai_service.email_call,
                                        df.loc[idx].to_dict(),
                                        config['openai_api_key'],
                                        config['email_max_tokens'],
                                        config['timeout_seconds']
                                    )
                                    future_to_profile[email_future] = (idx, "draft", df.loc[idx])
                                
                                processed += 1
                                progress = processed / (total_profiles * 2)  # research + email
                                progress_bar.progress(min(progress, 1.0))
                                status_text.text(f"Processed {processed} tasks... ({failed_tasks} failed)")
                                
                                # Update results display
                                self._update_results_display(df, results_container)
                                
                            except Exception as e:
                                failed_tasks += 1
                                error_msg = f"Error processing {row.get('name', 'unknown')}: {str(e)}"
                                st.error(error_msg)
                                self.ai_service.config.logger.error(error_msg)
                                
                                # Still count as processed for progress
                                processed += 1
                                progress = processed / (total_profiles * 2)
                                progress_bar.progress(min(progress, 1.0))
                                status_text.text(f"Processed {processed} tasks... ({failed_tasks} failed)")
                
                except cf.TimeoutError:
                    # Handle timeout gracefully - continue waiting for remaining futures
                    if future_to_profile:
                        status_text.text(f"Waiting for {len(future_to_profile)} remaining tasks... ({processed} completed, {failed_tasks} failed)")
                        continue
                    else:
                        break
                        
                except Exception as e:
                    # Handle any other unexpected errors
                    st.error(f"Unexpected error in processing loop: {str(e)}")
                    self.ai_service.config.logger.error(f"Processing loop error: {e}")
                    break
        
        # Final batch update
        if update_requests:
            try:
                self.sheets_service.batch_update_cells(config['spreadsheet_id'], update_requests)
            except Exception as e:
                st.error(f"Error updating Google Sheets: {str(e)}")
                self.ai_service.config.logger.error(f"Sheets update error: {e}")
        
        # Final status update
        if failed_tasks > 0:
            st.warning(f"⚠️ Processing completed with {failed_tasks} failed tasks out of {processed} total")
        
        return df
    
    def _update_results_display(self, df: pd.DataFrame, results_container):
        """Update the live results display."""
        # Clear the container and redraw all content
        results_container.empty()
        
        # Show session results table directly in the cleared container
        if st.session_state.session_results:
            with results_container:
                st.subheader("✨ New Results This Session")
                results_table_df = pd.DataFrame(st.session_state.session_results)
                
                # Style the results table
                st.dataframe(
                    results_table_df,
                    column_config={
                        "name": "Profile",
                        "task": "Task",
                        "content": st.column_config.TextColumn("Content Preview", width="large"),
                        "timestamp": "Time"
                    },
                    use_container_width=True,
                    hide_index=True
                )

    def regenerate_email(self, profile_data: Dict, idx: int, config: Dict) -> str:
        """Regenerate email for a specific profile."""
        try:
            # Call the AI service to regenerate the email
            new_email = self.ai_service.email_call(
                profile_data,
                config['openai_api_key'],
                config['email_max_tokens'],
                config['timeout_seconds']
            )
            
            # Update the local dataframe if it exists in session state
            if 'profiles_df' in st.session_state:
                st.session_state.profiles_df.at[idx, 'draft'] = new_email
            
            # Update Google Sheets
            sheet_id = self.sheets_service.get_sheet_id_by_name(config['spreadsheet_id'], config['sheet_name'])
            draft_col = st.session_state.profiles_df.columns.get_loc("draft")
            
            update_request = {
                "updateCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": idx + 1,
                        "endRowIndex": idx + 2,
                        "startColumnIndex": draft_col,
                        "endColumnIndex": draft_col + 1,
                    },
                    "rows": [{"values": [{"userEnteredValue": {"stringValue": new_email}}]}],
                    "fields": "userEnteredValue",
                }
            }
            
            self.sheets_service.batch_update_cells(config['spreadsheet_id'], [update_request])
            
            return new_email
            
        except Exception as e:
            self.ai_service.config.logger.error(f"Error regenerating email for profile at index {idx}: {e}")
            raise e


class StreamlitApp:
    """Main Streamlit application class."""
    
    def __init__(self):
        self.config = ConfigManager()
        self.cost_tracker = CostTracker()
        self.cost_estimator = CostEstimator(self.config)
        self.sheets_service = GoogleSheetsService(self.config)
        self.gmail_service = GmailService(self.config)
        self.ai_service = AIService(self.config)
        self.processor = ProfileProcessor(self.sheets_service, self.ai_service, self.cost_tracker)
        
        # Set up litellm callback
        litellm.success_callback = [self.cost_tracker.track_cost]
        
        # Initialize session state
        self._init_session_state()
        
        # Configure page
        st.set_page_config(
            page_title="LinkedIn Research Pipeline",
            page_icon="🔍",
            layout="wide",
            initial_sidebar_state="expanded"
        )
    
    def _init_session_state(self):
        """Initialize Streamlit session state variables."""
        if 'processing' not in st.session_state:
            st.session_state.processing = False
        if 'results' not in st.session_state:
            st.session_state.results = []
        if 'cost_tracking' not in st.session_state:
            st.session_state.cost_tracking = self.cost_tracker.cost_data
        if 'total_cost' not in st.session_state:
            st.session_state.total_cost = self.cost_tracker.total_cost
        if 'google_credentials' not in st.session_state:
            st.session_state.google_credentials = None
        if 'authenticated' not in st.session_state:
            st.session_state.authenticated = False
        if 'spreadsheets' not in st.session_state:
            st.session_state.spreadsheets = None
        if 'selected_spreadsheet' not in st.session_state:
            st.session_state.selected_spreadsheet = None
        if 'selected_sheet' not in st.session_state:
            st.session_state.selected_sheet = None
        if 'current_sheet_key' not in st.session_state:
            st.session_state.current_sheet_key = None
        if 'newly_processed' not in st.session_state:
            st.session_state.newly_processed = set()  # Track newly processed items
        if 'session_results' not in st.session_state:
            st.session_state.session_results = []  # Track results from current session
        if 'gmail_authenticated' not in st.session_state:
            st.session_state.gmail_authenticated = False
        if 'processing_complete' not in st.session_state:
            st.session_state.processing_complete = False
        if 'gmail_drafts_created' not in st.session_state:
            st.session_state.gmail_drafts_created = []
        if 'custom_email_prompt' not in st.session_state:
            st.session_state.custom_email_prompt = None
        if 'use_custom_prompt' not in st.session_state:
            st.session_state.use_custom_prompt = False
    
    def render_authentication_section(self):
        """Render authentication section."""
        st.subheader("🔐 Google Authentication")
        
        if st.session_state.authenticated:
            # Check both Sheets and Gmail authentication status
            sheets_status = self.sheets_service.authenticate_user()
            gmail_status = self.gmail_service.authenticate_user()
            
            # Both services must be authenticated
            if not sheets_status or not gmail_status:
                # Force re-authentication if either service fails
                st.session_state.authenticated = False
                st.session_state.gmail_authenticated = False
                st.error("❌ **Authentication Incomplete:** Missing required permissions")
                st.warning("🔄 You need permissions for both Google Sheets and Gmail to use this app")
                
                with st.expander("🔍 Why do I need both services?", expanded=True):
                    st.write("**This app requires access to:**")
                    st.write("✅ **Google Sheets** - To read profile data and save research results")
                    st.write("✅ **Gmail** - To create email drafts for outreach")
                    st.write("")
                    st.write("**If you previously authenticated without Gmail permissions,**")
                    st.write("you'll need to re-authenticate to grant access to both services.")
                
                if st.button("🔑 Re-authenticate with Full Permissions", type="primary"):
                    self._force_complete_reauthentication()
                
                return False
            
            # Both services authenticated successfully
            st.session_state.gmail_authenticated = gmail_status
            
            col1, col2 = st.columns(2)
            with col1:
                st.success("✅ Google Sheets: Authenticated")
            with col2:
                st.success("✅ Gmail: Authenticated")
            
            st.success("🎉 **Ready to use!** Both Google Sheets and Gmail are connected")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🔄 Refresh Authentication"):
                    st.session_state.authenticated = False
                    st.session_state.gmail_authenticated = False
                    st.session_state.spreadsheets = None
                    st.session_state.selected_spreadsheet = None
                    st.session_state.selected_sheet = None
                    if 'google_credentials' in st.session_state:
                        del st.session_state.google_credentials
                    st.rerun()
            return True
        else:
            # Check if we can authenticate automatically with BOTH services
            sheets_auth = self.sheets_service.authenticate_user()
            gmail_auth = self.gmail_service.authenticate_user() if sheets_auth else False
            
            if sheets_auth and gmail_auth:
                st.session_state.authenticated = True
                st.session_state.gmail_authenticated = True
                st.rerun()
                return True
            else:
                st.warning("⚠️ Please authenticate with Google to continue")
                st.info("📋 **Required Permissions:** Google Sheets (read/write) + Gmail (create drafts)")
                
                with st.expander("🛠️ Setup Instructions", expanded=True):
                    st.write("**Before authenticating, ensure you have:**")
                    st.write("1. **Enabled APIs:** Both Google Sheets API and Gmail API in your Google Cloud Console")
                    st.write("2. **OAuth Consent Screen:** Configured with both Sheets and Gmail scopes")
                    st.write("3. **Credentials:** Downloaded OAuth 2.0 credentials as `credentials.json`")
                    st.write("")
                    st.write("**Required OAuth Scopes:**")
                    st.code("https://www.googleapis.com/auth/spreadsheets")
                    st.code("https://www.googleapis.com/auth/drive.readonly") 
                    st.code("https://www.googleapis.com/auth/gmail.modify")
                    st.write("")
                    st.write("**Quick links:**")
                    st.write("• [Enable Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)")
                    st.write("• [Enable Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)")
                    st.write("• [OAuth Consent Screen](https://console.cloud.google.com/apis/credentials/consent)")
                
                if st.button("🔑 Start Authentication", type="primary"):
                    if self._authenticate_both_services():
                        st.session_state.authenticated = True
                        st.session_state.gmail_authenticated = True
                        st.success("✅ Authentication successful for both services!")
                        st.rerun()
                    else:
                        st.error("❌ Authentication failed. Please check your setup and try again.")
                return False
    
    def render_cost_estimation(self, df: pd.DataFrame, config: Dict):
        """Render cost estimation section."""
        if df.empty:
            return
            
        st.subheader("💰 Cost Estimation")
        
        with st.spinner("Calculating cost estimate..."):
            try:
                cost_estimate = self.cost_estimator.estimate_batch_cost(df, config)
                
                # Summary metrics
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        label="Total Estimated Cost",
                        value=f"${cost_estimate['total_cost']:.4f}"
                    )
                with col2:
                    st.metric(
                        label="Profiles to Process",
                        value=f"{cost_estimate['total_profiles']}"
                    )
                
                # Detailed breakdown
                with st.expander("📊 Detailed Cost Breakdown", expanded=False):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("Research (Perplexity)")
                        research_data = cost_estimate['research']
                        if research_data['profiles'] > 0:
                            st.write(f"• **Profiles needing research:** {research_data['profiles']}")
                            st.write(f"• **Total requests:** {research_data['requests']}")
                            st.write(f"• **Estimated tokens:** {research_data['tokens']:,}")
                            st.write(f"• **Total cost:** ${research_data['cost']:.4f}")
                        else:
                            st.write("No research needed - all profiles already have research data")
                    
                    with col2:
                        st.subheader("Email Generation (OpenAI)")
                        email_data = cost_estimate['email']
                        if email_data['profiles'] > 0:
                            st.write(f"• **Profiles needing emails:** {email_data['profiles']}")
                            st.write(f"• **Total requests:** {email_data['requests']}")
                            st.write(f"• **Estimated tokens:** {email_data['tokens']:,}")
                            st.write(f"• **Total cost:** ${email_data['cost']:.4f}")
                        else:
                            st.write("No email generation needed - all profiles already have drafts")
                    
                    # Show per-profile breakdown
                    if len(cost_estimate['breakdown']) > 0:
                        st.subheader("Per-Profile Cost Breakdown")
                        breakdown_df = pd.DataFrame(cost_estimate['breakdown'])
                        # Format cost columns as currency
                        for col in ['research_cost', 'email_cost', 'total_cost']:
                            breakdown_df[col] = breakdown_df[col].apply(lambda x: f"${x:.4f}")
                        
                        st.dataframe(
                            breakdown_df,
                            column_config={
                                "profile": "Profile Name",
                                "research_cost": "Research Cost",
                                "email_cost": "Email Cost", 
                                "total_cost": "Total Cost"
                            },
                            use_container_width=True
                        )
                
                # Cost breakdown alert
                if cost_estimate['total_cost'] > 1.0:
                    st.warning(f"⚠️ **High Cost Alert:** This processing will cost approximately ${cost_estimate['total_cost']:.2f}")
                elif cost_estimate['total_cost'] > 0.1:
                    st.info(f"💡 **Cost Notice:** This processing will cost approximately ${cost_estimate['total_cost']:.2f}")
                else:
                    st.success(f"✅ **Low Cost:** This processing will cost approximately ${cost_estimate['total_cost']:.4f}")
                
            except Exception as e:
                st.error(f"Failed to calculate cost estimate: {str(e)}")
                self.config.logger.error(f"Cost estimation failed: {e}")
                
                # Show simplified fallback estimate
                estimated_profiles = len(df)
                fallback_cost = estimated_profiles * 0.01  # Simple fallback: $0.01 per profile
                st.warning(f"Using fallback estimate: ~${fallback_cost:.2f} for {estimated_profiles} profiles")
    
    def render_sheet_selection(self):
        """Render spreadsheet and sheet selection interface."""
        if not st.session_state.authenticated:
            return None
        
        st.subheader("📋 Select Spreadsheet & Sheet")
        
        # Get list of spreadsheets
        if st.button("🔄 Refresh Spreadsheets"):
            st.session_state.spreadsheets = None
            # Clear selections since they might not be valid after refresh
            st.session_state.selected_spreadsheet = None
            st.session_state.selected_sheet = None
            st.session_state.current_sheet_key = None
            st.rerun()
        
        # Load spreadsheets if not already loaded or if explicitly refreshed
        if 'spreadsheets' not in st.session_state or st.session_state.spreadsheets is None:
            with st.spinner("Loading your spreadsheets..."):
                st.session_state.spreadsheets = self.sheets_service.list_spreadsheets()
        
        if not st.session_state.spreadsheets:
            st.error("No spreadsheets found or error loading spreadsheets")
            return None
        
        # Spreadsheet selection
        spreadsheet_options = {f"{ss['name']} (Modified: {ss['modified'][:10]})": ss for ss in st.session_state.spreadsheets}
        selected_spreadsheet_display = st.selectbox(
            "Choose a spreadsheet:",
            options=list(spreadsheet_options.keys()),
            key="spreadsheet_selector"
        )
        
        if selected_spreadsheet_display:
            selected_spreadsheet = spreadsheet_options[selected_spreadsheet_display]
            st.session_state.selected_spreadsheet = selected_spreadsheet
            
            # Sheet selection within the spreadsheet
            with st.spinner("Loading sheets..."):
                sheets = self.sheets_service.list_sheets_in_spreadsheet(selected_spreadsheet['id'])
            
            if sheets:
                sheet_names = [sheet['name'] for sheet in sheets]
                selected_sheet_name = st.selectbox(
                    "Choose a sheet:",
                    options=sheet_names,
                    key="sheet_selector"
                )
                
                if selected_sheet_name:
                    st.session_state.selected_sheet = selected_sheet_name
                    
                    return {
                        'spreadsheet_id': selected_spreadsheet['id'],
                        'spreadsheet_name': selected_spreadsheet['name'],
                        'sheet_name': selected_sheet_name
                    }
            else:
                st.error("No sheets found in the selected spreadsheet")
        
        return None
    
    def render_sidebar(self) -> Dict:
        """Render sidebar configuration and return config dictionary."""
        st.sidebar.header("⚙️ Configuration")
        
        # API Keys
        perplexity_api_key = st.sidebar.text_input(
            "Perplexity API Key", 
            value=os.getenv("PERPLEXITY_API_KEY", ""), 
            type="password",
            key="perplexity_api_key_input"
        )
        openai_api_key = st.sidebar.text_input(
            "OpenAI API Key", 
            value=os.getenv("OPENAI_API_KEY", ""), 
            type="password",
            key="openai_api_key_input"
        )
        
        # Processing parameters (hidden by default)
        with st.sidebar.expander("🔧 Advanced Settings", expanded=False):
            max_workers = st.slider("Max Workers", 1, 50, 25)
            research_max_tokens = st.slider("Research Max Tokens", 100, 2000, 800)
            email_max_tokens = st.slider("Email Max Tokens", 100, 1000, 350)
            timeout_seconds = st.slider("Timeout (seconds)", 10, 120, 40)
            profile_limit = st.number_input("Profile Limit (0 = all)", 0, 1000, 0)
        
        # Custom Email Prompt section
        with st.sidebar.expander("✉️ Custom Email Prompt", expanded=False):
            st.write("**Customize your email generation prompt**")
            
            # Toggle for using custom prompt
            use_custom = st.checkbox(
                "Use Custom Email Prompt", 
                value=st.session_state.use_custom_prompt,
                help="Enable to use your custom prompt instead of the default"
            )
            st.session_state.use_custom_prompt = use_custom
            
            # Show default prompt button
            if st.button("📋 View Default Prompt", help="See the current default email prompt"):
                default_template = get_default_email_prompt_template()
                st.text_area(
                    "Default Prompt Template",
                    value=default_template,
                    height=200,
                    disabled=True,
                    key="default_prompt_display"
                )
            
            if use_custom:
                # Custom prompt editor
                current_custom_prompt = st.session_state.custom_email_prompt or get_default_email_prompt_template()
                
                custom_prompt = st.text_area(
                    "Custom Email Prompt",
                    value=current_custom_prompt,
                    height=300,
                    help="Use placeholders like {name}, {company}, {role}, {research}, etc.",
                    key="custom_prompt_editor"
                )
                
                # Save the custom prompt
                st.session_state.custom_email_prompt = custom_prompt
                
                # Show available placeholders directly (no nested expander)
                st.write("**🔖 Available Placeholders:**")
                placeholders = [
                    "{name} - Contact's name",
                    "{role} - Contact's job title", 
                    "{company} - Company name",
                    "{location_context} - Location info (e.g., ' in New York')",
                    "{contact_info} - Phone and email info",
                    "{education_section} - Education details",
                    "{topic} - Topic field from spreadsheet",
                    "{subtopic} - Subtopic field from spreadsheet", 
                    "{research} - AI-generated research insights",
                    "{additional_info_section} - Any additional fields from spreadsheet"
                ]
                for placeholder in placeholders:
                    st.write(f"• `{placeholder}`")
                
                # Validation
                try:
                    # Test if the prompt has all required placeholders
                    test_profile = {
                        'name': 'Test',
                        'role': 'Test Role',
                        'company': 'Test Company',
                        'research': 'Test research'
                    }
                    get_email_prompt(test_profile, custom_prompt)
                    st.success("✅ Custom prompt is valid!")
                except Exception as e:
                    st.error(f"❌ Prompt validation error: {str(e)}")
                    st.info("💡 Make sure all required placeholders are included")
            else:
                st.info("Using default email prompt. Enable custom prompt above to customize.")
                
            # Reset button
            if st.button("🔄 Reset to Default", help="Reset custom prompt to default template"):
                st.session_state.custom_email_prompt = get_default_email_prompt_template()
                st.session_state.use_custom_prompt = False
                st.success("Reset to default prompt!")
                st.rerun()
        
        # Cost tracking section - integrated into configuration
        with st.sidebar.expander("💰 Cost Tracking", expanded=True):
            # Sync with cost tracker
            st.session_state.cost_tracking = self.cost_tracker.cost_data
            st.session_state.total_cost = self.cost_tracker.total_cost
            
            # Cost metrics
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Total Cost", f"${st.session_state.total_cost:.3f}")
            with col_b:
                total_calls = (st.session_state.cost_tracking['perplexity']['calls'] + 
                              st.session_state.cost_tracking['openai']['calls'])
                st.metric("Total Calls", total_calls)
            
            # Provider breakdown
            st.write("**Provider Details:**")
            for provider, data in st.session_state.cost_tracking.items():
                st.write(f"**{provider.title()}:** {data['calls']} calls, {data['tokens']:,} tokens, ${data['cost']:.3f}")
        
        config = {
            'perplexity_api_key': perplexity_api_key,
            'openai_api_key': openai_api_key,
            'max_workers': max_workers,
            'research_max_tokens': research_max_tokens,
            'email_max_tokens': email_max_tokens,
            'timeout_seconds': timeout_seconds,
            'profile_limit': profile_limit if profile_limit > 0 else None
        }
        
        # Add sheet selection to config if available
        if st.session_state.selected_spreadsheet and st.session_state.selected_sheet:
            config.update({
                'spreadsheet_id': st.session_state.selected_spreadsheet['id'],
                'sheet_name': st.session_state.selected_sheet
            })
        
        return config
    
    def render_profile_section(self, config: Dict):
        """Render profile data section."""
        st.subheader("📋 Profile Data")
        
        # Check if sheet is selected
        if 'spreadsheet_id' not in config or 'sheet_name' not in config:
            st.warning("⚠️ Please select a spreadsheet and sheet first")
            return
        
        # Add button to open spreadsheet in Google Sheets
        sheet_id = self.sheets_service.get_sheet_id_by_name(config['spreadsheet_id'], config['sheet_name'])
        if sheet_id is not None:
            spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{config['spreadsheet_id']}/edit#gid={sheet_id}"
        else:
            spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{config['spreadsheet_id']}/edit"
        
        col1, col2 = st.columns([1, 3])
        with col1:
            st.link_button(
                "📊 Open in Google Sheets",
                spreadsheet_url,
                help="Open the selected spreadsheet in Google Sheets (new tab)"
            )
        with col2:
            st.info(f"📄 **Sheet:** {config['sheet_name']}")
        
        # Automatically load profiles when sheet is selected
        current_sheet_key = f"{config['spreadsheet_id']}_{config['sheet_name']}"
        
        # Load profiles if not already loaded for this sheet
        if ('current_sheet_key' not in st.session_state or 
            st.session_state.current_sheet_key != current_sheet_key or
            'profiles_df' not in st.session_state):
            
            try:
                with st.spinner("Loading profiles from Google Sheets..."):
                    df = self.sheets_service.fetch_profiles(
                        config['spreadsheet_id'], 
                        config['sheet_name'], 
                        config['profile_limit']
                    )
                    st.session_state.profiles_df = df
                    st.session_state.current_sheet_key = current_sheet_key
            except Exception as e:
                st.error(f"Error loading profiles: {str(e)}")
                self.config.logger.error(f"Error loading profiles: {e}")
                return
        
        # Display profiles if loaded
        if 'profiles_df' in st.session_state and not st.session_state.profiles_df.empty:
            df = st.session_state.profiles_df
            
            # Validate required columns
            is_valid, missing_columns = self.validate_required_columns(df)
            
            # Show column validation status
            if not is_valid:
                st.error(f"❌ Missing required columns: {', '.join(missing_columns)}")
                st.info("**Required columns:** name, company, role")
                st.info("**Optional columns:** topic, subtopic, and any other fields will be automatically included in the prompts for additional context")
                st.info("**For Gmail drafts:** Add an email column (e.g., 'email', 'Email', 'email_address') to include recipients in drafts")
                st.info("💡 Please add the required columns to your spreadsheet before processing.")
            else:
                st.success("✅ All required columns found!")
                # Check for email column for Gmail functionality
                email_fields = ['email', 'Email', 'email_address', 'Email_Address', 'contact_email', 'work_email']
                has_email_column = any(field in df.columns for field in email_fields)
                if has_email_column:
                    st.success("✅ Email column detected - Gmail drafts will include recipients!")
                else:
                    st.info("💡 **Tip:** Add an email column to automatically include recipients in Gmail drafts")
            
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Start processing button - make it more prominent
            st.markdown("---")
            
            # Check for API keys and required columns
            if not config['perplexity_api_key'] or not config['openai_api_key']:
                st.error("⚠️ Please provide both API keys in the sidebar to start processing")
            elif not is_valid:
                st.error("⚠️ Cannot start processing - missing required columns (see above)")
            else:
                # Show cost estimation before processing
                self.render_cost_estimation(df, config)
                st.markdown("---")
                
                if st.button("🚀 Start Processing", type="primary", disabled=st.session_state.processing, use_container_width=True):
                    # Clear previous session results
                    st.session_state.newly_processed = set()
                    st.session_state.session_results = []
                    st.session_state.processing = True
                    st.rerun()
        else:
            st.info("No profiles found in the selected sheet")
    
    def render_processing_section(self, config: Dict):
        """Render processing section."""
        if st.session_state.processing and 'profiles_df' in st.session_state:
            st.subheader("⚡ Processing")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_container = st.container()
            
            try:
                start_time = time.time()
                processed_df = self.processor.process_profiles(
                    st.session_state.profiles_df.copy(), 
                    config, 
                    progress_bar, 
                    status_text,
                    results_container
                )
                
                elapsed = time.time() - start_time
                st.session_state.processing = False
                
                # Save summary
                self.cost_tracker.save_summary({
                    "elapsed_sec": elapsed,
                    "profiles_processed": len(processed_df),
                })
                
                # Mark processing as complete for Gmail integration
                st.session_state.processing_complete = True
                
                st.success(f"✅ Processing complete! {len(processed_df)} profiles processed in {elapsed:.1f}s")
                st.balloons()
                
            except Exception as e:
                st.session_state.processing = False
                error_msg = str(e)
                
                # Provide more specific error guidance
                if "unfinished" in error_msg.lower():
                    st.error("❌ **Processing Error:** Some tasks did not complete successfully.")
                    st.info("💡 **Common causes:**")
                    st.info("• **API timeouts** - Try reducing max workers or increasing timeout")
                    st.info("• **API key issues** - Verify your API keys are correct")
                    st.info("• **Network connectivity** - Check your internet connection")
                    st.info("• **Rate limiting** - Reduce concurrent requests (max workers)")
                elif "timeout" in error_msg.lower():
                    st.error("❌ **Timeout Error:** API calls took too long to complete.")
                    st.info("💡 **Solutions:**")
                    st.info("• Increase timeout in Advanced Settings")
                    st.info("• Reduce max workers to make fewer concurrent requests")
                    st.info("• Check your internet connection")
                elif "api" in error_msg.lower() or "key" in error_msg.lower():
                    st.error("❌ **API Error:** Problem with API authentication or quota.")
                    st.info("💡 **Check:**")
                    st.info("• API keys are correct and valid")
                    st.info("• You have sufficient API credits/quota")
                    st.info("• APIs are not experiencing outages")
                else:
                    st.error(f"❌ **Processing failed:** {error_msg}")
                    st.info("💡 **Try:**")
                    st.info("• Check the logs in pipeline.log for more details")
                    st.info("• Reduce the number of profiles or max workers")
                    st.info("• Ensure your spreadsheet data is valid")
                
                # Show additional troubleshooting info
                with st.expander("🔧 Troubleshooting Details", expanded=False):
                    st.write("**Error details:**")
                    st.code(error_msg)
                    st.write("**Current configuration:**")
                    config_summary = {
                        "max_workers": config.get('max_workers', 'N/A'),
                        "timeout_seconds": config.get('timeout_seconds', 'N/A'),
                        "research_max_tokens": config.get('research_max_tokens', 'N/A'),
                        "email_max_tokens": config.get('email_max_tokens', 'N/A'),
                        "profiles_count": len(st.session_state.profiles_df) if 'profiles_df' in st.session_state else 0
                    }
                    st.json(config_summary)
                
                self.config.logger.error(f"Processing failed: {e}")
        
        # Stop button
        if st.session_state.processing:
            if st.button("⏹️ Stop Processing"):
                st.session_state.processing = False
                st.warning("Processing stopped by user")
                st.rerun()
    
    def render_gmail_drafts_section(self):
        """Render Gmail drafts creation section."""
        st.subheader("📧 Gmail Integration")
        
        # Since authentication is now unified, we can trust st.session_state.authenticated
        if not st.session_state.authenticated:
            st.error("⚠️ Please complete authentication in the Research & Processing tab first")
            return
        
        # Get profiles with completed emails
        if 'profiles_df' not in st.session_state:
            st.warning("⚠️ No profile data loaded. Please load data from the Research & Processing tab first.")
            return
        
        df = st.session_state.profiles_df
        completed_profiles = df[df['draft'].notna() & (df['draft'] != '')].copy()
        
        if completed_profiles.empty:
            st.warning("⚠️ No completed email drafts found to create Gmail drafts")
            st.info("💡 Complete the research and email generation process first, then return to this tab to create Gmail drafts.")
            return
        
        # Check for email addresses in the data
        email_fields = ['email', 'Email', 'email_address', 'Email_Address', 'contact_email', 'work_email']
        has_email_column = any(field in df.columns for field in email_fields)
        profiles_with_email = 0
        
        if has_email_column:
            for field in email_fields:
                if field in completed_profiles.columns:
                    profiles_with_email += completed_profiles[field].notna().sum()
                    break
        
        # Show processing status
        if st.session_state.processing_complete:
            st.success("✅ Processing completed this session - ready to create Gmail drafts!")
        else:
            st.info("📋 Found existing email drafts in your data - you can create Gmail drafts from them")
        
        st.write(f"**{len(completed_profiles)} email drafts** are ready to be created in Gmail")
        
        # Email recipient information
        if has_email_column and profiles_with_email > 0:
            st.success(f"✅ **{profiles_with_email} profiles** have email addresses - drafts will include recipients")
        elif has_email_column:
            st.warning("⚠️ **Email column found but no email addresses** - drafts will be created without recipients")
        else:
            st.warning("⚠️ **No email column found** - drafts will be created without recipients")
            
        with st.expander("📋 About Email Recipients", expanded=not has_email_column):
            st.write("**To include recipients in Gmail drafts:**")
            st.write("• Add an email column to your spreadsheet with one of these names:")
            st.code(", ".join(email_fields))
            st.write("• The app will automatically detect and use email addresses")
            st.write("• Drafts without email addresses will still be created (you can add recipients manually in Gmail)")
            st.write("• **Tip:** The most common column name is simply `email`")
        
        # Subject prefix option
        subject_prefix = st.text_input(
            "Subject Prefix (optional)", 
            placeholder="e.g., '[Company Name] - '",
            help="Add a prefix to all email subjects for easy identification"
        )
        
        # Create drafts button
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("📧 Create Gmail Drafts", type="primary"):
                self._create_gmail_drafts(completed_profiles, subject_prefix)
        
        with col2:
            if st.button("🔍 View Recent Drafts"):
                self._show_recent_drafts()
        
        # Show created drafts from this session
        if st.session_state.gmail_drafts_created:
            st.subheader("✅ Drafts Created This Session")
            drafts_df = pd.DataFrame(st.session_state.gmail_drafts_created)
            st.dataframe(
                drafts_df,
                column_config={
                    "profile": "Profile Name",
                    "recipient": "Recipient Email",
                    "subject": "Email Subject",
                    "status": "Status",
                    "draft_id": "Gmail Draft ID"
                },
                use_container_width=True,
                hide_index=True
            )
            
            # Add link to Gmail
            st.markdown("🔗 [Open Gmail Drafts](https://mail.google.com/mail/u/0/#drafts)")
    
    def _create_gmail_drafts(self, profiles_df: pd.DataFrame, subject_prefix: str = ""):
        """Create Gmail drafts for completed profiles."""
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_profiles = len(profiles_df)
        successful_drafts = 0
        failed_drafts = 0
        
        # Clear previous session drafts
        st.session_state.gmail_drafts_created = []
        
        for idx, (_, row) in enumerate(profiles_df.iterrows()):
            profile = row.to_dict()
            email_content = profile.get('draft', '')
            
            if not email_content:
                continue
            
            # Extract recipient email using same logic as create_draft
            recipient_email = None
            email_fields = ['email', 'Email', 'email_address', 'Email_Address', 'contact_email', 'work_email']
            for field in email_fields:
                if field in profile and profile[field] and str(profile[field]).strip():
                    recipient_email = str(profile[field]).strip()
                    break
            
            status_text.text(f"Creating draft for {profile.get('name', 'Unknown')}...")
            
            try:
                draft_id = self.gmail_service.create_draft(
                    profile, 
                    email_content, 
                    subject_prefix
                )
                
                if draft_id:
                    successful_drafts += 1
                    # Extract subject for display
                    lines = email_content.split('\n')
                    subject = next((line[8:].strip() for line in lines if line.lower().startswith('subject:')), 
                                 f"Partnership Opportunity - {profile.get('company', 'Your Company')}")
                    
                    if subject_prefix:
                        subject = f"{subject_prefix}{subject}"
                    
                    st.session_state.gmail_drafts_created.append({
                        "profile": profile.get('name', 'Unknown'),
                        "recipient": recipient_email or 'No email found',
                        "subject": subject,
                        "status": "✅ Created",
                        "draft_id": draft_id
                    })
                else:
                    failed_drafts += 1
                    st.session_state.gmail_drafts_created.append({
                        "profile": profile.get('name', 'Unknown'),
                        "recipient": recipient_email or 'No email found',
                        "subject": "Failed to create",
                        "status": "❌ Failed",
                        "draft_id": "N/A"
                    })
                    
            except Exception as e:
                failed_drafts += 1
                st.session_state.gmail_drafts_created.append({
                    "profile": profile.get('name', 'Unknown'),
                    "recipient": recipient_email or 'No email found',
                    "subject": f"Error: {str(e)[:50]}...",
                    "status": "❌ Error",
                    "draft_id": "N/A"
                })
                self.config.logger.error(f"Error creating draft for {profile.get('name')}: {e}")
            
            # Update progress
            progress = (idx + 1) / total_profiles
            progress_bar.progress(progress)
        
        # Final status
        status_text.text(f"Completed! {successful_drafts} successful, {failed_drafts} failed")
        
        if successful_drafts > 0:
            st.success(f"✅ Successfully created {successful_drafts} Gmail drafts!")
            st.balloons()
        
        if failed_drafts > 0:
            st.warning(f"⚠️ {failed_drafts} drafts failed to create. Check the table below for details.")
    
    def _show_recent_drafts(self):
        """Show recent Gmail drafts."""
        with st.spinner("Loading recent drafts..."):
            recent_drafts = self.gmail_service.list_recent_drafts()
        
        if recent_drafts:
            st.subheader("📋 Recent Gmail Drafts")
            drafts_df = pd.DataFrame(recent_drafts)
            st.dataframe(
                drafts_df,
                column_config={
                    "subject": "Subject",
                    "snippet": "Preview",
                    "created": "Created"
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No recent drafts found")
    
    def _force_complete_reauthentication(self):
        """Force complete re-authentication for both Google Sheets and Gmail."""
        try:
            # Clear session state
            st.session_state.authenticated = False
            st.session_state.gmail_authenticated = False
            st.session_state.spreadsheets = None
            st.session_state.selected_spreadsheet = None
            st.session_state.selected_sheet = None
            if 'google_credentials' in st.session_state:
                del st.session_state.google_credentials
            
            # Delete token file if it exists
            token_path = "token.json"
            if os.path.exists(token_path):
                os.remove(token_path)
                st.success("✅ Cleared stored authentication")
            
            # Start new OAuth flow with both services
            st.info("🔄 Starting new authentication flow for both Google Sheets and Gmail...")
            if self._authenticate_both_services():
                st.session_state.authenticated = True
                st.session_state.gmail_authenticated = True
                st.success("✅ Complete re-authentication successful!")
                st.rerun()
            else:
                st.error("❌ Re-authentication failed. Please try again.")
                
        except Exception as e:
            st.error(f"Error during re-authentication: {str(e)}")
            self.config.logger.error(f"Re-authentication error: {e}")
    
    def _authenticate_both_services(self):
        """Authenticate both Google Sheets and Gmail services with proper OAuth flow."""
        try:
            creds_path = os.getenv("CREDENTIALS_PATH", "credentials.json")
            if not os.path.exists(creds_path):
                st.error("❌ Google credentials file not found. Please add 'credentials.json' to your project directory.")
                st.info("📋 To get credentials: Go to Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client ID")
                return False
            
            # Clear any existing token to force fresh authentication
            token_path = "token.json"
            if os.path.exists(token_path):
                os.remove(token_path)
                st.info("🔄 Cleared previous token to ensure fresh authentication")
            
            # Start OAuth flow with all required scopes
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, self.config.scopes)
            credentials = flow.run_local_server(port=0)
            
            # Verify all required scopes are present
            required_scopes = set(self.config.scopes)
            granted_scopes = set(credentials.scopes) if credentials.scopes else set()
            
            missing_scopes = required_scopes - granted_scopes
            if missing_scopes:
                st.error(f"❌ Missing required scopes: {', '.join(missing_scopes)}")
                st.error("Please ensure all required APIs are enabled and scopes are configured in OAuth consent screen")
                return False
            
            # Save credentials
            Path(token_path).write_text(credentials.to_json())
            st.session_state.google_credentials = json.loads(credentials.to_json())
            
            # Test both services
            try:
                sheets_service = build("sheets", "v4", credentials=credentials)
                gmail_service = build("gmail", "v1", credentials=credentials)
                
                # Simple test calls to verify access
                sheets_service.spreadsheets().get(spreadsheetId="test").execute()
            except Exception as test_error:
                # Ignore test errors - the main thing is that we have the right scopes
                pass
            
            self.sheets_service._credentials = credentials
            self.sheets_service._service = build("sheets", "v4", credentials=credentials)
            self.gmail_service._credentials = credentials
            self.gmail_service._service = build("gmail", "v1", credentials=credentials)
            
            return True
            
        except Exception as e:
            st.error(f"OAuth flow error: {str(e)}")
            self.config.logger.error(f"OAuth authentication error: {e}")
            return False
    
    def run(self):
        """Main application entry point."""
        st.title("🔍 LinkedIn Research Pipeline")
        st.markdown("Automated profile research and personalized email generation")
        
        # Authentication section
        if not self.render_authentication_section():
            st.info("👆 Please authenticate with Google to continue")
            return
        
        # Render sidebar once for all tabs (since sidebar is shared)
        config = self.render_sidebar()
        
        # Create tabs for different sections
        tab1, tab2, tab3 = st.tabs(["📊 Research & Processing", "📧 Email Management", "✉️ Gmail Drafts"])
        
        with tab1:
            # Sheet selection section
            sheet_config = self.render_sheet_selection()
            
            # Update config with sheet selection
            if sheet_config:
                config.update(sheet_config)
            
            # Main content area (only show if sheet is selected)
            if sheet_config:
                self.render_profile_section(config)
                self.render_processing_section(config)
            else:
                st.info("👆 Please select a spreadsheet and sheet to continue")
        
        with tab2:
            # Email Management tab - use the same config from sidebar
            self.render_email_management_section(config)
        
        with tab3:
            self.render_gmail_drafts_section()

    def validate_required_columns(self, df: pd.DataFrame) -> tuple[bool, list[str]]:
        """Validate that all required columns exist in the dataframe.
        
        Returns:
            tuple: (is_valid, missing_columns)
        """
        # Required columns based on prompts.py
        # Only truly mandatory fields that are always referenced without .get()
        required_columns = [
            'name',      # Required for both research and email prompts
            'company',   # Required for both research and email prompts  
            'role',      # Required for both research and email prompts
            # location, phone, education are now optional and handled with .get() in prompts
            # topic and subtopic are optional and handled with .get() in prompts
        ]
        
        # Convert dataframe columns to lowercase for case-insensitive comparison
        df_columns_lower = [col.lower() for col in df.columns]
        
        missing_columns = []
        for col in required_columns:
            if col.lower() not in df_columns_lower:
                missing_columns.append(col)
        
        return len(missing_columns) == 0, missing_columns

    def render_email_management_section(self, config: Dict):
        """Render email management section for viewing and regenerating emails."""
        st.subheader("📧 Email Management")
        
        # Custom Prompt Testing Section
        if st.session_state.use_custom_prompt and st.session_state.custom_email_prompt:
            with st.expander("🧪 Test Custom Email Prompt", expanded=False):
                st.write("**Test your custom prompt with sample data**")
                
                # Sample profile data for testing
                col1, col2 = st.columns(2)
                with col1:
                    test_name = st.text_input("Name", value="John Smith", key="test_name")
                    test_company = st.text_input("Company", value="TechCorp", key="test_company")
                    test_role = st.text_input("Role", value="VP of Engineering", key="test_role")
                    test_location = st.text_input("Location (optional)", value="San Francisco", key="test_location")
                
                with col2:
                    test_topic = st.text_input("Topic (optional)", value="AI Implementation", key="test_topic")
                    test_subtopic = st.text_input("Subtopic (optional)", value="Machine Learning", key="test_subtopic")
                    test_education = st.text_input("Education (optional)", value="Stanford University", key="test_education")
                    test_email = st.text_input("Email (optional)", value="john.smith@techcorp.com", key="test_email")
                
                test_research = st.text_area(
                    "Research (simulated)",
                    value="TechCorp is a leading software company that recently raised $50M in Series B funding. They are expanding their AI team and have been vocal about implementing machine learning solutions across their platform. John has been with the company for 3 years and previously worked at Google.",
                    height=100,
                    key="test_research"
                )
                
                if st.button("🔍 Preview Generated Prompt", key="test_prompt_button"):
                    try:
                        # Create test profile
                        test_profile = {
                            'name': test_name,
                            'company': test_company,
                            'role': test_role,
                            'location': test_location,
                            'topic': test_topic,
                            'subtopic': test_subtopic,
                            'education': test_education,
                            'email': test_email,
                            'research': test_research
                        }
                        
                        # Generate prompt using custom template
                        generated_prompt = get_email_prompt(test_profile, st.session_state.custom_email_prompt)
                        
                        st.success("✅ Custom prompt generated successfully!")
                        st.subheader("📝 Generated Prompt Preview:")
                        st.text_area(
                            "This is what will be sent to the AI model:",
                            value=generated_prompt,
                            height=300,
                            key="generated_prompt_preview"
                        )
                        
                    except Exception as e:
                        st.error(f"❌ Error generating prompt: {str(e)}")
                        st.info("💡 Check your custom prompt template for missing or invalid placeholders")
        
        # Check if we have profile data loaded
        if 'profiles_df' not in st.session_state or st.session_state.profiles_df.empty:
            st.warning("⚠️ No profile data loaded. Please load data first.")
            return
        
        # Check for required configuration
        if 'spreadsheet_id' not in config or 'sheet_name' not in config:
            st.warning("⚠️ Please select a spreadsheet and sheet first")
            return
        
        if not config.get('openai_api_key'):
            st.warning("⚠️ OpenAI API key required for email regeneration")
            return
        
        df = st.session_state.profiles_df
        
        # Show current prompt status
        st.markdown("---")
        if st.session_state.use_custom_prompt:
            st.info("🎯 **Using Custom Email Prompt** - All new emails will use your custom template")
        else:
            st.info("📝 **Using Default Email Prompt** - Enable custom prompt in the sidebar to customize")
        
        # Filter profiles that have emails
        profiles_with_emails = df[df['draft'].notna() & (df['draft'] != '')].copy()
        
        if profiles_with_emails.empty:
            st.info("💡 No email drafts found. Complete the research and email generation process first.")
            return
        
        st.write(f"Found **{len(profiles_with_emails)}** profiles with email drafts")
        
        # Add tabs for different views
        tab1, tab2 = st.tabs(["📧 Email Preview", "🔄 Bulk Actions"])
        
        with tab1:
            # Email preview and individual regeneration
            for idx, (df_idx, row) in enumerate(profiles_with_emails.iterrows()):
                with st.expander(f"📧 {row['name']} - {row['company']}", expanded=False):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write("**Current Email Draft:**")
                        email_content = row['draft']
                        st.text_area(
                            "Email Content", 
                            value=email_content,
                            height=200,
                            key=f"email_content_{df_idx}",
                            disabled=True
                        )
                    
                    with col2:
                        st.write("**Actions:**")
                        
                        # Regenerate button
                        if st.button(
                            "🔄 Regenerate Email", 
                            key=f"regenerate_{df_idx}",
                            help="Generate a new email using the latest AI model"
                        ):
                            with st.spinner(f"Regenerating email for {row['name']}..."):
                                try:
                                    # Use the profile data from the row
                                    profile_data = row.to_dict()
                                    new_email = self.processor.regenerate_email(profile_data, df_idx, config)
                                    
                                    st.success(f"✅ Email regenerated for {row['name']}!")
                                    st.info("🔄 Page will refresh to show the new email")
                                    time.sleep(1)
                                    st.rerun()
                                    
                                except Exception as e:
                                    st.error(f"❌ Failed to regenerate email: {str(e)}")
                        
                        # Copy email button
                        if st.button(
                            "📋 Copy Email", 
                            key=f"copy_{df_idx}",
                            help="Copy email content to clipboard"
                        ):
                            # Show the email content in a code block for easy copying
                            st.code(email_content, language="text")
                            st.info("📋 Email content displayed above - select and copy")
        
        with tab2:
            # Bulk actions
            st.write("**Bulk Email Management**")
            
            # Select profiles for bulk regeneration
            selected_profiles = st.multiselect(
                "Select profiles to regenerate emails:",
                options=profiles_with_emails.index.tolist(),
                format_func=lambda x: f"{profiles_with_emails.loc[x, 'name']} - {profiles_with_emails.loc[x, 'company']}",
                key="bulk_regenerate_selection"
            )
            
            if selected_profiles:
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    if st.button(
                        f"🔄 Regenerate {len(selected_profiles)} Emails", 
                        type="primary",
                        help="Regenerate emails for all selected profiles"
                    ):
                        # Show cost estimation for bulk regeneration
                        estimated_cost = len(selected_profiles) * 0.01  # Rough estimate
                        st.info(f"💰 Estimated cost: ~${estimated_cost:.3f}")
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        successful = 0
                        failed = 0
                        
                        for i, df_idx in enumerate(selected_profiles):
                            profile_data = profiles_with_emails.loc[df_idx].to_dict()
                            profile_name = profile_data.get('name', 'Unknown')
                            
                            status_text.text(f"Regenerating email for {profile_name}...")
                            
                            try:
                                self.processor.regenerate_email(profile_data, df_idx, config)
                                successful += 1
                                
                            except Exception as e:
                                failed += 1
                                st.error(f"❌ Failed to regenerate email for {profile_name}: {str(e)}")
                            
                            # Update progress
                            progress_bar.progress((i + 1) / len(selected_profiles))
                        
                        status_text.text(f"Completed! {successful} successful, {failed} failed")
                        
                        if successful > 0:
                            st.success(f"✅ Successfully regenerated {successful} emails!")
                            st.balloons()
                            
                        if failed == 0:
                            st.info("🔄 Page will refresh to show updated emails")
                            time.sleep(2)
                            st.rerun()
                
                with col2:
                    if st.button(
                        "📊 Preview Selected",
                        help="Preview the profiles selected for regeneration"
                    ):
                        preview_df = profiles_with_emails.loc[selected_profiles][['name', 'company', 'role']]
                        st.dataframe(preview_df, use_container_width=True)


def main():
    """Application entry point."""
    app = StreamlitApp()
    app.run()


if __name__ == "__main__":
    main() 