# LinkedIn Research Pipeline - Streamlit App 🔍

A modern web interface for automated LinkedIn profile research and personalized email generation using AI.

## Features

- **🔐 User Authentication**: OAuth integration - any user can sign in with their Google account
- **📋 Dynamic Sheet Selection**: Choose any spreadsheet and sheet from your Google Drive
- **📊 Interactive Web Interface**: User-friendly Streamlit dashboard
- **🔄 Real-time Progress Tracking**: Live updates during processing
- **💰 Cost Management**: Real-time API cost tracking for both Perplexity and OpenAI
- **⚙️ Configurable Parameters**: Adjust workers, tokens, timeouts via UI
- **📈 Live Results Display**: See results as they're generated
- **🛡️ Error Handling**: Robust retry logic and error reporting
- **📋 Google Sheets Integration**: Direct read/write to your own Google Sheets
- **💾 Response Archival**: All API responses saved for audit trail

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up Google OAuth (One-time setup)

Follow the detailed instructions in [SETUP_INSTRUCTIONS.md](SETUP_INSTRUCTIONS.md) to:
1. Create a Google Cloud project
2. Enable Google Sheets and Drive APIs
3. Create OAuth 2.0 credentials
4. Download `credentials.json`

### 3. Environment Variables

Create a `.env` file with your API keys:

```env
PERPLEXITY_API_KEY=your_perplexity_key_here
OPENAI_API_KEY=your_openai_key_here
```

### 4. Run the App

```bash
streamlit run streamlit_app.py
```

## How to Use

### First Time Setup

1. **Start the app**: `streamlit run streamlit_app.py`
2. **Authenticate**: Click "Sign in with Google" and complete OAuth flow
3. **Select Spreadsheet**: Choose from your Google Drive spreadsheets
4. **Select Sheet**: Pick the specific sheet within your spreadsheet
5. **Configure**: Set your API keys and processing parameters
6. **Load & Process**: Load profiles and start processing

### Sheet Requirements

Your Google Sheet should have these columns:
- `name` - Profile name
- `research` - Will be populated with research data (can start empty)
- `draft` - Will be populated with email drafts (can start empty)
- Any other profile data columns you need

### Processing Flow

1. **Authentication**: Sign in with your Google account
2. **Sheet Selection**: Choose your spreadsheet and specific sheet
3. **Configuration**: Set API keys and processing parameters in sidebar
4. **Load Profiles**: Click "Load Profiles" to fetch data from your sheet
5. **Start Processing**: Click "Start Processing" for automated research and email generation
6. **Monitor Progress**: Watch real-time progress, cost tracking, and live results
7. **View Results**: Results automatically save back to your Google Sheet

## Configuration Options

| Setting | Description | Default |
|---------|-------------|---------|
| Max Workers | Number of concurrent threads | 25 |
| Research Max Tokens | Token limit for research calls | 800 |
| Email Max Tokens | Token limit for email generation | 350 |
| Timeout | API call timeout in seconds | 40 |
| Profile Limit | Max profiles to process (0 = all) | 0 |

## Security & Privacy

- **Local Authentication**: Your Google credentials are stored locally, never sent to external servers
- **Minimal Permissions**: App only requests read access to Drive and write access to Sheets
- **Revocable Access**: You can revoke access anytime in your Google Account settings
- **No Data Collection**: Your data stays in your Google Sheets and local machine

## Cost Tracking

The app provides detailed cost tracking:
- Real-time total cost display
- Per-provider breakdown (Perplexity/OpenAI)
- Call counts and token usage
- Costs saved to `api_cost_summary.json`

## File Structure

```
linkedin_deep_research/
├── streamlit_app.py          # Main Streamlit application
├── prompts.py               # Prompt templates
├── requirements.txt         # Python dependencies
├── SETUP_INSTRUCTIONS.md    # Detailed OAuth setup guide
├── .env                     # Environment variables (API keys)
├── credentials.json         # Google OAuth credentials (you create this)
├── token.json              # Google OAuth token (auto-generated)
├── responses/              # API response archive
│   ├── perplexity/         # Perplexity API responses
│   └── openai/             # OpenAI API responses
└── README_streamlit.md     # This file
```

## Error Handling

- **Automatic Retries**: Failed API calls are automatically retried with exponential backoff
- **Graceful Degradation**: Processing continues even if individual profiles fail
- **Error Logging**: All errors logged to `pipeline.log`
- **User Feedback**: Real-time error messages in the UI

## Performance

- **Concurrent Processing**: Parallel research and email generation
- **Batch Updates**: Efficient Google Sheets updates
- **Memory Efficient**: Processes data in configurable batches
- **Responsive UI**: Non-blocking interface during processing

## Troubleshooting

### Common Issues

1. **"Credentials not found" error**: 
   - Make sure `credentials.json` is in the same directory as `streamlit_app.py`
   - Follow [SETUP_INSTRUCTIONS.md](SETUP_INSTRUCTIONS.md) to create OAuth credentials

2. **"No spreadsheets found" error**:
   - Check that you have spreadsheets in your Google Drive
   - Try clicking "Refresh Spreadsheets"
   - Verify the APIs are enabled in Google Cloud Console

3. **OAuth flow fails**:
   - Check your internet connection
   - Make sure the OAuth consent screen is properly configured
   - Try deleting `token.json` and re-authenticating

4. **API Key Issues**:
   - Confirm API keys are correct in `.env` file or sidebar
   - Check API key permissions and quotas

## Advanced Usage

### Custom Prompts

Edit `prompts.py` to customize the research and email generation prompts:

```python
def get_research_prompt(profile):
    # Customize research prompt here
    pass

def get_email_prompt(profile):
    # Customize email prompt here
    pass
```

### Extending the App

The Streamlit app is modular and can be extended with:
- Additional AI providers
- Custom processing steps
- Enhanced visualizations
- Export functionality
- Scheduling capabilities

## What's New

### v2.0 Features
- **🔐 Universal OAuth**: Any user can now authenticate with their own Google account
- **📋 Dynamic Sheet Selection**: Choose any spreadsheet/sheet from your Google Drive
- **🔒 Enhanced Security**: Better credential management and privacy protection
- **📚 Improved Documentation**: Comprehensive setup guide and troubleshooting

## License

This project is for educational and research purposes. Please ensure compliance with LinkedIn's Terms of Service and applicable data privacy regulations. 