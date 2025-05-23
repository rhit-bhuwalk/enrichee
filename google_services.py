"""Google Services for LinkedIn Research Pipeline
==============================================
Handles all Google Sheets and Gmail operations including authentication,
data fetching, updating, and draft creation.
"""

import json
import os
import base64
import email.mime.text
import email.mime.multipart
import logging
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Set up logging
logger = logging.getLogger(__name__)


def get_google_credentials():
    """Get Google OAuth credentials from either Streamlit secrets or local file."""
    # First try Streamlit secrets (for web deployment)
    try:
        if hasattr(st, 'secrets') and 'google_oauth' in st.secrets:
            credentials_info = dict(st.secrets['google_oauth'])
            
            # Ensure proper structure for OAuth flow
            if 'client_id' in credentials_info:
                # Streamlit secrets format - wrap in 'installed' key
                oauth_config = {
                    "installed": {
                        "client_id": credentials_info.get("client_id"),
                        "client_secret": credentials_info.get("client_secret"),
                        "auth_uri": credentials_info.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
                        "token_uri": credentials_info.get("token_uri", "https://oauth2.googleapis.com/token"),
                        "auth_provider_x509_cert_url": credentials_info.get("auth_provider_x509_cert_url", "https://www.googleapis.com/oauth2/v1/certs"),
                        "redirect_uris": credentials_info.get("redirect_uris", ["http://localhost"])
                    }
                }
                return oauth_config
            else:
                # Already in proper format
                return credentials_info
    except Exception as e:
        # Log the error but continue to fallback
        logger.warning(f"Could not load Streamlit secrets: {e}")
    
    # Fallback to local credentials.json file (for local development)
    creds_path = os.getenv("CREDENTIALS_PATH", "credentials.json")
    if os.path.exists(creds_path):
        try:
            with open(creds_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Could not load credentials.json: {e}")
    
    return None


class BaseGoogleService:
    """Base class for Google services with shared authentication logic."""
    
    def __init__(self, config, service_name: str, api_version: str, required_scope: str):
        self.config = config
        self.service_name = service_name
        self.api_version = api_version
        self.required_scope = required_scope
        self._service = None
        self._credentials = None
    
    def authenticate_user(self) -> bool:
        """Authenticate user with Google OAuth flow."""
        try:
            # Check if we have stored credentials in session state
            if 'google_credentials' in st.session_state and st.session_state.google_credentials:
                creds_data = st.session_state.google_credentials
                self._credentials = Credentials.from_authorized_user_info(creds_data, self.config.scopes)
                
                # Refresh if expired
                if self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    st.session_state.google_credentials = json.loads(self._credentials.to_json())
                
                # Check if required scope is actually included
                if self.required_scope not in self._credentials.scopes:
                    self.config.logger.warning(f"{self.service_name} scope not found in stored credentials")
                    return False
                
                self._service = build(self.service_name.lower(), self.api_version, credentials=self._credentials)
                return True
            
            # Try to load from file if available (local development)
            token_path = "token.json"
            if os.path.exists(token_path):
                self._credentials = Credentials.from_authorized_user_file(token_path, self.config.scopes)
                
                if self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    Path(token_path).write_text(self._credentials.to_json())
                
                # Check if required scope is actually included
                if self.required_scope not in self._credentials.scopes:
                    self.config.logger.warning(f"{self.service_name} scope not found in token file")
                    return False
                
                # Store in session state
                st.session_state.google_credentials = json.loads(self._credentials.to_json())
                self._service = build(self.service_name.lower(), self.api_version, credentials=self._credentials)
                return True
                
            return False
            
        except Exception as e:
            self.config.logger.error(f"{self.service_name} authentication error: {str(e)}")
            return False
    
    def get_service(self):
        """Get Google service."""
        if not self._service:
            if not self.authenticate_user():
                return None
        return self._service
    
    def start_oauth_flow(self):
        """Start the OAuth flow for new authentication."""
        try:
            credentials_info = get_google_credentials()
            if not credentials_info:
                st.error("❌ Google OAuth credentials not found.")
                
                # Show different instructions based on environment
                is_web_deployment = self._is_web_deployment()
                if is_web_deployment:
                    # Web deployment
                    st.info("🌐 **For Streamlit Cloud deployment:**")
                    st.markdown("""
                    1. Go to your app's secrets management in Streamlit Cloud
                    2. Add a section called `[google_oauth]` with your OAuth credentials:
                    ```toml
                    [google_oauth]
                    client_id = "your-client-id"
                    client_secret = "your-client-secret"
                    redirect_uris = ["http://localhost"]
                    auth_uri = "https://accounts.google.com/o/oauth2/auth"
                    token_uri = "https://oauth2.googleapis.com/token"
                    ```
                    """)
                else:
                    # Local development
                    st.info("💻 **For local development:**")
                    st.markdown("""
                    Add a `credentials.json` file to your project directory with your OAuth 2.0 credentials.
                    
                    📋 **To get credentials:** Go to Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client ID
                    """)
                return False
            
            # Create OAuth flow from credentials
            flow = InstalledAppFlow.from_client_config(
                credentials_info,
                self.config.scopes
            )
            
            # Determine if we're in a web deployment environment
            is_web_deployment = self._is_web_deployment()
            
            if is_web_deployment:
                # Web deployment - use manual authorization code flow
                return self._handle_web_oauth_flow(flow)
            else:
                # Local development - use local server
                return self._handle_local_oauth_flow(flow)
            
        except Exception as e:
            st.error(f"OAuth flow error: {str(e)}")
            self.config.logger.error(f"OAuth flow error: {e}")
            return False
    
    def _handle_web_oauth_flow(self, flow):
        """Handle OAuth flow for web deployment environments."""
        try:
            # Check if we already have an authorization code from URL params
            # st.query_params returns lists for each key (e.g., {"code": ["xyz"]})
            # Handle both list and string for compatibility across Streamlit versions
            auth_code_param = st.query_params.get("code")
            if isinstance(auth_code_param, list):
                auth_code = auth_code_param[0] if auth_code_param else None
            else:
                auth_code = auth_code_param
            
            if auth_code:
                # We have an authorization code, exchange it for tokens
                try:
                    flow.fetch_token(code=auth_code)
                    self._credentials = flow.credentials
                    
                    # Save credentials to session state
                    st.session_state.google_credentials = json.loads(self._credentials.to_json())
                    self._service = build(self.service_name.lower(), self.api_version, credentials=self._credentials)
                    
                    # Clear the URL parameters to avoid reprocessing on reload
                    try:
                        st.query_params.clear()
                    except AttributeError:
                        # Older versions: fall back to setting empty params
                        try:
                            st.query_params.update({})
                        except Exception:
                            pass
                    
                    st.success("✅ Authentication successful!")
                    st.rerun()
                    return True
                    
                except Exception as e:
                    st.error(f"❌ Authentication failed: {str(e)}")
                    self.config.logger.error(f"Token exchange failed: {e}")
                    return False
            else:
                # No authorization code yet, show the authentication link
                # Use a more flexible redirect URI approach
                redirect_uri = self._get_web_redirect_uri()
                flow.redirect_uri = redirect_uri
                
                auth_url, _ = flow.authorization_url(
                    prompt='consent',
                    access_type='offline',
                    include_granted_scopes='true'
                )
                
                st.warning("🌐 **Web Authentication Required**")
                st.markdown(f"""
                **Step 1:** [Click here to authenticate with Google]({auth_url})
                
                **Step 2:** After granting permissions, you'll be redirected back to this app automatically.
                
                ⚠️ **Important:** Make sure your Google Cloud OAuth client has the correct redirect URI configured:
                `{redirect_uri}`
                """)
                
                with st.expander("🔧 Troubleshooting", expanded=False):
                    st.markdown(f"""
                    **If you get a "redirect_uri_mismatch" error:**
                    
                    1. Go to [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials)
                    2. Edit your OAuth 2.0 Client ID
                    3. Add this redirect URI: `{redirect_uri}`
                    4. Save and try again
                    
                    **Current redirect URI:** `{redirect_uri}`
                    """)
                
                return False
                
        except Exception as e:
            st.error(f"Web OAuth flow error: {str(e)}")
            self.config.logger.error(f"Web OAuth flow error: {e}")
            return False
    
    def _handle_local_oauth_flow(self, flow):
        """Handle OAuth flow for local development."""
        try:
            # Local development - use local server
            self._credentials = flow.run_local_server(port=0)
            
            # Save credentials
            Path("token.json").write_text(self._credentials.to_json())
            st.session_state.google_credentials = json.loads(self._credentials.to_json())
            
            self._service = build(self.service_name.lower(), self.api_version, credentials=self._credentials)
            st.success("✅ Authentication successful!")
            return True
            
        except Exception as e:
            st.error(f"Local OAuth flow error: {str(e)}")
            self.config.logger.error(f"Local OAuth flow error: {e}")
            return False
    
    def _get_web_redirect_uri(self):
        """Get the appropriate redirect URI for web deployment."""
        try:
            # Method 1: Try to get from Streamlit's internal context
            try:
                import streamlit.web.server.server as server
                if hasattr(server, 'Server') and server.Server._singleton:
                    server_instance = server.Server._singleton
                    if hasattr(server_instance, '_config'):
                        base_url = server_instance._config.get('server.baseUrlPath', '')
                        if base_url:
                            return base_url.rstrip('/') + '/'
            except Exception:
                pass
            
            # Method 2: Try to get from browser/request context
            try:
                # Check if we can get the current URL from the browser
                if hasattr(st, 'context') and hasattr(st.context, 'headers'):
                    host = st.context.headers.get('host')
                    if host and not host.startswith('localhost'):
                        protocol = 'https' if 'streamlit.app' in host else 'http'
                        return f"{protocol}://{host}/"
            except Exception:
                pass
            
            # Method 3: Check for Streamlit Cloud deployment (enrichee.streamlit.app)
            if 'STREAMLIT_SHARING_MODE' in os.environ or 'STREAMLIT_CLOUD' in os.environ:
                # Known Streamlit Cloud URL for this app
                return "https://enrichee.streamlit.app/"
            
            # Method 4: Check for local development with specific port
            try:
                # Try to get the current port from Streamlit config
                if hasattr(st, 'get_option'):
                    server_port = st.get_option('server.port')
                    if server_port:
                        return f"http://localhost:{server_port}/"
            except Exception:
                pass
            
            # Method 5: Environment-based detection for other cloud platforms
            possible_urls = [
                # Try to get from environment variables
                os.environ.get('STREAMLIT_SERVER_HEADLESS_URL'),
                os.environ.get('STREAMLIT_APP_URL'),
                # Common Streamlit Cloud pattern
                f"https://{os.environ.get('STREAMLIT_APP_NAME', 'app')}.streamlit.app/",
            ]
            
            for url in possible_urls:
                if url and url.startswith('http'):
                    return url if url.endswith('/') else url + '/'
            
            # Method 6: Try to get from Streamlit config
            try:
                if hasattr(st, 'get_option'):
                    server_address = st.get_option('server.address')
                    server_port = st.get_option('server.port')
                    if server_address and server_port and not server_address.startswith('localhost'):
                        return f"https://{server_address}:{server_port}/"
            except Exception:
                pass
            
            # Method 7: Check if we have secrets (indicates web deployment)
            if self._has_secrets_safely():
                # For web deployment, default to the known Streamlit Cloud URL
                try:
                    if hasattr(st, 'secrets') and 'google_oauth' in st.secrets:
                        redirect_uris = st.secrets['google_oauth'].get('redirect_uris', [])
                        if redirect_uris and isinstance(redirect_uris, list) and len(redirect_uris) > 0:
                            return redirect_uris[0]
                except Exception:
                    pass
                
                # Default to the known Streamlit Cloud URL for this app
                return "https://enrichee.streamlit.app/"
            
            # Method 8: Local development fallback - check for common ports
            # Default to port 8501 but also check for other common ports
            common_ports = [8501, 8502, 8503, 8504, 8505, 8506, 8507, 8508]
            
            # First try to detect the actual port being used
            try:
                import socket
                for port in common_ports:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    result = sock.connect_ex(('localhost', port))
                    sock.close()
                    if result == 0:  # Port is open
                        return f"http://localhost:{port}/"
            except Exception:
                pass
            
            # Final fallback
            return "http://localhost:8501/"
            
        except Exception as e:
            self.config.logger.error(f"Error detecting redirect URI: {e}")
            return "http://localhost:8501/"
    
    def _has_secrets_safely(self):
        """Safely check if Google OAuth secrets exist without raising exceptions."""
        try:
            return hasattr(st, 'secrets') and 'google_oauth' in st.secrets
        except Exception:
            return False
    
    def _is_web_deployment(self):
        """Detect if we're running in a web deployment environment."""
        # Check for common cloud environment indicators
        cloud_indicators = [
            'STREAMLIT_SHARING_MODE' in os.environ,
            'STREAMLIT_CLOUD' in os.environ,
            'DYNO' in os.environ,  # Heroku
            'KUBERNETES_SERVICE_HOST' in os.environ,
            'CLOUD_RUN_JOB' in os.environ,
        ]
        
        # Check for secrets-based configuration
        secrets_available = (
            hasattr(st, 'secrets') and 
            'google_oauth' in st.secrets and
            not os.path.exists("credentials.json")
        )
        
        # Check for headless environment (no display/browser)
        headless_env = (
            os.environ.get('DISPLAY') is None and 
            os.environ.get('BROWSER') is None and
            'SSH_CLIENT' not in os.environ  # Exclude SSH sessions
        )
        
        return any(cloud_indicators) or secrets_available or headless_env


class GoogleSheetsService(BaseGoogleService):
    """Handles all Google Sheets operations."""
    
    def __init__(self, config):
        super().__init__(config, "sheets", "v4", "https://www.googleapis.com/auth/spreadsheets")
    
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
        if not requests:
            self.config.logger.warning("No requests provided for batch update")
            return
            
        service = self.get_service()
        if not service:
            self.config.logger.error("Could not get Google Sheets service for batch update")
            return
            
        try:
            response = service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, 
                body={"requests": requests}
            ).execute()
            
            replies = response.get('replies', [])
            self.config.logger.info(f"Successfully updated {len(replies)} cells in spreadsheet")
            
        except Exception as e:
            self.config.logger.error(f"Error updating sheets: {str(e)}")
            # Re-raise for caller to handle
            raise


class GmailService(BaseGoogleService):
    """Handles all Gmail operations for creating email drafts."""
    
    def __init__(self, config):
        super().__init__(config, "gmail", "v1", "https://www.googleapis.com/auth/gmail.modify")
    
    def create_draft(self, profile: Dict, email_content: str, subject_prefix: str = "") -> Optional[str]:
        """Create a Gmail draft for the given profile and email content."""
        service = self.get_service()
        if not service:
            return None
        
        try:
            # Extract recipient email from profile data
            recipient_email = None
            # Try common email field names (case-insensitive)
            email_fields = [
                'email', 'Email', 'EMAIL',
                'email_address', 'Email_Address', 'EMAIL_ADDRESS',
                'contact_email', 'Contact_Email', 'CONTACT_EMAIL',
                'work_email', 'Work_Email', 'WORK_EMAIL',
                'business_email', 'Business_Email', 'BUSINESS_EMAIL',
                'professional_email', 'Professional_Email'
            ]
            
            for field in email_fields:
                if field in profile and profile[field]:
                    email_value = str(profile[field]).strip()
                    # Basic email validation
                    if email_value and '@' in email_value and '.' in email_value:
                        recipient_email = email_value
                        break
            
            # If no email found, log warning but still create draft
            if not recipient_email:
                self.config.logger.warning(f"No email found for {profile.get('name', 'unknown')}. Draft will be created without recipient.")
            
            # Extract email subject from the email content if available
            lines = email_content.strip().split('\n')
            subject_line = None
            body_lines = []
            
            # Look for subject line in first few lines
            for i, line in enumerate(lines[:5]):  # Check first 5 lines for subject
                line_lower = line.lower().strip()
                if line_lower.startswith('subject:'):
                    subject_line = line[8:].strip()  # Remove "Subject:" prefix
                    # Body starts after subject line
                    body_lines = lines[i+1:]
                    break
            
            # If no subject found, treat entire content as body
            if subject_line is None:
                body_lines = lines
            
            # Clean up body content
            cleaned_body_lines = []
            for line in body_lines:
                line = line.strip()
                if line:  # Skip empty lines at start
                    cleaned_body_lines.append(line)
                elif cleaned_body_lines:  # Keep empty lines in middle/end
                    cleaned_body_lines.append(line)
            
            # Fallback subject if not found in content
            if not subject_line:
                company_name = profile.get('company', profile.get('Company', 'Your Company'))
                subject_line = f"Partnership Opportunity - {company_name}"
            
            # Add prefix if provided
            if subject_prefix:
                subject_line = f"{subject_prefix}{subject_line}"
            
            # Join body content
            body = '\n'.join(cleaned_body_lines) if cleaned_body_lines else email_content
            
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