"""LinkedIn Research Pipeline - Streamlit App
===========================================
Interactive web interface for bulk profile research and personalized email generation.
"""

import streamlit as st
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict
import pandas as pd
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import litellm
from prompts import get_default_email_prompt_template, get_email_prompt

# Import our new modules
from config import ConfigManager
from cost_tracking import CostTracker, CostEstimator
from google_services import GoogleSheetsService, GmailService
from ai_service import AIService
from profile_processor import ProfileProcessor


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
            page_title="Enrichee",
            page_icon="🔍",
            initial_sidebar_state="collapsed"
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
            sheets_status = self.sheets_service.authenticate_user()
            gmail_status = self.gmail_service.authenticate_user()
            
            # Both services must be authenticated
            if not sheets_status or not gmail_status:
              
                st.session_state.authenticated = False
                st.session_state.gmail_authenticated = False
                st.error("❌ **Authentication Incomplete:** Missing required permissions")
                st.warning("🔄 You need permissions for both Google Sheets and Gmail to use this app")
                
                if st.button("🔑 Re-authenticate with Full Permissions", type="primary"):
                    self._force_complete_reauthentication()
                
                return False
            
            st.session_state.gmail_authenticated = gmail_status
            
            col1, col2 = st.columns(2)
            with col1:
                st.success("✅ Google Sheets: Authenticated")
            with col2:
                st.success("✅ Gmail: Authenticated")
            
            
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
            sheets_auth = self.sheets_service.authenticate_user()
            gmail_auth = self.gmail_service.authenticate_user() if sheets_auth else False
            
            if sheets_auth and gmail_auth:
                st.session_state.authenticated = True
                st.session_state.gmail_authenticated = True
                st.rerun()
            else:                
                with st.expander("🛠️ Setup Instructions", expanded=False):
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
                
                if st.button("🔑 Authenticate", type="primary"):
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
    
    def _has_secrets_safely(self) -> bool:
        """Safely check if Google OAuth secrets exist without raising exceptions."""
        try:
            return hasattr(st, 'secrets') and 'google_oauth' in st.secrets
        except Exception:
            return False
    
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
            # Use the updated authentication approach from google_services
            sheets_auth = self.sheets_service.start_oauth_flow()
            
            if sheets_auth:
                # Gmail uses the same credentials, so we just need to verify it works
                gmail_auth = self.gmail_service.authenticate_user()
                
                if gmail_auth:
                    st.success("✅ Successfully authenticated both Google Sheets and Gmail!")
                    return True
                else:
                    st.error("❌ Gmail authentication failed.")
                    return False
            else:
                st.error("❌ Google Sheets authentication failed.")
                return False
                
        except Exception as e:
            st.error(f"Authentication error: {str(e)}")
            self.config.logger.error(f"OAuth authentication error: {e}")
            return False
    
    def run(self):
        """Main application entry point."""
        st.title("🔍 LinkedIn Research Pipeline")
        st.markdown("Automated profile research and personalized email generation")
        
        # Authentication section
        self.render_authentication_section()
        
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