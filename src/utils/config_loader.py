import yaml
import os
from functools import lru_cache
from .resource_path import get_resource_path

@lru_cache(maxsize=1)
def get_config():
    """Load configuration from config.yaml file."""
    try:
        if os.environ.get('DOCKER_ENV') == 'true':
            config_path = '/app/config/config.yaml'
        else:
            config_path = get_resource_path("config.yaml")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return {}  # Return empty dict on error