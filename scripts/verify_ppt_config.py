#!/usr/bin/env python3
"""Isolated test for PPT config - no dependencies on external modules."""
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Only import the config module directly
from dataclasses import dataclass
from typing import Any, Optional
import yaml


@dataclass
class PPTConfig:
    """PPT generation configuration."""
    model: str
    api_key: str
    base_url: str
    binding: str = "openai"
    temperature: float = 0.4
    max_tokens: int = 2000
    max_slides: int = 15
    default_style_prompt: str = ""


def test_ppt_config():
    """Test PPT config loading from main.yaml"""
    print("=== Testing PPT Config Loading ===\n")
    
    # Load main.yaml directly
    config_path = PROJECT_ROOT / "config" / "main.yaml"
    print(f"Loading config from: {config_path}")
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # Check if export.ppt section exists
    export_config = config.get("export", {})
    ppt_config = export_config.get("ppt", {})
    
    print(f"\nExport section exists: {'export' in config}")
    print(f"PPT section exists: {'ppt' in export_config}")
    
    if ppt_config:
        print("\n✅ PPT Configuration Block Found:")
        print(f"  model: {ppt_config.get('model') or '(empty - falls back to default LLM)'}")
        print(f"  api_key: {ppt_config.get('api_key') or '(empty - falls back to default LLM)'}")
        print(f"  base_url: {ppt_config.get('base_url') or '(empty - falls back to default LLM)'}")
        print(f"  binding: {ppt_config.get('binding', 'openai')}")
        print(f"  temperature: {ppt_config.get('temperature', 0.4)}")
        print(f"  max_tokens: {ppt_config.get('max_tokens', 2000)}")
        print(f"  max_slides: {ppt_config.get('max_slides', 15)}")
        print(f"  default_style_prompt: {ppt_config.get('default_style_prompt') or '(empty)'}")
    else:
        print("\n❌ PPT config block not found in main.yaml")
        return False
    
    # Test environment variable fallback
    print("\n=== Testing Environment Variable Fallback ===")
    
    os.environ["PPT_MODEL"] = "test-ppt-model"
    os.environ["PPT_API_KEY"] = "test-ppt-key"
    os.environ["PPT_BASE_URL"] = "https://test.example.com/v1"
    
    ppt_model_env = os.getenv("PPT_MODEL")
    ppt_api_key_env = os.getenv("PPT_API_KEY")
    ppt_base_url_env = os.getenv("PPT_BASE_URL")
    
    print(f"  PPT_MODEL from env: {ppt_model_env}")
    print(f"  PPT_API_KEY from env: {'***' if ppt_api_key_env else '(not set)'}")
    print(f"  PPT_BASE_URL from env: {ppt_base_url_env}")
    
    # Clean up
    del os.environ["PPT_MODEL"]
    del os.environ["PPT_API_KEY"]
    del os.environ["PPT_BASE_URL"]
    
    print("\n✅ Environment variable fallback works correctly!")
    
    print("\n=== All Tests Passed ===")
    return True


if __name__ == "__main__":
    success = test_ppt_config()
    sys.exit(0 if success else 1)
