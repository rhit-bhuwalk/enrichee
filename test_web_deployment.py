#!/usr/bin/env python3
"""
Web Deployment Test for LinkedIn Research Pipeline
=================================================
Test script to verify web deployment configuration and OAuth setup.
"""

import os
import streamlit as st
from google_services import get_google_credentials, BaseGoogleService
from config import ConfigManager

def test_web_deployment():
    """Test web deployment configuration."""
    st.title("🌐 Web Deployment Test")
    st.markdown("This page helps diagnose web deployment issues.")
    
    # Environment Detection
    st.subheader("🔍 Environment Detection")
    
    web_indicators = {
        'STREAMLIT_SHARING_MODE': 'STREAMLIT_SHARING_MODE' in os.environ,
        'STREAMLIT_CLOUD': 'STREAMLIT_CLOUD' in os.environ,
        'DYNO (Heroku)': 'DYNO' in os.environ,
        'KUBERNETES_SERVICE_HOST': 'KUBERNETES_SERVICE_HOST' in os.environ,
        'CLOUD_RUN_JOB': 'CLOUD_RUN_JOB' in os.environ,
        'Has google_oauth secrets': _has_secrets_safely(),
        'No DISPLAY': os.environ.get('DISPLAY') is None,
        'No BROWSER': os.environ.get('BROWSER') is None,
        'No credentials.json': not os.path.exists("credentials.json"),
    }
    
    for indicator, detected in web_indicators.items():
        status = "✅" if detected else "❌"
        st.write(f"{status} **{indicator}:** {detected}")
    
    is_web = any(web_indicators.values())
    st.write(f"**Overall Detection:** {'🌐 Web Deployment' if is_web else '💻 Local Development'}")
    
    # Credentials Test
    st.subheader("🔑 Credentials Test")
    
    credentials_info = get_google_credentials()
    if credentials_info:
        st.success("✅ Credentials found!")
        
        # Show credential structure (without sensitive data)
        if 'installed' in credentials_info:
            client_config = credentials_info['installed']
            st.write("**Credential Structure:** ✅ Proper OAuth format")
            st.write(f"**Client ID:** {client_config.get('client_id', 'Missing')[:20]}...")
            st.write(f"**Auth URI:** {client_config.get('auth_uri', 'Missing')}")
            st.write(f"**Token URI:** {client_config.get('token_uri', 'Missing')}")
            st.write(f"**Redirect URIs:** {client_config.get('redirect_uris', 'Missing')}")
        else:
            st.warning("⚠️ Credentials found but structure may be incorrect")
            st.write("Expected 'installed' key in credentials")
    else:
        st.error("❌ No credentials found!")
        
        if is_web:
            st.info("**For web deployment, add to Streamlit secrets:**")
            st.code("""
[google_oauth]
client_id = "your-client-id.googleusercontent.com"
client_secret = "your-client-secret"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
redirect_uris = ["https://your-app.streamlit.app/"]
            """)
        else:
            st.info("**For local development, create credentials.json file**")
    
    # Redirect URI Test
    st.subheader("🔗 Redirect URI Test")
    
    try:
        config = ConfigManager()
        service = BaseGoogleService(config, "test", "v1", "test_scope")
        redirect_uri = service._get_web_redirect_uri()
        
        st.write(f"**Detected Redirect URI:** `{redirect_uri}`")
        
        if is_web:
            st.info("**Important:** Make sure this redirect URI is added to your Google Cloud OAuth client!")
            st.markdown(f"""
            **Steps to add redirect URI:**
            1. Go to [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials)
            2. Edit your OAuth 2.0 Client ID
            3. Add this redirect URI: `{redirect_uri}`
            4. Save changes
            """)
        
    except Exception as e:
        st.error(f"Error getting redirect URI: {e}")
    
    # OAuth Flow Test
    st.subheader("🔄 OAuth Flow Test")
    
    # Check for authorization code in URL
    auth_code = st.query_params.get("code")
    if auth_code:
        st.success(f"✅ Authorization code received: {auth_code[:20]}...")
        st.info("OAuth redirect is working! The app should now be able to complete authentication.")
    else:
        st.info("No authorization code in URL. This is normal before authentication.")
    
    # Environment Variables
    st.subheader("🌍 Environment Variables")
    
    env_vars = [
        'STREAMLIT_SHARING_MODE', 'STREAMLIT_CLOUD', 'DYNO',
        'KUBERNETES_SERVICE_HOST', 'CLOUD_RUN_JOB',
        'DISPLAY', 'BROWSER', 'HOME', 'USER'
    ]
    
    for var in env_vars:
        value = os.environ.get(var, 'Not set')
        st.write(f"**{var}:** {value}")
    
    # Troubleshooting Guide
    st.subheader("🛠️ Troubleshooting Guide")
    
    with st.expander("Common Issues and Solutions", expanded=True):
        st.markdown("""
        **Issue: "redirect_uri_mismatch" error**
        - Solution: Add your app's URL to Google Cloud OAuth client redirect URIs
        - Format: `https://your-app.streamlit.app/` (note the trailing slash)
        
        **Issue: "Credentials not found"**
        - Solution: Configure Streamlit secrets with your OAuth credentials
        - Go to app settings → Secrets → Add [google_oauth] section
        
        **Issue: "Authentication failed"**
        - Check that all required APIs are enabled in Google Cloud Console
        - Verify OAuth consent screen is properly configured
        - Ensure all required scopes are added
        
        **Issue: App works locally but not on web**
        - Different OAuth flow needed for web vs local
        - Check redirect URI configuration
        - Verify secrets are properly configured
        """)

def _has_secrets_safely() -> bool:
    """Safely check if Google OAuth secrets exist without raising exceptions."""
    try:
        return hasattr(st, 'secrets') and 'google_oauth' in st.secrets
    except Exception:
        return False

if __name__ == "__main__":
    test_web_deployment() 