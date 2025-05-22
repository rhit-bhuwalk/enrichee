#!/usr/bin/env python3
"""Environment Detection Test for LinkedIn Research Pipeline
=========================================================
Simple test to verify environment detection logic works correctly.
"""

import os
import streamlit as st

def test_environment_detection():
    """Test environment detection logic."""
    print("🔍 Environment Detection Test")
    print("=" * 50)
    
    # Check various environment indicators
    web_indicators = {
        'STREAMLIT_SHARING_MODE': 'STREAMLIT_SHARING_MODE' in os.environ,
        'STREAMLIT_CLOUD': 'STREAMLIT_CLOUD' in os.environ,
        'DYNO (Heroku)': 'DYNO' in os.environ,
        'KUBERNETES_SERVICE_HOST': 'KUBERNETES_SERVICE_HOST' in os.environ,
        'CLOUD_RUN_JOB': 'CLOUD_RUN_JOB' in os.environ,
        'No DISPLAY': os.environ.get('DISPLAY') is None,
        'No BROWSER': os.environ.get('BROWSER') is None,
        'No credentials.json': not os.path.exists("credentials.json"),
    }
    
    # Try to check for secrets (only works in Streamlit context)
    try:
        has_secrets = hasattr(st, 'secrets') and 'google_oauth' in st.secrets
        web_indicators['Has google_oauth secrets'] = has_secrets
    except:
        web_indicators['Has google_oauth secrets'] = "N/A (not in Streamlit context)"
    
    print("\n📋 Environment Indicators:")
    for indicator, detected in web_indicators.items():
        status = "✅" if detected is True else "❌" if detected is False else "❓"
        print(f"{status} {indicator}: {detected}")
    
    # Overall determination
    boolean_indicators = [v for v in web_indicators.values() if isinstance(v, bool)]
    is_web = any(boolean_indicators)
    
    print(f"\n🎯 **Overall Detection:** {'🌐 Web Deployment' if is_web else '💻 Local Development'}")
    
    # Show some helpful environment variables
    print(f"\n🌍 Key Environment Variables:")
    env_vars = ['HOME', 'USER', 'PATH', 'PYTHONPATH', 'STREAMLIT_SERVER_PORT']
    for var in env_vars:
        value = os.environ.get(var, 'Not set')
        print(f"  {var}: {value[:100]}{'...' if len(value) > 100 else ''}")
    
    return is_web

if __name__ == "__main__":
    test_environment_detection() 