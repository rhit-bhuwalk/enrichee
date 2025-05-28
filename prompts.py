def format_additional_fields(profile):
    """Format additional fields from the profile that aren't part of the core required fields."""
    # Core required fields that are handled explicitly in the prompts
    core_fields = {
        'name', 'company', 'role', 'location', 'phone', 'email', 
        'education', 'topic', 'subtopic', 'research', 'draft'
    }
    
    additional_info = []
    for key, value in profile.items():
        # Skip empty values and core fields
        if key not in core_fields and value and str(value).strip():
            # Format the field name nicely (convert underscores to spaces, capitalize)
            formatted_key = key.replace('_', ' ').title()
            additional_info.append(f"- {formatted_key}: {value}")
    
    return additional_info

def get_research_prompt(profile):
    """Return the prompt template for generating research about a person and company."""
    # Get any additional fields
    additional_fields = format_additional_fields(profile)
    additional_info_section = ""
    
    if additional_fields:
        additional_info_section = f"""
    
    ADDITIONAL PROFILE INFORMATION:
    {chr(10).join(additional_fields)}
    
    Please incorporate this additional information into your research where relevant.
    """
    
    # Handle optional location field
    location_info = profile.get('location', '')
    location_context = f" in {location_info}" if location_info else ""
    location_section = f" based in {location_info}" if location_info else ""
    
    return f"""
    Comprehensive professional research report on {profile['name']} and {profile['company']}.{additional_info_section}
    
    PART 1: INDIVIDUAL ANALYSIS
    
    Provide detailed information about {profile['name']} who works as {profile['role']} at {profile['company']}{location_context}:
    
    1. Professional Background:
       - Current responsibilities at {profile['company']}
       - Career trajectory and previous positions/companies
       - Years of experience in this role and industry
       - Key professional achievements and notable projects
       - Areas of specialization or expertise
    
    2. Educational Background:
       - Degrees, certifications, and institutions attended
       - Specialized training relevant to their current role
    
    3. Industry Presence:
       - Speaking engagements at conferences or industry events
       - Published articles, whitepapers, or research papers
       - Professional association memberships
       - LinkedIn profile details and activity
       - Other social media or professional online presence
    
    4. Professional Pain Points:
       - Common challenges faced by professionals in {profile['role']} positions
       - Industry-specific issues that might affect their daily operations
       - Regulatory or compliance concerns relevant to their position
    
    PART 2: COMPANY ANALYSIS
    
    Comprehensive information about {profile['company']}{location_section}:
    
    1. Company Overview:
       - Industry classification and primary business focus
       - Company size (employees, revenue if public)
       - Year founded and brief history
       - Market positioning and key competitors
       - Parent company or subsidiaries, if applicable
    
    2. Recent Developments:
       - Recent news or press releases (last 1-2 years)
       - Recent product launches or service expansions
       - Mergers, acquisitions, or partnerships
       - Leadership changes or restructuring
       - Financial performance indicators (if public)
    
    3. Corporate Technology Stack:
       - Known technology systems or platforms used
       - Recent technology investments or digital transformation initiatives
       - Potential technology gaps or upgrade needs
    
    4. Business Challenges:
       - Industry-specific challenges the company might be facing
       - Market pressures or competitive threats
       - Regulatory changes affecting their business model
       - Growth opportunities they might be pursuing
    
    5. Company Culture:
       - Mission and values statements
       - Corporate social responsibility initiatives
       - Work environment and company reviews
    
    PART 3: REGIONAL CONTEXT
    
    Information about the business environment{location_context}:
    
    1. Local Business Climate:
       - Major industry trends{location_context}
       - Local economic conditions
       - Regional competitors or partners
    
    2. Regional Challenges:
       - Location-specific business challenges
       - Regulatory environment unique to this region
    
    PART 4: CONNECTION POINTS
    
    1. Potential Needs:
       - Based on role, company, and industry, what services or products might be most valuable
       - Specific pain points our solution could address
       
    2. Conversation Starters:
       - Recent company news that could be referenced
       - Industry trends relevant to both their business and our offering
       - Common connections or networking opportunities
    
    Provide factual, well-researched information only. Clearly distinguish between verified facts and potential inferences. Include sources where available.
    """

def get_default_email_prompt_template():
    """Return the default email prompt template with placeholders for profile data."""
    # NOTE: This template is the single source of truth for default email generation.  
    # Any changes to the default copy should be made only here to keep the UI and
    # backend generation behaviour perfectly in-sync.
    return """ You are a top-tier growth representative writing a cold outreach email from a boutique AI consulting firm made up of three top-tier AI engineers. Our mission: bring the same AI power that only big real-estate firms can afford today to mid-sized and smaller developers.

    Your goal is to get a meeting with 
      {name} (a {role} at {company}{location_context}). You also know the following about them:
    - Contact: {contact_info}
{education_section}    - Topic: {topic} / {subtopic}
    - Research insights: {research}{additional_info_section}

    Make it personal and show that you have done your homework. Be warm and concise, with a touch of humour and persuasion. Do not make any generic statements, such as 'Your role as a {role} at {company} is important to us', or 'I hope this email finds you well'.
    Don't be overly salesy or sycophantic. Do not use em-dashes, or '-'. 

    Some things that we can do is automate some of their repetitive tasks. 

    <RULE> The body of the email should be no more than 150 words. </RULE>

    Lastly, make sure the signature is the following:

    Evan Brooks
    Sr. Engineer, DevelopIQ
    evan@developiq.com
    561.789.8905
    www.developiq.com
    """

def get_email_prompt(profile, custom_prompt=None):
    """Return the prompt template for generating a personalized cold‐outreach email.
    
    Args:
        profile: Dictionary containing profile data
        custom_prompt: Optional custom prompt template with placeholders
    """
    # Get any additional fields
    additional_fields = format_additional_fields(profile)
    additional_info_section = ""
    
    if additional_fields:
        additional_info_section = f"""
    - Additional Information:
{chr(10).join([f"      {field}" for field in additional_fields])}"""
    
    # Handle optional fields
    location_info = profile.get('location', '')
    location_context = f" in {location_info}" if location_info else ""
    
    phone_info = profile.get('phone', '')
    email_info = profile.get('email', '')
    
    # Build contact info dynamically
    contact_parts = []
    if phone_info:
        contact_parts.append(phone_info)
    if email_info:
        contact_parts.append(email_info)
    contact_info = ", ".join(contact_parts) if contact_parts else "Contact information not available"
    
    education_info = profile.get('education', '')
    education_section = f"    - Education: {education_info}\n" if education_info else ""
    
    # If a custom template is supplied, format that. Otherwise use our default
    # template (defined above) so there is only one authoritative copy.
    if custom_prompt:
        # Replace placeholders in the custom prompt
        try:
            return custom_prompt.format(
                name=profile['name'],
                role=profile['role'],
                company=profile['company'],
                location_context=location_context,
                contact_info=contact_info,
                education_section=education_section,
                topic=profile.get('topic', 'Not specified'),
                subtopic=profile.get('subtopic', 'Not specified'),
                research=profile['research'],
                additional_info_section=additional_info_section
            )
        except KeyError as e:
            # If custom prompt is missing required placeholders, fall back to default
            raise ValueError(f"Custom prompt is missing required placeholder: {e}")
    else:
        # Build prompt from the single default template defined above
        default_template = get_default_email_prompt_template()
        return default_template.format(
            name=profile['name'],
            role=profile['role'],
            company=profile['company'],
            location_context=location_context,
            contact_info=contact_info,
            education_section=education_section,
            topic=profile.get('topic', 'Not specified'),
            subtopic=profile.get('subtopic', 'Not specified'),
            research=profile['research'],
            additional_info_section=additional_info_section
        )


