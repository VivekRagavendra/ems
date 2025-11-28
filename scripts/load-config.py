#!/usr/bin/env python3
"""
Load configuration from config/config.yaml and output as JSON
Used by scripts and Terraform/Terragrunt to read configuration
"""

import sys
import os
import json
import yaml
from pathlib import Path

def find_config_file():
    """Find the config.yaml file."""
    # Get the directory where this script is located
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    
    # Possible locations
    possible_paths = [
        project_root / "config" / "config.yaml",
        Path.cwd() / "config" / "config.yaml",
        Path.cwd().parent / "config" / "config.yaml",
    ]
    
    # Check environment variable
    env_config_path = Path(os.environ.get("CONFIG_PATH", ""))
    if env_config_path.exists():
        possible_paths.insert(0, env_config_path)
    
    for path in possible_paths:
        if path.exists() and path.is_file():
            return path
    
    return None

def load_config():
    """Load and return configuration as dict."""
    import os
    
    config_file = find_config_file()
    
    if config_file is None:
        print("Error: config/config.yaml not found", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config.yaml: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    config = load_config()
    print(json.dumps(config, indent=2))

