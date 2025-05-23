# Google OAuth Setup Instructions

This app now supports OAuth authentication with Google for Sheets, Drive, and Gmail access. Follow these steps to set up OAuth credentials:

## 1. Create Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Make sure billing is enabled (required for API access)

## 2. Enable Required APIs

1. Go to "APIs & Services" > "Library"
2. Search for and enable these APIs:
   - **Google Sheets API** (required for reading/writing spreadsheet data)
   - **Google Drive API** (required to list your spreadsheets)
   - **Gmail API** (required to create email drafts)

## 3. Create OAuth 2.0 Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth 2.0 Client IDs"
3. If prompted, configure the OAuth consent screen:
   - Choose "External" user type
   - Fill in required fields (App name, User support email, Developer contact)
   - Add scopes: `../auth/spreadsheets`, `../auth/drive.readonly`, `../auth/gmail.modify`
   - Add test users if needed (only required if app is in testing mode)
4. For Application type, choose "Desktop application"
5. Give it a name (e.g., "LinkedIn Research App")
6. Click "Create"

## 4. Download Credentials

1. Click the download button (⬇️) next to your newly created OAuth client
2. Save the file as `credentials.json` in your project directory
3. **Never commit this file to version control!**

## 5. Run the Application

1. Start the Streamlit app: `streamlit run streamlit_app.py`
2. Click "Start Authentication" button
3. Complete the OAuth flow in your browser
4. Grant permissions for:
   - Google Sheets (read and modify your spreadsheets)
   - Google Drive (view your Google Drive files)
   - Gmail (create drafts in your Gmail account)
5. Select your spreadsheet and sheet
6. Complete processing, then use the Gmail Drafts tab to create drafts!

## Permissions Explained

The app requests these OAuth scopes:

- **`auth/spreadsheets`**: Read and write access to your Google Sheets
  - Used to: Load profile data, save research results and email drafts
  
- **`auth/drive.readonly`**: Read-only access to list your Google Drive files
  - Used to: Show you a list of your spreadsheets to choose from
  
- **`auth/gmail.modify`**: Create, read, update, and delete Gmail drafts and labels
  - Used to: Create email drafts from generated content
  - **Note**: This does NOT allow sending emails or reading your existing emails

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
- Your credentials are stored locally and never sent to any external servers
- Gmail access is limited to draft creation only - no email reading or sending
- You can revoke access anytime in your [Google Account security settings](https://myaccount.google.com/permissions)
- Email drafts are created in your Gmail account and remain under your control

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

**Gmail authentication fails:**
- Verify Gmail API is enabled in Google Cloud Console
- Check that Gmail scope is included in your OAuth consent screen
- Re-authenticate to ensure all permissions are granted
- Ensure your Google account has Gmail enabled

**Gmail drafts not creating:**
- Check that you have a valid Gmail account (not just Google Workspace)
- Verify the email content is properly formatted
- Check the app logs for specific error messages

