import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append("/Users/bytedance/DeepTutor-1")

from src.services.export.ppt_generator import PPTGenerator
from src.services.config import get_ppt_config

async def test_ppt_generation():
    print("Testing PPT Generator...")
    
    # 0. Test PPT Config Loading
    print("\n=== Testing PPT Config ===")
    try:
        ppt_config = get_ppt_config()
        print(f"  Model: {ppt_config.model or '(using default LLM)'}")
        print(f"  API Key: {'***' if ppt_config.api_key else '(using default LLM)'}")
        print(f"  Base URL: {ppt_config.base_url or '(using default LLM)'}")
        print(f"  Binding: {ppt_config.binding}")
        print(f"  Temperature: {ppt_config.temperature}")
        print(f"  Max Tokens: {ppt_config.max_tokens}")
        print(f"  Max Slides: {ppt_config.max_slides}")
        print("✅ PPT config loaded successfully!")
    except Exception as e:
        print(f"❌ PPT config failed: {e}")
    
    # 1. Test Sanitization
    print("\n=== Testing Filename Sanitization ===")
    generator = PPTGenerator(export_dir="/tmp/ppt_test")
    
    dangerous_name = "深度学习/Deep Learning: Introduction?"
    safe_name = generator._sanitize_filename(dangerous_name)
    print(f"Original: '{dangerous_name}'")
    print(f"Sanitized: '{safe_name}'")
    
    assert "深度学习" in safe_name, "Chinese characters were stripped!"
    assert "/" not in safe_name, "Slashes should be removed"
    assert "?" not in safe_name, "Question marks should be removed"
    
    print("✅ Sanitization test passed!")

    # 2. Test Generation (Mocking python-pptx if needed, but we check if it runs)
    print("\n=== Testing PPT Generation ===")
    markdown_content = """
# Deep Learning
## Introduction
- Neural Networks
- Backpropagation

## Advanced Topics
1. CNN
2. RNN
3. Transformers
    """
    
    try:
        result = await generator.generate(
            markdown=markdown_content,
            title="AI Test",
            max_slides=5
        )
        print(f"Generation Result: {result}")
        print("✅ Generation test passed!")
    except ImportError:
        print("⚠ python-pptx not installed, skipping generation test")
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        # raise e

if __name__ == "__main__":
    asyncio.run(test_ppt_generation())

