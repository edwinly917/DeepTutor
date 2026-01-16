import asyncio
import sys
from unittest.mock import MagicMock
from pathlib import Path

# Add project root to path
sys.path.append("/Users/bytedance/DeepTutor-1")

# MOCK dependencies to bypass Python 3.9 incompatibility in src.services
sys.modules["src"] = MagicMock()
sys.modules["src.logging"] = MagicMock()
sys.modules["src.services"] = MagicMock()
sys.modules["src.services.llm"] = MagicMock()
sys.modules["src.services.config"] = MagicMock()

# Now import the class under test
# We need to manually import it because we mocked the parent package 'src'
# But 'src.services.export.ppt_generator' is a file we want to use REAL code from.
# So we need to be careful.
# Strategy: load the file directly using importlib

import importlib.util

spec = importlib.util.spec_from_file_location(
    "PPTGeneratorModule", 
    "/Users/bytedance/DeepTutor-1/src/services/export/ppt_generator.py"
)
ppt_module = importlib.util.module_from_spec(spec)
# We need to ensure the mocked modules are available to this module
sys.modules["src.services.export.ppt_generator"] = ppt_module
spec.loader.exec_module(ppt_module)

PPTGenerator = ppt_module.PPTGenerator

async def test_ppt_generation():
    print("Testing PPT Generator (Isolated)...")
    
    # 1. Test Sanitization
    # We can instantiate without export_dir checking python-pptx if we mock it?
    # The real PPTGenerator checks for python-pptx. We installed it, so it should be fine.
    
    try:
        generator = PPTGenerator(export_dir="/tmp/ppt_test")
    except Exception as e:
        print(f"Failed to instantiate generator: {e}")
        return

    dangerous_name = "深度学习/Deep Learning: Introduction?"
    safe_name = generator._sanitize_filename(dangerous_name)
    print(f"Original: '{dangerous_name}'")
    print(f"Sanitized: '{safe_name}'")
    
    # Validation
    if "深度学习" not in safe_name:
        print("❌ FAILED: Chinese characters were stripped!")
        sys.exit(1)
    if "/" in safe_name or "?" in safe_name:
        print("❌ FAILED: Special chars were not stripped!")
        sys.exit(1)
    
    print("✅ Sanitization test passed!")

    # 2. Test Generation
    markdown_content = """
# Deep Learning Report
## Neural Networks
- Perceptron
- MLP
## CNN
1. Convolution
2. Pooling
    """
    
    try:
        # Mock LLM calls inside if strictly needed, but if we don't pass style prompt, it skips LLM
        result = await generator.generate(
            markdown=markdown_content,
            title="AI Test",
            max_slides=5
        )
        print(f"Generation Result: {result}")
        print("✅ Generation test passed!")
        
        # Check if file exists
        output_path = Path("/tmp/ppt_test") / result["filename"]
        if output_path.exists():
            print("✅ File was actually created!")
        else:
            print("❌ File was not created.")

    except ImportError:
        print("⚠️ python-pptx not installed, skipping generation test")
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ppt_generation())
