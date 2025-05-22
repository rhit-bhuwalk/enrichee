"""Configuration management for LinkedIn Research Pipeline
====================================================
Handles application configuration, environment variables, and logging setup.
"""

import logging
import os
import sys
from pathlib import Path
from typing import List
from dotenv import load_dotenv


class ConfigManager:
    """Manages application configuration and environment variables."""
    
    def __init__(self):
        load_dotenv()
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging for the application."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            handlers=[
                logging.FileHandler("pipeline.log"),
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.logger = logging.getLogger("pipeline")
    
    @property
    def scopes(self) -> List[str]:
        return [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/gmail.modify"
        ]
    
    @property
    def responses_dir(self) -> Path:
        resp_dir = Path("responses")
        resp_dir.mkdir(exist_ok=True)
        return resp_dir 