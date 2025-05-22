#!/usr/bin/env python3
"""
Authentication Checker for LinkedIn Research Pipeline
=====================================================
This script helps debug authentication issues, especially with Gmail permissions.
"""

import json
import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

def check_auth_status():
    """Check current authentication status and scopes."""
    load_dotenv()
    
    print("🔍 LinkedIn Research Pipeline - Authentication Checker")
    print("=" * 60)
    
    # Check for credentials.json
    creds_path = os.getenv("CREDENTIALS_PATH", "credentials.json")
    print(f"\n📋 Checking credentials file: {creds_path}")
    
    if os.path.exists(creds_path):
        print("✅ credentials.json found")
        try:
            with open(creds_path, 'r') as f:
                creds_data = json.load(f)
                print(f"   Client ID: {creds_data.get('installed', {}).get('client_id', 'Not found')[:20]}...")
                print(f"   Project ID: {creds_data.get('installed', {}).get('project_id', 'Not found')}")
        except Exception as e:
            print(f"❌ Error reading credentials: {e}")
    else:
        print("❌ credentials.json not found")
        print("   💡 Download OAuth 2.0 credentials from Google Cloud Console")
    
    # Check token.json
    token_path = "token.json"
    print(f"\n🔑 Checking stored token: {token_path}")
    
    if os.path.exists(token_path):
        print("✅ token.json found")
        try:
            with open(token_path, 'r') as f:
                token_data = json.load(f)
                
            # Load credentials to check scopes
            scopes_needed = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.readonly", 
                "https://www.googleapis.com/auth/gmail.modify"
            ]
            
            creds = Credentials.from_authorized_user_file(token_path, scopes_needed)
            
            print(f"   Expiry: {creds.expiry}")
            print(f"   Valid: {creds.valid}")
            print(f"   Expired: {creds.expired}")
            
            print("\n📝 Authorized Scopes:")
            for scope in creds.scopes:
                if "sheets" in scope:
                    print(f"   ✅ {scope} (Google Sheets)")
                elif "drive" in scope:
                    print(f"   ✅ {scope} (Google Drive)")
                elif "gmail" in scope:
                    print(f"   ✅ {scope} (Gmail)")
                else:
                    print(f"   ℹ️  {scope}")
            
            print("\n🎯 Required Scopes Check:")
            for scope in scopes_needed:
                if scope in creds.scopes:
                    service_name = "Gmail" if "gmail" in scope else "Sheets" if "sheets" in scope else "Drive"
                    print(f"   ✅ {service_name}: {scope}")
                else:
                    service_name = "Gmail" if "gmail" in scope else "Sheets" if "sheets" in scope else "Drive"
                    print(f"   ❌ {service_name}: {scope} - MISSING!")
            
            # Check if Gmail scope is missing
            gmail_scope = "https://www.googleapis.com/auth/gmail.modify"
            if gmail_scope not in creds.scopes:
                print(f"\n🚨 ISSUE FOUND: Gmail scope is missing!")
                print(f"   Missing scope: {gmail_scope}")
                print(f"   This is why you're only seeing Sheets authentication.")
            else:
                print(f"\n✅ GREAT: Gmail scope is present!")
                print(f"   Found scope: {gmail_scope}")
                print(f"   Gmail integration should work.")
                
        except Exception as e:
            print(f"❌ Error reading token: {e}")
    else:
        print("❌ token.json not found - not authenticated yet")
    
    print("\n🛠️  Next Steps:")
    if not os.path.exists(creds_path):
        print("1. Create OAuth 2.0 credentials in Google Cloud Console")
        print("2. Download credentials.json")
        print("3. Enable both Google Sheets API and Gmail API")
    elif not os.path.exists(token_path):
        print("1. Run the Streamlit app and authenticate")
        print("2. Make sure Gmail API is enabled in Google Cloud Console")
    else:
        # Check if Gmail scope is missing
        try:
            creds = Credentials.from_authorized_user_file(token_path, [])
            gmail_scope = "https://www.googleapis.com/auth/gmail.modify"
            print(f"\nℹ️  Final verification - Gmail scope check:")
            print(f"   Looking for: {gmail_scope}")
            print(f"   Available scopes: {len(creds.scopes)} total")
            
            if gmail_scope not in creds.scopes:
                print("❌ PROBLEM: Gmail scope is missing from token")
                print("1. Delete token.json file")
                print("2. Enable Gmail API in Google Cloud Console")
                print("3. Re-authenticate in the Streamlit app")
                print("4. When prompted, grant Gmail permissions")
            else:
                print("✅ CONFIRMED: Gmail scope is in the token")
                print("   All required scopes are present.")
                print("   Gmail API should work properly.")
                
                # Additional checks
                print("\n🔧 If Gmail still doesn't work in the app, possible causes:")
                print("1. Gmail API not enabled in Google Cloud Console")
                print("2. OAuth consent screen missing Gmail scopes")
                print("3. API quota limits exceeded")
                print("4. App verification required (if external users)")
                print("5. Check the Streamlit app logs for specific Gmail errors")
                print("6. Try running the app with debug logging enabled")
        except Exception as e:
            print(f"❌ Error checking scopes: {e}")
            print("1. Delete token.json and re-authenticate")
    
    print("\n🔗 Useful Links:")
    print("• Enable Gmail API: https://console.cloud.google.com/apis/library/gmail.googleapis.com")
    print("• Enable Sheets API: https://console.cloud.google.com/apis/library/sheets.googleapis.com")
    print("• OAuth Consent Screen: https://console.cloud.google.com/apis/credentials/consent")
    print("• Create Credentials: https://console.cloud.google.com/apis/credentials")

if __name__ == "__main__":
    check_auth_status() 