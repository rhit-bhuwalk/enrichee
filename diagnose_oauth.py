#!/usr/bin/env python3
"""
OAuth Diagnostic Script
======================
Quick diagnostic to identify OAuth redirect URI issues.
"""

import streamlit as st
import os
from google_services import get_google_credentials, BaseGoogleService
from config import ConfigManager

def main():
    st.title("🔍 OAuth Diagnostic Tool")
    st.markdown("This tool helps diagnose OAuth redirect URI issues.")
    
    # Current URL Detection
    st.subheader("📍 Current App URL")
    
    # Try to detect current URL
    current_url = "Unknown"
    try:
        # Method 1: Check query params for any clues
        if st.query_params:
            st.write("**Query Parameters Found:**", dict(st.query_params))
        
        # Method 2: Environment variables
        env_urls = {
            'STREAMLIT_SERVER_HEADLESS_URL': os.environ.get('STREAMLIT_SERVER_HEADLESS_URL'),
            'STREAMLIT_APP_URL': os.environ.get('STREAMLIT_APP_URL'),
            'STREAMLIT_APP_NAME': os.environ.get('STREAMLIT_APP_NAME'),
        }
        
        st.write("**Environment Variables:**")
        for key, value in env_urls.items():
            st.write(f"- {key}: {value or 'Not set'}")
        
        # Method 3: Try to construct likely URL
        if os.environ.get('STREAMLIT_APP_NAME'):
            likely_url = f"https://{os.environ.get('STREAMLIT_APP_NAME')}.streamlit.app/"
            st.success(f"**Likely App URL:** `{likely_url}`")
            current_url = likely_url
        
    except Exception as e:
        st.error(f"Error detecting URL: {e}")
    
    # Credentials Check
    st.subheader("🔑 Credentials Status")
    
    credentials_info = get_google_credentials()
    if credentials_info:
        st.success("✅ Credentials found!")
        
        # Check redirect URIs in credentials
        if 'installed' in credentials_info:
            redirect_uris = credentials_info['installed'].get('redirect_uris', [])
            st.write("**Configured Redirect URIs:**")
            for uri in redirect_uris:
                st.write(f"- `{uri}`")
        
        # Check if current URL matches any configured URI
        if current_url != "Unknown":
            if 'installed' in credentials_info:
                redirect_uris = credentials_info['installed'].get('redirect_uris', [])
                if current_url in redirect_uris:
                    st.success("✅ Current URL matches configured redirect URI!")
                else:
                    st.error("❌ Current URL does NOT match any configured redirect URI!")
                    st.warning(f"**Add this to Google Cloud Console:** `{current_url}`")
    else:
        st.error("❌ No credentials found!")
    
    # OAuth Flow Test
    st.subheader("🔄 OAuth Flow Test")
    
    # Check for authorization code
    auth_code = st.query_params.get("code")
    if auth_code:
        st.success(f"✅ Authorization code received: `{auth_code[:20]}...`")
        st.info("OAuth redirect is working! The issue might be in token exchange.")
    else:
        st.info("No authorization code in URL. This is normal before authentication.")
    
    # Error parameter check
    error = st.query_params.get("error")
    if error:
        st.error(f"❌ OAuth error received: `{error}`")
        error_description = st.query_params.get("error_description", "No description")
        st.write(f"**Error Description:** {error_description}")
    
    # Manual URL Input
    st.subheader("🛠️ Manual Configuration")
    
    st.markdown("""
    **If auto-detection fails, manually configure your OAuth client:**
    
    1. **Find your exact app URL** by copying it from your browser address bar
    2. **Add it to Google Cloud Console:**
       - Go to [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials)
       - Edit your OAuth 2.0 Client ID
       - Under "Authorized redirect URIs", add your exact app URL
       - **Important:** Include the trailing slash `/`
    
    3. **Update your Streamlit secrets** with the same URL in `redirect_uris`
    """)
    
    manual_url = st.text_input(
        "Enter your app's URL manually:",
        placeholder="https://your-app.streamlit.app/",
        help="Copy this from your browser's address bar"
    )
    
    if manual_url:
        if not manual_url.endswith('/'):
            manual_url += '/'
        
        st.info(f"**Use this redirect URI:** `{manual_url}`")
        
        # Generate secrets configuration
        st.subheader("📋 Streamlit Secrets Configuration")
        st.markdown("**Add this to your Streamlit app secrets:**")
        st.code(f"""
[google_oauth]
client_id = "your-client-id.googleusercontent.com"
client_secret = "your-client-secret"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
redirect_uris = ["{manual_url}"]
        """)
    
    # Test OAuth Flow
    st.subheader("🧪 Test OAuth Flow")
    
    if st.button("Test OAuth Configuration"):
        try:
            config = ConfigManager()
            service = BaseGoogleService(config, "test", "v1", "test_scope")
            
            # Test redirect URI detection
            detected_uri = service._get_web_redirect_uri()
            st.write(f"**Detected Redirect URI:** `{detected_uri}`")
            
            # Test credentials loading
            creds = get_google_credentials()
            if creds:
                st.success("✅ Credentials loaded successfully")
            else:
                st.error("❌ Failed to load credentials")
            
        except Exception as e:
            st.error(f"Test failed: {e}")

if __name__ == "__main__":
    main() 