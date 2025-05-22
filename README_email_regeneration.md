# Email Regeneration Feature

This document describes the new email regeneration functionality added to the LinkedIn Research Pipeline application.

## Overview

The email regeneration feature allows users to:
- View existing email drafts in a dedicated management interface
- Regenerate individual emails with new AI-generated content
- Perform bulk regeneration operations on multiple profiles
- Copy email content for manual use
- **NEW: Customize email prompts** to match your specific outreach style

## Custom Email Prompts

### What are Custom Email Prompts?
Custom email prompts allow you to modify the instructions given to the AI model when generating emails. Instead of using the default template, you can create your own prompt that reflects your company's voice, style, and specific value propositions.

### How to Use Custom Prompts

1. **Enable Custom Prompts**
   - Go to the sidebar in the app
   - Expand the "✉️ Custom Email Prompt" section
   - Check "Use Custom Email Prompt"

2. **Edit Your Prompt**
   - The text area will populate with the default prompt as a starting point
   - Modify the prompt to match your needs
   - Use the provided placeholders to insert dynamic data

3. **Available Placeholders**
   Use these placeholders in your custom prompt:
   - `{name}` - Contact's name
   - `{role}` - Contact's job title
   - `{company}` - Company name
   - `{location_context}` - Location info (e.g., " in New York")
   - `{contact_info}` - Phone and email info
   - `{education_section}` - Education details
   - `{topic}` - Topic field from spreadsheet
   - `{subtopic}` - Subtopic field from spreadsheet
   - `{research}` - AI-generated research insights
   - `{additional_info_section}` - Any additional fields from spreadsheet

4. **Test Your Prompt**
   - Go to the "📧 Email Management" tab
   - Use the "🧪 Test Custom Email Prompt" expander
   - Fill in sample data and preview the generated prompt
   - This shows exactly what will be sent to the AI model

5. **Validation**
   - The app automatically validates your prompt
   - Ensures all required placeholders are present
   - Shows validation errors if the prompt is invalid

### Example Custom Prompt

```
You are writing a cold outreach email from [Your Company Name], a [your value proposition].

Write a personalized email to {name}, who is a {role} at {company}{location_context}.

Key information about them:
- Contact: {contact_info}
{education_section}- Topic: {topic} / {subtopic}  
- Research insights: {research}{additional_info_section}

Instructions:
- Keep it under 150 words
- Focus on [your specific value proposition]
- Include a clear call-to-action for [your specific goal]
- Be professional but friendly
- Reference specific details from the research

Email signature:
[Your Name]
[Your Title]
[Your Contact Info]
```

### Tips for Custom Prompts

1. **Be Specific**: The more specific your instructions, the better the AI output
2. **Include Examples**: You can include example phrases or tones in your prompt
3. **Test Thoroughly**: Use the test feature with various profile types
4. **Iterate**: Refine your prompt based on the generated results
5. **Keep Placeholders**: Always include required placeholders like `{name}`, `{company}`, `{role}`, and `{research}`

### Benefits of Custom Prompts

- **Brand Consistency**: Ensure all emails match your company's voice
- **Industry Specific**: Tailor prompts for specific industries or use cases  
- **Personalization**: Include your unique value propositions
- **A/B Testing**: Create different prompts for different campaigns
- **Compliance**: Add specific compliance language if required

## How to Use

### 1. Access Email Management

After completing the research and email generation process:

1. Navigate to the **"📧 Email Management"** tab in the application
2. The system will automatically detect profiles with existing email drafts
3. You'll see a summary of how many email drafts are available

### 2. Individual Email Management

In the **"📧 Email Preview"** tab:

- **View Emails**: Each profile with an email draft is shown in an expandable section
- **Regenerate Email**: Click the "🔄 Regenerate Email" button to generate a new email using the latest AI model
- **Copy Email**: Click the "📋 Copy Email" button to display the email content in a code block for easy copying

### 3. Bulk Operations

In the **"🔄 Bulk Actions"** tab:

- **Select Profiles**: Use the multiselect dropdown to choose profiles for bulk regeneration
- **Preview Selection**: Click "📊 Preview Selected" to see which profiles you've selected
- **Bulk Regenerate**: Click the bulk regenerate button to regenerate emails for all selected profiles
- **Cost Estimation**: The system provides a rough cost estimate for bulk operations

## Technical Details

### Backend Implementation

The regeneration feature includes:

- **`regenerate_email()` method** in `ProfileProcessor` class that:
  - Calls the AI service to generate a new email
  - Updates the local dataframe in session state
  - Updates the Google Sheets document automatically
  - Provides error handling and logging

### UI Components

- **Expandable sections** for each profile showing current email content
- **Progress tracking** for bulk operations
- **Cost estimation** for bulk regenerations
- **Success/error feedback** with clear status messages
- **Automatic page refresh** to show updated content

### Data Persistence

- All regenerated emails are automatically saved to Google Sheets
- Local session state is updated in real-time
- Changes are immediately available across all application tabs

## Requirements

To use the email regeneration feature:

1. **Authentication**: Must be authenticated with Google (both Sheets and Gmail APIs)
2. **API Keys**: OpenAI API key must be configured in the sidebar
3. **Data**: Must have profiles loaded with existing email drafts
4. **Sheet Selection**: Must have a spreadsheet and sheet selected

## Error Handling

The system handles common errors gracefully:

- **API timeouts**: Retries with exponential backoff
- **Missing data**: Clear warnings when profiles or configuration are missing
- **Permission issues**: Helpful error messages for authentication problems
- **Rate limiting**: Built-in retry mechanisms for API calls

## Cost Considerations

- Each email regeneration uses the OpenAI API (gpt-4o-mini model)
- Bulk operations provide cost estimates before execution
- All API usage is tracked and displayed in the sidebar cost tracking section

## Tips for Best Results

1. **Review existing emails** before regenerating to understand what needs improvement
2. **Use individual regeneration** first to test changes before bulk operations
3. **Check the research data** is complete and accurate before regenerating emails
4. **Monitor API costs** using the built-in cost tracking features

## Troubleshooting

### Common Issues

1. **"No profile data loaded"**: Navigate to the Research & Processing tab first to load data
2. **"OpenAI API key required"**: Add your OpenAI API key in the sidebar configuration
3. **"Please select a spreadsheet"**: Ensure you've selected both a spreadsheet and sheet
4. **Regeneration fails**: Check your internet connection and API key validity

### Getting Help

- Check the application logs in `pipeline.log` for detailed error information
- Verify all required APIs are enabled in your Google Cloud Console
- Ensure your API keys have sufficient quota/credits 

## Best Practices

1. **Test First**: Always test regeneration on a small subset before bulk processing
2. **Backup Data**: Ensure your Google Sheets data is backed up
3. **Monitor Costs**: Use the cost estimation feature for budget planning
4. **Review Output**: Manually review regenerated emails for quality
5. **Custom Prompts**: Iterate on your custom prompts to improve results
6. **API Limits**: Be mindful of OpenAI API rate limits for bulk operations

## Integration with Gmail

After regenerating emails, you can:
1. Navigate to the "✉️ Gmail Drafts" tab
2. Create Gmail drafts from your regenerated emails
3. Edit drafts directly in Gmail before sending

This creates a complete workflow from research → email generation → regeneration → Gmail drafts → sending. 