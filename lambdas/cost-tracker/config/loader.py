"""
Configuration Loader for EKS Application Start/Stop Controller
Loads configuration from config/config.yaml at runtime
"""

import os
import yaml
import json
from pathlib import Path

# Global cached config
_config = None
_config_path = None


def _find_config_file():
    """Find the config.yaml file, checking multiple possible locations."""
    # Get the directory where this file is located
    current_file = Path(__file__).resolve()
    config_dir = current_file.parent
    
    # Possible locations (in order of preference):
    # 1. config/config.yaml (relative to this file)
    # 2. ./config/config.yaml (current working directory)
    # 3. ../config/config.yaml (parent directory)
    # 4. Environment variable CONFIG_PATH
    
    possible_paths = [
        config_dir / "config.yaml",
        Path.cwd() / "config" / "config.yaml",
        Path.cwd().parent / "config" / "config.yaml",
    ]
    
    # Check environment variable
    env_config_path = os.environ.get("CONFIG_PATH")
    if env_config_path:
        possible_paths.insert(0, Path(env_config_path))
    
    for path in possible_paths:
        if path.exists() and path.is_file():
            return path
    
    # If running in Lambda, try /opt/config/config.yaml (for Lambda layers)
    lambda_path = Path("/opt/config/config.yaml")
    if lambda_path.exists():
        return lambda_path
    
    return None


def load_config():
    """
    Load configuration from config.yaml file.
    Returns cached config if already loaded.
    """
    global _config, _config_path
    
    if _config is not None:
        return _config
    
    config_file = _find_config_file()
    
    if config_file is None:
        raise FileNotFoundError(
            "config/config.yaml not found. "
            "Please ensure config/config.yaml exists or set CONFIG_PATH environment variable."
        )
    
    _config_path = config_file
    
    try:
        with open(config_file, 'r') as f:
            _config = yaml.safe_load(f)
        
        # Validate required fields
        _validate_config(_config)
        
        return _config
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing config.yaml: {e}")
    except Exception as e:
        raise RuntimeError(f"Error loading config.yaml: {e}")


def _validate_config(config):
    """Validate that required configuration fields are present."""
    required_fields = [
        ("aws", "account_id"),
        ("aws", "region"),
        ("eks", "cluster_name"),
        ("dynamodb", "table_name"),
        ("project", "name"),
    ]
    
    missing = []
    for *path, key in required_fields:
        current = config
        for p in path:
            if not isinstance(current, dict) or p not in current:
                missing.append(".".join(path + [key]))
                break
            current = current[p]
        else:
            if key not in current:
                missing.append(".".join(path + [key]))
    
    if missing:
        raise ValueError(
            f"Missing required configuration fields: {', '.join(missing)}"
        )


def get_config():
    """Get the current configuration (loads if not already loaded)."""
    return load_config()


def get_aws_account_id():
    """Get AWS account ID from config."""
    return get_config()["aws"]["account_id"]


def get_aws_region():
    """Get AWS region from config."""
    return get_config()["aws"]["region"]


def get_eks_cluster_name():
    """Get EKS cluster name from config."""
    return get_config()["eks"]["cluster_name"]


def get_dynamodb_table_name():
    """Get DynamoDB table name from config."""
    return get_config()["dynamodb"]["table_name"]


def get_s3_bucket_name():
    """Get S3 bucket name for UI from config."""
    return get_config()["s3"]["ui_bucket_name"]


def get_api_gateway_stage():
    """Get API Gateway stage name from config."""
    return get_config()["api_gateway"]["stage_name"]


def get_app_namespace_mapping():
    """Get application to namespace mapping from config."""
    return get_config().get("app_namespace_mapping", {})


def get_nodegroup_defaults():
    """Get NodeGroup defaults mapping from config."""
    return get_config().get("nodegroup_defaults", {})


def get_ec2_tag_keys():
    """Get EC2 tag key names from config."""
    tags = get_config().get("ec2_tags", {})
    return {
        "app_name": tags.get("app_name_key", "AppName"),
        "component": tags.get("component_key", "Component"),
        "shared": tags.get("shared_key", "Shared"),
    }


def get_eventbridge_schedules():
    """Get EventBridge schedule expressions from config."""
    eb = get_config().get("eventbridge", {})
    return {
        "discovery": eb.get("discovery_schedule", "rate(2 hours)"),
        "health_check": eb.get("health_check_schedule", "rate(15 minutes)"),
    }


def get_lambda_config():
    """Get Lambda configuration from config."""
    lambda_cfg = get_config().get("lambda", {})
    return {
        "runtime": lambda_cfg.get("runtime", "python3.11"),
        "memory_size": lambda_cfg.get("memory_size", 256),
        "timeout": lambda_cfg.get("timeout", 90),
    }


def get_project_name():
    """Get project name from config."""
    return get_config()["project"]["name"]


def get_ui_config():
    """Get UI configuration from config."""
    ui_cfg = get_config().get("ui", {})
    return {
        "auto_refresh_interval": ui_cfg.get("auto_refresh_interval", 30),
        "api_url": ui_cfg.get("api_url", ""),
    }


def reload_config():
    """Force reload of configuration (useful for testing)."""
    global _config, _config_path
    _config = None
    _config_path = None
    return load_config()

