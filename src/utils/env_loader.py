import os
from dotenv import load_dotenv
from .resource_path import get_resource_path
from src.utils.config_loader import get_config

def load_environment():
    """Load environment variables using a hybrid approach:
    1. First check config.yaml for API keys
    2. Fall back to .env file if it exists
    3. Finally check if environment variables are already set
    """
    env_vars_loaded = False
    required_vars = ['GOOGLE_API_KEY', 'GOOGLE_CSE_ID']
    
    # First try to load from config.yaml
    try:
        config = get_config()
                
        # Check if API keys section exists in config
        if config and 'api_keys' in config:
            for key, value in config['api_keys'].items():
                if value and value.strip():  # Only set if value is not empty
                    os.environ[key.upper()] = value
                    env_vars_loaded = True
    except Exception as e:
        print(f"Warning: Error loading from config.yaml: {str(e)}")
    
    # Then try to load from .env file if it exists
    env_path = get_resource_path('.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        env_vars_loaded = True
    
    # Check if required variables are set
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"Warning: Missing environment variables: {', '.join(missing_vars)}")
        return False
    
    return env_vars_loaded