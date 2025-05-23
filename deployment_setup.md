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
   - Choose "External" (unless you have a Google Workspace)
   - Fill in app name, user support email, and developer contact information
   - Add the following scopes:
     ```
     https://www.googleapis.com/auth/spreadsheets
     https://www.googleapis.com/auth/drive.readonly
     https://www.googleapis.com/auth/gmail.modify
     ```

4. **Create OAuth 2.0 Credentials:**
   - Go to [Credentials](https://console.cloud.google.com/apis/credentials)
   - Click "Create Credentials" → "OAuth 2.0 Client ID"
   - Choose "Desktop application"
   - Download the JSON file (this contains your `client_id`, `client_secret`, etc.)

## Local Development Setup

1. **Save OAuth Credentials:**
   - Save the downloaded JSON file as `credentials.json` in your project root
   - The file should look like:
   ```json
   {
     "installed": {
       "client_id": "your-client-id",
       "client_secret": "your-client-secret",
       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
       "token_uri": "https://oauth2.googleapis.com/token",
       "redirect_uris": ["http://localhost"]
     }
   }
   ```

2. **Run the app:**
   ```bash
   streamlit run streamlit_app.py
   ```

3. **First-time authentication:**
   - The app will automatically open a browser for Google OAuth
   - Grant permissions for both Google Sheets and Gmail
   - Credentials will be saved locally for future use

## Web Deployment (Streamlit Cloud)

### Option 1: Using Streamlit Secrets (Recommended)

1. **Deploy to Streamlit Cloud:**
   - Connect your GitHub repository to Streamlit Cloud
   - Deploy the app

2. **Configure Secrets:**
   - In your Streamlit Cloud app settings, go to "Secrets"
   - Add the following TOML configuration:
   ```toml
   [google_oauth]
   client_id = "37409654206-p1tkrm5gtsq09mq3ncljnmavfllt9588.apps.googleusercontent.com"
   client_secret = "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"
   redirect_uris = ["http://localhost"]
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   project_id = "developiq-456318"
   ```

3. **Authentication Flow:**
   - The app will detect it's running in a web environment
   - It will show an authentication link instead of opening a browser
   - Click the link, complete Google OAuth, and copy the authorization code
   - Paste the code back in the app to complete authentication

### Option 2: Environment Variables

Alternatively, you can set environment variables in your deployment platform:

```bash
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URIS=["http://localhost"]
```

## Troubleshooting

### Common Issues

1. **"could not locate runnable browser" error:**
   - This indicates the app is trying to use local browser authentication in a web environment
   - Check the "Debug Info" section in the app to see environment detection
   - Ensure your secrets are properly configured

2. **"Authentication failed" in web deployment:**
   - Verify your OAuth credentials are correctly added to Streamlit secrets
   - Check that all required APIs are enabled in Google Cloud Console
   - Ensure OAuth consent screen is properly configured

3. **Missing scopes error:**
   - Make sure all three scopes are added to your OAuth consent screen:
     - `https://www.googleapis.com/auth/spreadsheets`
     - `https://www.googleapis.com/auth/drive.readonly`
     - `https://www.googleapis.com/auth/gmail.modify`

4. **Environment detection issues:**
   - Check the debug information in the app's authentication section
   - The app should detect web deployment automatically
   - If not, you may need to set a manual environment variable

### Testing Your Setup

1. **Local testing:**
   ```bash
   python test_setup.py
   ```

2. **Environment detection testing:**
   ```bash
   python test_env_detection.py
   ```

3. **Google authentication testing:**
   ```bash
   python test_gmail_auth.py
   ```

### Environment Detection Logic

The app detects web deployment using these indicators:

- **Streamlit Cloud:** `STREAMLIT_SHARING_MODE` or `STREAMLIT_CLOUD` environment variables
- **Heroku:** `DYNO` environment variable
- **General cloud:** `KUBERNETES_SERVICE_HOST`, `CLOUD_RUN_JOB` environment variables
- **Secrets presence:** Having `google_oauth` in Streamlit secrets
- **Display indicators:** Missing `DISPLAY` or `BROWSER` environment variables
- **File indicators:** Missing `credentials.json` but having secrets

## API Keys Setup

Don't forget to configure your AI service API keys:

**For local development (.env file):**
```env
PERPLEXITY_API_KEY=your_perplexity_key
OPENAI_API_KEY=your_openai_key
```

**For web deployment (Streamlit secrets):**
```toml
PERPLEXITY_API_KEY = "your_perplexity_key"
OPENAI_API_KEY = "your_openai_key"
```

## Security Notes

- Never commit `credentials.json` or `.env` files to your repository
- Use Streamlit secrets or environment variables for web deployments
- Regularly rotate your API keys and OAuth credentials
- Review OAuth scopes to ensure you only request necessary permissions

## Support

If you encounter issues:

1. Check the app's debug information
2. Review the logs in your deployment platform
3. Verify all APIs are enabled in Google Cloud Console
4. Ensure OAuth consent screen is properly configured
5. Test the environment detection with the provided scripts 