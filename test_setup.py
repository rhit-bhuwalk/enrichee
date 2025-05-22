#!/usr/bin/env python3
"""Test Script for LinkedIn Research Pipeline Setup
==================================================
This script helps verify your Google Cloud setup before running the main app.
"""

import os
import json
import sys
from pathlib import Path

def check_local_credentials():
    """Check if local credentials.json file exists and is valid."""
    print("🔍 Checking local credentials...")
    
    creds_path = "credentials.json"
    if not os.path.exists(creds_path):
        print("❌ credentials.json not found")
        print("💡 For local development, download OAuth 2.0 credentials from Google Cloud Console")
        return False
    
    try:
        with open(creds_path, 'r') as f:
            creds = json.load(f)
        
        # Check structure
        if 'installed' in creds:
            client_info = creds['installed']
        elif 'web' in creds:
            client_info = creds['web']
        else:
            print("❌ Invalid credentials format")
            return False
        
        required_fields = ['client_id', 'client_secret', 'auth_uri', 'token_uri']
        missing = [field for field in required_fields if field not in client_info]
        
        if missing:
            print(f"❌ Missing required fields: {missing}")
            return False
        
        print("✅ credentials.json is valid")
        return True
        
    except json.JSONDecodeError:
        print("❌ credentials.json is not valid JSON")
        return False
    except Exception as e:
        print(f"❌ Error reading credentials: {e}")
        return False

def check_streamlit_secrets():
    """Check if Streamlit secrets are configured (for web deployment)."""
    print("🔍 Checking Streamlit secrets...")
    
    try:
        import streamlit as st
        
        if hasattr(st, 'secrets') and 'google_oauth' in st.secrets:
            oauth_secrets = st.secrets['google_oauth']
            required_fields = ['client_id', 'client_secret']
            missing = [field for field in required_fields if field not in oauth_secrets]
            
            if missing:
                print(f"❌ Missing required Streamlit secrets: {missing}")
                return False
            
            print("✅ Streamlit secrets configured")
            return True
        else:
            print("⚠️ Streamlit secrets not found (OK for local development)")
            return False
            
    except ImportError:
        print("⚠️ Streamlit not available (not running in Streamlit context)")
        return False
    except Exception as e:
        print(f"⚠️ Could not check Streamlit secrets: {e}")
        return False

def check_environment_variables():
    """Check if required environment variables are set."""
    print("🔍 Checking environment variables...")
    
    required_vars = ['PERPLEXITY_API_KEY', 'OPENAI_API_KEY']
    missing = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print(f"❌ Missing environment variables: {missing}")
        print("💡 Create a .env file or set these as environment variables")
        return False
    
    print("✅ All required environment variables are set")
    return True

def check_dependencies():
    """Check if required Python packages are installed."""
    print("🔍 Checking Python dependencies...")
    
    required_packages = [
        'streamlit',
        'pandas', 
        'google.auth',
        'google_auth_oauthlib',
        'googleapiclient',
        'litellm'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('.', '_') if '.' in package else package)
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"❌ Missing packages: {missing}")
        print("💡 Run: pip install -r requirements.txt")
        return False
    
    print("✅ All required packages are installed")
    return True

def print_setup_summary():
    """Print setup instructions summary."""
    print("\n📋 Setup Summary:")
    print("================")
    print("\n🔧 **Required Setup Steps:**")
    print("1. Google Cloud Console:")
    print("   - Enable Google Sheets API, Gmail API, Drive API")
    print("   - Configure OAuth consent screen")
    print("   - Create OAuth 2.0 credentials")
    print("\n2. Local Development:")
    print("   - Save credentials as 'credentials.json'") 
    print("   - Create .env file with API keys")
    print("\n3. Web Deployment:")
    print("   - Configure Streamlit secrets with OAuth credentials")
    print("   - Set API keys in secrets or environment variables")
    print("\n📖 **Detailed Instructions:** See deployment_setup.md")

def main():
    """Run all setup checks."""
    print("🧪 LinkedIn Research Pipeline - Setup Test")
    print("==========================================\n")
    
    checks = [
        ("Dependencies", check_dependencies),
        ("Environment Variables", check_environment_variables),
        ("Local Credentials", check_local_credentials),
        ("Streamlit Secrets", check_streamlit_secrets),
    ]
    
    results = {}
    for name, check_func in checks:
        results[name] = check_func()
        print()
    
    print("📊 **Test Results:**")
    print("===================")
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name}: {status}")
    
    # Overall assessment
    print("\n🎯 **Overall Assessment:**")
    if results["Dependencies"]:
        if results["Environment Variables"]:
            if results["Local Credentials"] or results["Streamlit Secrets"]:
                print("✅ **Ready to run!** Your setup appears to be complete.")
            else:
                print("⚠️ **Missing credentials** - Set up either local credentials.json or Streamlit secrets")
        else:
            print("⚠️ **Missing API keys** - Add PERPLEXITY_API_KEY and OPENAI_API_KEY")
    else:
        print("❌ **Missing dependencies** - Install required packages first")
    
    print_setup_summary()

if __name__ == "__main__":
    main() 