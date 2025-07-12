import yaml
from functools import lru_cache
from .resource_path import get_resource_path

@lru_cache(maxsize=1)  # Cache the config to avoid re-reading it multiple times
def get_config():
    """Load configuration from config.yaml file."""
    try:
        config_path = get_resource_path("config.yaml")
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return {}  # Return empty dict on error