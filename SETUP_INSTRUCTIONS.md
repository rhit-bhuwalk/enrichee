# Google Sheets OAuth Setup Instructions

This app now supports any user authenticating with their own Google Sheets account. Follow these steps to set up OAuth credentials:

## 1. Create Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Make sure billing is enabled (required for API access)

## 2. Enable Required APIs

1. Go to "APIs & Services" > "Library"
2. Search for and enable these APIs:
   - **Google Sheets API**
   - **Google Drive API** (needed to list your spreadsheets)

## 3. Create OAuth 2.0 Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth 2.0 Client IDs"
3. If prompted, configure the OAuth consent screen:
   - Choose "External" user type
   - Fill in required fields (App name, User support email, Developer contact)
   - Add test users if needed
4. For Application type, choose "Desktop application"
5. Give it a name (e.g., "LinkedIn Research App")
6. Click "Create"

## 4. Download Credentials

1. Click the download button (⬇️) next to your newly created OAuth client
2. Save the file as `credentials.json` in your project directory
3. **Never commit this file to version control!**

## 5. Run the Application

1. Start the Streamlit app: `streamlit run streamlit_app.py`
2. Click "Sign in with Google" button
3. Complete the OAuth flow in your browser
4. Select your spreadsheet and sheet
5. Start processing!

## File Structure

Your project should look like this:
```
linkedin_deep_research/
├── credentials.json        # Your OAuth credentials (don't commit!)
├── token.json             # Auto-generated token (don't commit!)
├── streamlit_app.py       # Main app
├── prompts.py            # Prompt templates
├── requirements.txt      # Dependencies
└── .env                  # API keys
```

## Security Notes

- Add `credentials.json` and `token.json` to your `.gitignore`
- The app only requests read access to your Google Drive and full access to Google Sheets
- Your credentials are stored locally and never sent to any external servers
- You can revoke access anytime in your [Google Account security settings](https://myaccount.google.com/permissions)

## Troubleshooting

**"Credentials not found" error:**
- Make sure `credentials.json` is in the same directory as `streamlit_app.py`

**"No spreadsheets found" error:**
- Check that you have spreadsheets in your Google Drive
- Try clicking "Refresh Spreadsheets"
- Verify the APIs are enabled in Google Cloud Console

**OAuth flow fails:**
- Check your internet connection
- Make sure the OAuth consent screen is properly configured
- Try deleting `token.json` and re-authenticating 

