#!/bin/bash

# LinkedIn Research Pipeline - Streamlit App Launcher
# ===================================================

echo "🔍 LinkedIn Research Pipeline - Streamlit App"
echo "=============================================="
echo ""

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "✅ Virtual environment detected: $(basename $VIRTUAL_ENV)"
else
    echo "⚠️  No virtual environment detected. Consider activating one."
fi

# Check if dependencies are installed
echo "📦 Checking dependencies..."
python -c "import streamlit, pandas, litellm, google.oauth2.credentials" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ All required packages are installed"
else
    echo "❌ Missing dependencies. Installing..."
    pip install -r requirements.txt
fi

# Check if .env file exists
if [ -f ".env" ]; then
    echo "✅ Environment file found"
else
    echo "⚠️  .env file not found. Make sure to set your API keys."
fi

echo ""
echo "🚀 Starting Streamlit app..."
echo "📱 The app will open in your browser at: http://localhost:8501"
echo "⏹️  Press Ctrl+C to stop the app"
echo ""

# Start the Streamlit app
streamlit run streamlit_app.py 