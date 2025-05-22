#!/usr/bin/env python3
"""
Gmail Authentication Test
========================
Test script to verify Gmail authentication is working.
"""

import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

def test_gmail_auth():
    """Test Gmail authentication."""
    load_dotenv()
    
    print("🧪 Gmail Authentication Test")
    print("=" * 40)
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/gmail.modify"
    ]
    
    token_path = "token.json"
    
    if not os.path.exists(token_path):
        print("❌ token.json not found")
        return False
    
    try:
        # Load credentials
        print("📋 Loading credentials from token.json...")
        creds = Credentials.from_authorized_user_file(token_path, scopes)
        
        # Check if expired and refresh
        if creds.expired and creds.refresh_token:
            print("🔄 Token expired, refreshing...")
            creds.refresh(Request())
            # Save refreshed token
            Path(token_path).write_text(creds.to_json())
            print("✅ Token refreshed and saved")
        
        print(f"📝 Token expiry: {creds.expiry}")
        print(f"✅ Token valid: {creds.valid}")
        print(f"📊 Scopes: {len(creds.scopes)}")
        
        # Check Gmail scope specifically
        gmail_scope = "https://www.googleapis.com/auth/gmail.modify"
        if gmail_scope in creds.scopes:
            print(f"✅ Gmail scope found: {gmail_scope}")
        else:
            print(f"❌ Gmail scope missing: {gmail_scope}")
            return False
        
        # Try to build Gmail service
        print("\n🔨 Building Gmail service...")
        gmail_service = build("gmail", "v1", credentials=creds)
        print("✅ Gmail service built successfully")
        
        # Test basic Gmail API call
        print("\n📧 Testing Gmail API access...")
        profile = gmail_service.users().getProfile(userId='me').execute()
        print(f"✅ Gmail API working! Email: {profile.get('emailAddress', 'Unknown')}")
        print(f"   Messages total: {profile.get('messagesTotal', 0)}")
        print(f"   Threads total: {profile.get('threadsTotal', 0)}")
        
        # Test drafts access
        print("\n📝 Testing drafts access...")
        drafts = gmail_service.users().drafts().list(userId='me', maxResults=1).execute()
        draft_count = len(drafts.get('drafts', []))
        print(f"✅ Drafts access working! Found {draft_count} existing drafts")
        
        print("\n🎉 ALL TESTS PASSED!")
        print("Gmail authentication and API access are working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nPossible issues:")
        print("1. Gmail API not enabled in Google Cloud Console")
        print("2. Invalid credentials")
        print("3. Expired refresh token")
        print("4. Missing permissions")
        return False

if __name__ == "__main__":
    success = test_gmail_auth()
    exit(0 if success else 1) 