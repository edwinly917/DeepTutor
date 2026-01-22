
import os
import sys

# Add src to path
sys.path.append('/app')

from src.tools.web_search import web_search

try:
    print("Testing web_search with query 'latest news about AI'...")
    result = web_search("latest news about AI", verbose=True)
    print("\nSearch Result Keys:", result.keys())
    print("Answer length:", len(result.get('answer', '')))
    print("Citations count:", len(result.get('citations', [])))
    if result.get('answer'):
        print("\nAnswer Preview:", result['answer'][:100])
    else:
        print("\nNO ANSWER RETURNED")
except Exception as e:
    print(f"\nERROR: {e}")
