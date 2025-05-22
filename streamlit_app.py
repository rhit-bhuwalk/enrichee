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
from prompts import get_email_prompt, get_research_prompt
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
        prompt = get_email_prompt(profile)
        messages = [
            {"role": "system", "content": "You draft personalized outreach emails."},
            {"role": "user", "content": prompt},
        ]
        
        resp = completion(
            model="openai/gpt-4o-mini",
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
        with results_container:
            # Show session results table
            if st.session_state.session_results:
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


class StreamlitApp:
    """Main Streamlit application class."""
    
    def __init__(self):
        self.config = ConfigManager()
        self.cost_tracker = CostTracker()
        self.cost_estimator = CostEstimator(self.config)
        self.sheets_service = GoogleSheetsService(self.config)
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
    
    def render_authentication_section(self):
        """Render authentication section."""
        st.subheader("🔐 Google Sheets Authentication")
        
        if st.session_state.authenticated:
            st.success("✅ Authenticated with Google Sheets")
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🔄 Refresh Authentication"):
                    st.session_state.authenticated = False
                    st.session_state.spreadsheets = None
                    st.session_state.selected_spreadsheet = None
                    st.session_state.selected_sheet = None
                    if 'google_credentials' in st.session_state:
                        del st.session_state.google_credentials
                    st.rerun()
            return True
        else:
            # Check if we can authenticate automatically
            if self.sheets_service.authenticate_user():
                st.session_state.authenticated = True
                st.rerun()
                return True
            else:
                st.warning("⚠️ Please authenticate with Google Sheets to continue")
                if st.button("🔑 Start Authentication"):
                    if self.sheets_service.start_oauth_flow():
                        st.session_state.authenticated = True
                        st.success("✅ Authentication successful!")
                        st.rerun()
                    else:
                        st.error("❌ Authentication failed. Please try again.")
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
            type="password"
        )
        openai_api_key = st.sidebar.text_input(
            "OpenAI API Key", 
            value=os.getenv("OPENAI_API_KEY", ""), 
            type="password"
        )
        
        # Processing parameters (hidden by default)
        with st.sidebar.expander("🔧 Advanced Settings", expanded=False):
            max_workers = st.slider("Max Workers", 1, 50, 25)
            research_max_tokens = st.slider("Research Max Tokens", 100, 2000, 800)
            email_max_tokens = st.slider("Email Max Tokens", 100, 1000, 350)
            timeout_seconds = st.slider("Timeout (seconds)", 10, 120, 40)
            profile_limit = st.number_input("Profile Limit (0 = all)", 0, 1000, 0)
        
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
                st.info("💡 Please add the required columns to your spreadsheet before processing.")
            else:
                st.success("✅ All required columns found!")
            
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
    
    def run(self):
        """Main application entry point."""
        st.title("🔍 LinkedIn Research Pipeline")
        st.markdown("Automated profile research and personalized email generation")
        
        # Authentication section
        if not self.render_authentication_section():
            st.info("👆 Please authenticate with Google Sheets to continue")
            return
        
        # Sheet selection section
        sheet_config = self.render_sheet_selection()
        
        # Render sidebar and get config
        config = self.render_sidebar()
        
        # Main content area (only show if sheet is selected)
        if sheet_config:
            self.render_profile_section(config)
            self.render_processing_section(config)
        else:
            st.info("👆 Please select a spreadsheet and sheet to continue")

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


def main():
    """Application entry point."""
    app = StreamlitApp()
    app.run()


if __name__ == "__main__":
    main() 