# LinkedIn Research Pipeline 🔍

A modern web application for automated LinkedIn profile research and personalized email generation using AI. Built with Streamlit and integrated with Google Workspace services.

## 🚀 Quick Start

### Local Development

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Test Your Setup** (recommended)
   ```bash
   python test_setup.py
   ```

3. **Set up Google OAuth** (one-time setup)
   - Download OAuth 2.0 credentials from Google Cloud Console
   - Save as `credentials.json` in project root
   - See detailed guide: [`deployment_setup.md`](deployment_setup.md)

4. **Configure API Keys**
   Create a `.env` file:
   ```env
   PERPLEXITY_API_KEY=your_perplexity_key_here
   OPENAI_API_KEY=your_openai_key_here
   ```

5. **Run the Application**
   ```bash
   streamlit run streamlit_app.py
   # or
   ./run_app.sh
   ```

### Web Deployment (Streamlit Cloud)

1. **Deploy to Streamlit Cloud**
   - Push your code to GitHub (excluding `credentials.json`)
   - Connect your repo to [Streamlit Cloud](https://share.streamlit.io/)

2. **Configure Secrets**
   In your Streamlit Cloud app settings, add:
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

📖 **Complete Setup Guide**: [`deployment_setup.md`](deployment_setup.md)

## ✨ Key Features

- **🔐 Universal OAuth Authentication** - Works both locally and on the web
- **📋 Dynamic Sheet Selection** - Choose any spreadsheet and sheet from your Google Drive
- **🤖 AI-Powered Research** - Automated LinkedIn profile research using Perplexity AI
- **✉️ Email Generation** - Personalized cold outreach emails with OpenAI GPT-4o-mini
- **💰 Real-time Cost Tracking** - Monitor API usage and costs across all providers
- **📧 Gmail Integration** - Automatically create email drafts in your Gmail account
- **🔄 Email Regeneration** - Regenerate individual or bulk emails with custom prompts
- **⚙️ Configurable Processing** - Adjust workers, tokens, timeouts via UI
- **🌐 Web & Local Support** - Run locally or deploy to Streamlit Cloud

## 📁 Repository Structure

```
linkedin_deep_research/
├── streamlit_app.py          # Main Streamlit application
├── config.py                # Configuration management
├── google_services.py       # Google Sheets & Gmail integration  
├── ai_service.py           # AI model integrations
├── profile_processor.py    # Main processing pipeline
├── cost_tracking.py        # Cost estimation & tracking
├── prompts.py              # AI prompt templates
├── requirements.txt        # Python dependencies  
├── deployment_setup.md     # 📖 Setup guide for local & web
├── test_setup.py          # 🧪 Setup verification script
├── run_app.sh             # Application startup script
├── docs/                  # 📚 Legacy documentation
└── responses/             # API response archive (gitignored)
```

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [`deployment_setup.md`](deployment_setup.md) | **🎯 Primary setup guide** - Local development & web deployment |
| [`test_setup.py`](test_setup.py) | **🧪 Setup verification** - Test your configuration before running |
| [`docs/README_streamlit.md`](docs/README_streamlit.md) | **Complete usage guide** - Features, setup, troubleshooting |
| [`docs/SETUP_INSTRUCTIONS.md`](docs/SETUP_INSTRUCTIONS.md) | **OAuth configuration** - Step-by-step Google Cloud setup |
| [`docs/README_email_regeneration.md`](docs/README_email_regeneration.md) | **Email regeneration** - Bulk operations and custom prompts |
| [`docs/README_cost_estimation.md`](docs/README_cost_estimation.md) | **Cost tracking** - Real-time estimation and monitoring |

## 🔧 Configuration

### Required APIs
- **Google Sheets API** - Read/write spreadsheet data
- **Google Drive API** - List and access spreadsheets
- **Gmail API** - Create email drafts
- **Perplexity API** - AI-powered research
- **OpenAI API** - Email generation

### Sheet Requirements
Your Google Sheet should include these columns:
- `name` - Profile name *(required)*
- `company` - Company name *(required)*
- `role` - Job title *(required)*
- `research` - AI research results *(auto-populated)*
- `draft` - Generated email drafts *(auto-populated)*
- Additional profile data columns as needed *(optional)*

## 🛡️ Security & Privacy

- **Local Authentication** - Credentials stored locally, never sent externally
- **Minimal Permissions** - Only requests necessary Google API scopes
- **No Data Collection** - Your data stays in Google Sheets and local machine
- **Revocable Access** - Remove access anytime in Google Account settings
- **Web-Safe Deployment** - Secure credential management for cloud deployment

## 🔄 Workflow

1. **Authenticate** with your Google account
2. **Select** your spreadsheet and sheet
3. **Configure** API keys and processing parameters
4. **Load** profiles from your Google Sheet
5. **Process** profiles for research and email generation
6. **Monitor** real-time progress and costs
7. **Create** Gmail drafts for outreach
8. **Regenerate** emails as needed with custom prompts

## 💰 Cost Management

- Real-time cost tracking across all API providers
- Upfront cost estimation before processing
- Per-profile and per-provider cost breakdowns
- Built-in safeguards and transparent pricing

## 🆘 Support

### Quick Troubleshooting
- **Setup issues**: Run `python test_setup.py` to diagnose problems
- **Authentication issues**: See [`deployment_setup.md`](deployment_setup.md)
- **App usage questions**: See [`docs/README_streamlit.md`](docs/README_streamlit.md)
- **Email features**: See [`docs/README_email_regeneration.md`](docs/README_email_regeneration.md)
- **Cost questions**: See [`docs/README_cost_estimation.md`](docs/README_cost_estimation.md)

### Common Issues
1. **"Credentials not found"** - 
   - **Local**: Ensure `credentials.json` is in project root
   - **Web**: Configure Streamlit secrets with OAuth credentials
2. **"No spreadsheets found"** - Check Google Drive access and API enablement
3. **API key errors** - Verify keys in `.env` file, Streamlit secrets, or sidebar configuration
4. **Web authentication issues** - Follow the manual OAuth flow with authorization codes

## 🌐 Deployment Options

### Local Development
- ✅ Full OAuth flow with browser popup
- ✅ Credentials saved locally
- ✅ `.env` file for API keys
- ✅ Full featured development environment

### Streamlit Cloud
- ✅ Manual OAuth flow with authorization codes
- ✅ Streamlit secrets for secure credential storage
- ✅ Environment variables for API keys
- ✅ Public web access

## 🏗️ Development

### Key Components
- `streamlit_app.py` - Main UI and application orchestration
- `google_services.py` - Google API authentication and operations
- `ai_service.py` - AI model integrations (Perplexity, OpenAI)
- `profile_processor.py` - Main processing pipeline with progress tracking
- `cost_tracking.py` - Real-time cost estimation and tracking
- `config.py` - Configuration management and logging

### Extension Points
- Add new AI providers in `ai_service.py`
- Customize prompts in `prompts.py`
- Extend UI with additional Streamlit components
- Add new Google Workspace services in `google_services.py`

## 📄 License

This project is for educational and research purposes. Please ensure compliance with:
- LinkedIn's Terms of Service
- Applicable data privacy regulations
- Google API Terms of Service
- OpenAI and Perplexity usage policies

---

**Ready to get started?** 

- 🏠 **Local Development**: [`deployment_setup.md`](deployment_setup.md) → Local Development Setup
- 🌐 **Web Deployment**: [`deployment_setup.md`](deployment_setup.md) → Web Deployment Setup  
- 🧪 **Test Setup**: Run `python test_setup.py` to verify your configuration
