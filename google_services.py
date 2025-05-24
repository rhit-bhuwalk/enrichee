"""Google Services for LinkedIn Research Pipeline
==============================================
Handles Google Sheets and Gmail operations.
"""

import json
import os
import base64
import email.mime.text
import logging
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


def get_google_credentials():
    """Get Google OAuth credentials from Streamlit secrets or local file."""
   
    try:
        if hasattr(st, 'secrets') and 'google_oauth' in st.secrets:
            credentials_info = dict(st.secrets['google_oauth'])
            if 'client_id' in credentials_info:
                return {
                    "installed": {
                        "client_id": credentials_info["client_id"],
                        "client_secret": credentials_info["client_secret"],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": ["https://enrichee.streamlit.app/"]
                    }
                }
            logger.info("Credentials info:")
            return credentials_info
    except Exception as e:
        logger.warning(f"Could not load Streamlit secrets: {e}")
    
    # Fallback to local credentials.json
    if os.path.exists("credentials.json"):
        try:
            with open("credentials.json", 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Could not load credentials.json: {e}")
    
    return None


class BaseGoogleService:
    """Base class for Google services with shared authentication."""
    
    def __init__(self, config, service_name: str, api_version: str, required_scope: str):
        self.config = config
        self.service_name = service_name
        self.api_version = api_version
        self.required_scope = required_scope
        self._service = None
        self._credentials = None
    
    def authenticate_user(self) -> bool:
        """Authenticate user with Google OAuth."""
        try:
            # Check session state first
            if 'google_credentials' in st.session_state and st.session_state.google_credentials:
                self._credentials = Credentials.from_authorized_user_info(
                    st.session_state.google_credentials, self.config.scopes
                )
                
                if self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    st.session_state.google_credentials = json.loads(self._credentials.to_json())
                
                if self.required_scope in self._credentials.scopes:
                    self._service = build(self.service_name.lower(), self.api_version, credentials=self._credentials)
                    return True
            
            # Try token file
            if os.path.exists("token.json"):
                self._credentials = Credentials.from_authorized_user_file("token.json", self.config.scopes)
                
                if self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    Path("token.json").write_text(self._credentials.to_json())
                
                if self.required_scope in self._credentials.scopes:
                    st.session_state.google_credentials = json.loads(self._credentials.to_json())
                    self._service = build(self.service_name.lower(), self.api_version, credentials=self._credentials)
                    return True
                
            return False
            
        except Exception as e:
            logger.error(f"{self.service_name} authentication error: {e}")
            return False
    
    def get_service(self):
        """Get Google service."""
        if not self._service:
            if not self.authenticate_user():
                return None
        return self._service
    
    def start_oauth_flow(self):
        """Start OAuth flow for authentication."""
        try:
            credentials_info = get_google_credentials()
            if not credentials_info:
                st.error("❌ Google OAuth credentials not found.")
                st.info("""
                Add `credentials.json` file to your project directory or configure Streamlit secrets.
                
                📋 **To get credentials:** Go to Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client ID
                """)
                return False
            
            flow = InstalledAppFlow.from_client_config(credentials_info, self.config.scopes)
            
            # Handle web vs local environments
            if self._is_web_deployment():
                return self._handle_web_oauth(flow)
            else:
                return self._handle_local_oauth(flow)
                
        except Exception as e:
            st.error(f"OAuth flow error: {e}")
            return False
    
    def _handle_web_oauth(self, flow):
        """Handle OAuth for web deployment."""
        redirect_uri = self._get_redirect_uri()
        flow.redirect_uri = redirect_uri
        
        # Check for authorization code
        auth_code = st.query_params.get("code")
        if auth_code:
            try:
                flow.fetch_token(code=auth_code)
                self._credentials = flow.credentials
                st.session_state.google_credentials = json.loads(self._credentials.to_json())
                self._service = build(self.service_name.lower(), self.api_version, credentials=self._credentials)
                
                st.query_params.clear()
                st.success("✅ Authentication successful!")
                st.rerun()
                return True
                
            except Exception as e:
                st.error(f"❌ Authentication failed: {e}")
                return False
        else:
            # Show auth link
            auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
            st.warning("🌐 **Authentication Required**")
            st.markdown(f"[Click here to authenticate with Google]({auth_url})")
            st.info(f"**Redirect URI:** `{redirect_uri}`")
            return False
    
    def _handle_local_oauth(self, flow):
        """Handle OAuth for local development."""
        try:
            self._credentials = flow.run_local_server(port=0)
            Path("token.json").write_text(self._credentials.to_json())
            st.session_state.google_credentials = json.loads(self._credentials.to_json())
            self._service = build(self.service_name.lower(), self.api_version, credentials=self._credentials)
            st.success("✅ Authentication successful!")
            return True
        except Exception as e:
            st.error(f"Local OAuth error: {e}")
            return False
    
    def _get_redirect_uri(self):
        """Get redirect URI for web deployment."""
        # Check for Streamlit Cloud
        if 'STREAMLIT_SHARING_MODE' in os.environ or 'STREAMLIT_CLOUD' in os.environ:
            return "https://enrichee.streamlit.app/"
        
        # Try to get from secrets
        try:
            if hasattr(st, 'secrets') and 'google_oauth' in st.secrets:
                redirect_uris = st.secrets['google_oauth'].get('redirect_uris', [])
                if redirect_uris:
                    return redirect_uris[0]
        except Exception:
            pass
        
        return "http://localhost:8501/"
    
    def _is_web_deployment(self):
        """Check if running in web deployment."""
        return (
            'STREAMLIT_SHARING_MODE' in os.environ or
            'STREAMLIT_CLOUD' in os.environ or
            (hasattr(st, 'secrets') and 'google_oauth' in st.secrets and not os.path.exists("credentials.json"))
        )


class GoogleSheetsService(BaseGoogleService):
    """Handles Google Sheets operations."""
    
    def __init__(self, config):
        super().__init__(config, "sheets", "v4", "https://www.googleapis.com/auth/spreadsheets")
    
    def list_spreadsheets(self) -> List[Dict]:
        """List available spreadsheets."""
        service = self.get_service()
        if not service:
            return []
        
        try:
            drive_service = build("drive", "v3", credentials=self._credentials)
            results = drive_service.files().list(
                q="mimeType='application/vnd.google-apps.spreadsheet'",
                pageSize=100,
                fields="files(id, name, modifiedTime)"
            ).execute()
            
            items = results.get('files', [])
            return [{'id': item['id'], 'name': item['name'], 'modified': item['modifiedTime']} for item in items]
            
        except Exception as e:
            st.error(f"Error listing spreadsheets: {e}")
            return []
    
    def list_sheets_in_spreadsheet(self, spreadsheet_id: str) -> List[Dict]:
        """List sheets within a spreadsheet."""
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
            st.error(f"Error listing sheets: {e}")
            return []
    
    def get_sheet_id_by_name(self, spreadsheet_id: str, sheet_name: str) -> Optional[int]:
        """Get sheet ID by name."""
        sheets = self.list_sheets_in_spreadsheet(spreadsheet_id)
        for sheet in sheets:
            if sheet["name"] == sheet_name:
                return sheet["id"]
        return None
    
    def fetch_profiles(self, spreadsheet_id: str, sheet_name: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch profiles from Google Sheet."""
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
            st.error(f"Error fetching profiles: {e}")
            return pd.DataFrame()
    
    def batch_update_cells(self, spreadsheet_id: str, requests: List[Dict]):
        """Update Google Sheets with batch requests."""
        if not requests:
            logger.warning("No requests provided for batch update")
            return
            
        service = self.get_service()
        if not service:
            logger.error("Could not get Google Sheets service")
            return
            
        try:
            response = service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, 
                body={"requests": requests}
            ).execute()
            
            replies = response.get('replies', [])
            logger.info(f"Successfully updated {len(replies)} cells")
            
        except Exception as e:
            logger.error(f"Error updating sheets: {e}")
            raise


class GmailService(BaseGoogleService):
    """Handles Gmail operations."""
    
    def __init__(self, config):
        super().__init__(config, "gmail", "v1", "https://www.googleapis.com/auth/gmail.modify")
    
    def create_draft(self, profile: Dict, email_content: str, subject_prefix: str = "") -> Optional[str]:
        """Create Gmail draft for profile."""
        service = self.get_service()
        if not service:
            return None
        
        try:
            # Extract recipient email
            recipient_email = None
            email_fields = ['email', 'Email', 'email_address', 'contact_email']
            
            for field in email_fields:
                if field in profile and profile[field]:
                    email_value = str(profile[field]).strip()
                    if email_value and '@' in email_value and '.' in email_value:
                        recipient_email = email_value
                        break
            
            # Parse email content
            lines = email_content.strip().split('\n')
            subject_line = None
            body_lines = []
            
            for i, line in enumerate(lines[:5]):
                if line.lower().strip().startswith('subject:'):
                    subject_line = line[8:].strip()
                    body_lines = lines[i+1:]
                    break
            
            if subject_line is None:
                body_lines = lines
                company_name = profile.get('company', profile.get('Company', 'Your Company'))
                subject_line = f"Partnership Opportunity - {company_name}"
            
            if subject_prefix:
                subject_line = f"{subject_prefix}{subject_line}"
            
            body = '\n'.join(line.strip() for line in body_lines if line.strip())
            
            # Create email message
            message = email.mime.text.MIMEText(body)
            message['Subject'] = subject_line
            if recipient_email:
                message['To'] = recipient_email
            
            # Create draft
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            draft_body = {'message': {'raw': raw_message}}
            
            draft = service.users().drafts().create(userId='me', body=draft_body).execute()
            return draft.get('id')
            
        except Exception as e:
            logger.error(f"Error creating Gmail draft: {e}")
            return None
    
    def list_recent_drafts(self, max_results: int = 10) -> List[Dict]:
        """List recent drafts."""
        service = self.get_service()
        if not service:
            return []
        
        try:
            results = service.users().drafts().list(userId='me', maxResults=max_results).execute()
            drafts = results.get('drafts', [])
            
            detailed_drafts = []
            for draft in drafts[:5]:
                try:
                    draft_detail = service.users().drafts().get(userId='me', id=draft['id']).execute()
                    message = draft_detail.get('message', {})
                    headers = message.get('payload', {}).get('headers', [])
                    
                    subject = "No Subject"
                    for header in headers:
                        if header['name'] == 'Subject':
                            subject = header['value']
                            break
                    
                    snippet = message.get('snippet', '')
                    if len(snippet) > 100:
                        snippet = snippet[:100] + "..."
                    
                    detailed_drafts.append({
                        'id': draft['id'],
                        'subject': subject,
                        'snippet': snippet,
                        'created': draft_detail.get('message', {}).get('internalDate', '')
                    })
                except Exception as e:
                    logger.error(f"Error getting draft details: {e}")
                    continue
            
            return detailed_drafts
            
        except Exception as e:
            logger.error(f"Error listing drafts: {e}")
            return [] 