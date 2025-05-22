# LinkedIn Research Pipeline - Deployment Setup

This guide explains how to set up the LinkedIn Research Pipeline for both local development and web deployment (Streamlit Cloud).

## Google Cloud Setup (Required for Both)

1. **Create a Google Cloud Project:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one

2. **Enable Required APIs:**
   - [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
   - [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   - [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)

3. **Configure OAuth Consent Screen:**
   - Go to [OAuth Consent Screen](https://console.cloud.google.com/apis/credentials/consent)
   - Choose "External" user type (unless you have a Google Workspace)
   - Fill in required fields (App name, User support email, Developer contact)
   - Add required scopes:
     - `https://www.googleapis.com/auth/spreadsheets`
     - `https://www.googleapis.com/auth/drive.readonly`
     - `https://www.googleapis.com/auth/gmail.modify`

4. **Create OAuth 2.0 Credentials:**
   - Go to [Credentials](https://console.cloud.google.com/apis/credentials)
   - Click "Create Credentials" → "OAuth 2.0 Client ID"
   - Choose "Desktop application" as application type
   - Download the credentials JSON file

## Local Development Setup

1. **Save Credentials File:**
   - Rename the downloaded file to `credentials.json`
   - Place it in your project root directory
   - Add `credentials.json` to your `.gitignore` file

2. **Environment Variables:**
   Create a `.env` file with your API keys:
   ```bash
   PERPLEXITY_API_KEY=your_perplexity_key_here
   OPENAI_API_KEY=your_openai_key_here
   ```

3. **Run the App:**
   ```bash
   streamlit run streamlit_app.py
   ```

## Web Deployment Setup (Streamlit Cloud)

### Option 1: Using Streamlit Secrets (Recommended)

1. **Deploy to Streamlit Cloud:**
   - Push your code to GitHub (excluding `credentials.json`)
   - Connect your GitHub repo to [Streamlit Cloud](https://share.streamlit.io/)

2. **Configure Secrets:**
   In your Streamlit Cloud app settings, add the following secrets:

   ```toml
   # API Keys
   PERPLEXITY_API_KEY = "your_perplexity_key_here"
   OPENAI_API_KEY = "your_openai_key_here"

   # Google OAuth Credentials
   [google_oauth]
   client_id = "your-client-id.googleusercontent.com"
   client_secret = "your-client-secret"
   redirect_uris = ["http://localhost"]
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   ```

   **To get these values from your credentials.json:**
   ```json
   {
     "installed": {
       "client_id": "copy this value",
       "client_secret": "copy this value",
       "redirect_uris": ["http://localhost"],
       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
       "token_uri": "https://oauth2.googleapis.com/token",
       "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
     }
   }
   ```

### Option 2: Using Environment Variables

Alternatively, you can set these as environment variables in Streamlit Cloud:

```bash
PERPLEXITY_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
GOOGLE_CLIENT_ID=your-client-id.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
```

## Authentication Flow

### Local Development
- The app will automatically open a browser window for Google OAuth
- Complete the authentication in your browser
- Credentials are saved locally in `token.json`

### Web Deployment
- The app will show a "Click here to authenticate" link
- Follow the link to complete Google OAuth
- Copy the authorization code and paste it back in the app
- Credentials are stored in the browser session

## Troubleshooting

### Common Issues

1. **"Credentials not found" error:**
   - Ensure `credentials.json` exists (local) or secrets are configured (web)
   - Check that OAuth credentials are correctly formatted

2. **"API not enabled" error:**
   - Verify all three APIs are enabled in Google Cloud Console
   - Wait a few minutes after enabling APIs

3. **"Scope not granted" error:**
   - Check OAuth consent screen configuration
   - Ensure all required scopes are added
   - Try re-authentication

4. **"Access blocked" error:**
   - Your OAuth consent screen might need verification for production use
   - For testing, add your Gmail address as a test user in OAuth consent screen

### Getting Help

- Check the `pipeline.log` file for detailed error messages
- Ensure your Google Cloud project has billing enabled (required for some APIs)
- Make sure you're using the correct Google account that has access to your spreadsheets

## Security Notes

- Never commit `credentials.json` to version control
- Use Streamlit secrets for web deployment
- Regularly rotate your API keys
- Only grant minimum required permissions 