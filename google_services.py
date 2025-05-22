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
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


def get_google_credentials():
    """Get Google OAuth credentials from either Streamlit secrets or local file."""
    # First try Streamlit secrets (for web deployment)
    try:
        if hasattr(st, 'secrets') and 'google_oauth' in st.secrets:
            credentials_info = dict(st.secrets['google_oauth'])
            return credentials_info
    except Exception:
        pass
    
    # Fallback to local credentials.json file (for local development)
    creds_path = os.getenv("CREDENTIALS_PATH", "credentials.json")
    if os.path.exists(creds_path):
        with open(creds_path, 'r') as f:
            return json.load(f)
    
    return None


class GoogleSheetsService:
    """Handles all Google Sheets operations."""
    
    def __init__(self, config):
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
            
            # Try to load from file if available (local development)
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
            credentials_info = get_google_credentials()
            if not credentials_info:
                st.error("❌ Google OAuth credentials not found.")
                
                # Show different instructions based on environment
                if 'STREAMLIT_SHARING_MODE' in os.environ or 'STREAMLIT_CLOUD' in os.environ:
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
                {
                    "installed": credentials_info if "client_id" in credentials_info else credentials_info.get("installed", credentials_info)
                },
                self.config.scopes
            )
            
            # For web deployment, we need a different approach
            if 'STREAMLIT_SHARING_MODE' in os.environ or 'STREAMLIT_CLOUD' in os.environ:
                # Use the authorization URL approach for web deployment
                auth_url, _ = flow.authorization_url(prompt='consent')
                
                st.warning("🌐 **Web Authentication Required**")
                st.markdown(f"**[Click here to authenticate with Google]({auth_url})**")
                st.info("After authentication, you'll get an authorization code. Paste it below:")
                
                auth_code = st.text_input("Authorization Code", type="password")
                if auth_code and st.button("Complete Authentication"):
                    try:
                        flow.fetch_token(code=auth_code)
                        self._credentials = flow.credentials
                        
                        # Save credentials to session state
                        st.session_state.google_credentials = json.loads(self._credentials.to_json())
                        self._service = build("sheets", "v4", credentials=self._credentials)
                        st.success("✅ Authentication successful!")
                        return True
                    except Exception as e:
                        st.error(f"❌ Authentication failed: {str(e)}")
                        return False
                
                return False
            else:
                # Local development - use local server
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
    
    def __init__(self, config):
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