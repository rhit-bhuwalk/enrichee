#!/usr/bin/env python3
"""
OAuth Redirect URI Fix Script
============================
This script helps identify and fix OAuth redirect URI issues.
"""

import os
import sys
import streamlit as st
from google_services import get_google_credentials, BaseGoogleService
from config import ConfigManager

def main():
    st.title("🔧 OAuth Redirect URI Fix for Enrichee App")
    st.markdown("This tool helps you fix the 'Missing required parameter: redirect_uri' error for both local and web deployment.")
    
    # Step 1: Detect current environment
    st.subheader("📍 Step 1: Detect Current Environment")
    
    # Check if running on Streamlit Cloud
    is_streamlit_cloud = 'STREAMLIT_SHARING_MODE' in os.environ or 'STREAMLIT_CLOUD' in os.environ
    
    if is_streamlit_cloud:
        st.success("✅ **Running on Streamlit Cloud:** `https://enrichee.streamlit.app/`")
        current_url = "https://enrichee.streamlit.app/"
    else:
        # Try to detect local port
        detected_port = None
        try:
            if hasattr(st, 'get_option'):
                detected_port = st.get_option('server.port')
        except Exception:
            pass
        
        if detected_port:
            current_url = f"http://localhost:{detected_port}/"
            st.success(f"✅ **Running locally:** `{current_url}`")
        else:
            st.info("🔍 **Local development detected** - Please check your browser address bar for the exact port.")
            current_url = "http://localhost:8506/"  # Default based on your usage
    
    # Step 2: Required redirect URIs
    st.subheader("🔗 Step 2: Required Redirect URIs")
    
    required_uris = [
        "https://enrichee.streamlit.app/",  # Web deployment
        "http://localhost:8501/",          # Default local port
        "http://localhost:8506/",          # Your current local port
    ]
    
    st.markdown("**Your Google Cloud OAuth client needs these redirect URIs:**")
    for uri in required_uris:
        if uri == current_url:
            st.success(f"✅ `{uri}` (current environment)")
        else:
            st.write(f"- `{uri}`")
    
    # Step 3: Check current OAuth configuration
    st.subheader("🔑 Step 3: Check Current OAuth Configuration")
    
    credentials_info = get_google_credentials()
    if credentials_info:
        st.success("✅ OAuth credentials found!")
        
        if 'installed' in credentials_info:
            client_config = credentials_info['installed']
            current_redirect_uris = client_config.get('redirect_uris', [])
            
            st.write("**Current redirect URIs in your configuration:**")
            missing_uris = []
            
            for uri in required_uris:
                if uri in current_redirect_uris:
                    st.success(f"✅ `{uri}` (configured)")
                else:
                    st.error(f"❌ `{uri}` (missing)")
                    missing_uris.append(uri)
            
            # Show any extra URIs
            for uri in current_redirect_uris:
                if uri not in required_uris:
                    st.info(f"ℹ️ `{uri}` (extra - can be removed if not needed)")
            
            if missing_uris:
                st.error(f"❌ **Problem found:** {len(missing_uris)} redirect URI(s) are missing!")
            else:
                st.success("✅ All required redirect URIs are configured!")
        else:
            st.warning("⚠️ Unexpected credential format")
    else:
        st.error("❌ No OAuth credentials found!")
    
    # Step 4: Instructions to fix
    st.subheader("🛠️ Step 4: Fix Your Google Cloud OAuth Client")
    
    st.markdown(f"""
    **Follow these steps to fix the redirect URI issue:**
    
    1. **Go to Google Cloud Console:**
       - Open [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials)
       - Sign in with your Google account
    
    2. **Find your OAuth 2.0 Client ID:**
       - Look for your OAuth 2.0 Client ID in the credentials list
       - Click the edit button (pencil icon) next to it
    
    3. **Update Authorized redirect URIs:**
       - Scroll down to "Authorized redirect URIs"
       - **Add ALL of these URIs** (click "ADD URI" for each):
         - `https://enrichee.streamlit.app/`
         - `http://localhost:8501/`
         - `http://localhost:8506/`
       - **Important:** Make sure each includes the trailing slash `/`
    
    4. **Save changes:**
       - Click "SAVE" at the bottom of the page
       - Wait for the changes to propagate (usually immediate)
    
    5. **Test both environments:**
       - Test your local app: `http://localhost:8506/`
       - Test your web app: `https://enrichee.streamlit.app/`
    """)
    
    # Step 5: Streamlit Secrets Configuration
    st.subheader("🔐 Step 5: Streamlit Secrets Configuration")
    
    st.markdown("""
    **For web deployment, make sure your Streamlit secrets include the correct redirect URIs:**
    
    Go to your app settings in Streamlit Cloud and add/update your secrets:
    """)
    
    st.code(f"""
[google_oauth]
client_id = "your-client-id.googleusercontent.com"
client_secret = "your-client-secret"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
redirect_uris = [
    "https://enrichee.streamlit.app/",
    "http://localhost:8501/",
    "http://localhost:8506/"
]
    """)
    
    # Step 6: Test OAuth flow
    st.subheader("🧪 Step 6: Test OAuth Configuration")
    
    if st.button("Test OAuth Flow"):
        try:
            config = ConfigManager()
            service = BaseGoogleService(config, "test", "v1", "test_scope")
            
            # Test redirect URI detection
            detected_uri = service._get_web_redirect_uri()
            st.write(f"**App detected redirect URI:** `{detected_uri}`")
            
            if detected_uri in required_uris:
                st.success("✅ Redirect URI detection is working correctly!")
            else:
                st.warning(f"⚠️ Unexpected redirect URI detected: `{detected_uri}`")
            
            # Test credentials loading
            creds = get_google_credentials()
            if creds:
                st.success("✅ Credentials loaded successfully")
                
                # Check if the required URIs are in the credentials
                if 'installed' in creds:
                    redirect_uris = creds['installed'].get('redirect_uris', [])
                    missing = [uri for uri in required_uris if uri not in redirect_uris]
                    
                    if not missing:
                        st.success("✅ All required URLs are configured in the credentials!")
                    else:
                        st.error(f"❌ Missing redirect URIs: {missing}")
                        st.info("You need to update your Google Cloud OAuth client configuration")
            else:
                st.error("❌ Failed to load credentials")
            
        except Exception as e:
            st.error(f"Test failed: {e}")
    
    # Step 7: Additional troubleshooting
    st.subheader("🔍 Step 7: Additional Troubleshooting")
    
    with st.expander("Common Issues and Solutions", expanded=False):
        st.markdown(f"""
        **Issue: "redirect_uri_mismatch" error**
        - **Solution:** Make sure ALL required URIs are added to your Google Cloud OAuth client
        - **Required URIs:** 
          - `https://enrichee.streamlit.app/` (for web)
          - `http://localhost:8501/` (default local)
          - `http://localhost:8506/` (your current local)
        
        **Issue: "invalid_request" error**
        - **Solution:** Verify your client_id and client_secret are correct
        - **Check:** Make sure your OAuth client is for "Desktop application" type
        
        **Issue: "Access blocked: Authorization Error"**
        - **Solution:** Check your OAuth consent screen configuration
        - **Check:** Make sure required scopes are added and consent screen is configured
        
        **Issue: Works locally but not on web (or vice versa)**
        - **Solution:** Both environments need their respective redirect URIs
        - **Local:** `http://localhost:XXXX/`
        - **Web:** `https://enrichee.streamlit.app/`
        
        **Issue: Streamlit secrets not working**
        - **Solution:** Make sure secrets are properly formatted in TOML
        - **Check:** Verify the redirect_uris array includes all required URLs
        """)
    
    # Current environment summary
    st.subheader("📋 Current Environment Summary")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Current Environment:**")
        if is_streamlit_cloud:
            st.success("🌐 Streamlit Cloud")
            st.write("URL: `https://enrichee.streamlit.app/`")
        else:
            st.info("💻 Local Development")
            st.write(f"URL: `{current_url}`")
    
    with col2:
        st.markdown("**Required Action:**")
        if credentials_info and 'installed' in credentials_info:
            current_redirect_uris = credentials_info['installed'].get('redirect_uris', [])
            missing = [uri for uri in required_uris if uri not in current_redirect_uris]
            
            if missing:
                st.error(f"❌ Add {len(missing)} redirect URI(s)")
                for uri in missing:
                    st.write(f"- `{uri}`")
            else:
                st.success("✅ All URIs configured")
        else:
            st.warning("⚠️ Check credentials")

if __name__ == "__main__":
    main() 