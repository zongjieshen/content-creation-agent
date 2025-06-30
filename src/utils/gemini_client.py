import logging
import os
from google import genai
from .env_loader import load_environment
from .tool import _init_search_service  # Import the search service initialization function

# Configure logging
logger = logging.getLogger(__name__)

# Global client variable
client = None
search_client = None

def initialize_client():
    """Initialize or reinitialize the Gemini client with the current environment variables"""
    global client
    global search_client
    try:
        # Load environment variables before initializing the client
        load_environment()
        
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            logger.error("GOOGLE_API_KEY not found. Please configure it in config.yaml or .env file.")
            client = None
        else:
            client = genai.Client(api_key=api_key)
            logger.info("Gemini client initialized successfully")

        ces_id = os.getenv('GOOGLE_CSE_ID')
        if not ces_id:
            logger.error("GOOGLE_CSE_ID not found. Please configure it in config.yaml or .env file.")
            search_client = None
        else:
            # Initialize search_client using the _init_search_service function from tool.py
            search_client = _init_search_service()
            logger.info("Search client initialized successfully")
            return True
        
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {str(e)}")
        client = None
        return False

def get_client():
    """Get the Gemini client instance, initializing it if necessary"""
    global client
    if client is None:
        initialize_client()
    return client

def get_search_client():
    """Get the search client instance, initializing it if necessary"""
    global search_client
    if search_client is None:
        initialize_client()
    return search_client


# Initialize the client when the module is imported
initialize_client()