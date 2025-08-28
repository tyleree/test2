#!/usr/bin/env python3
"""
Script to replace all 'settings.' references with 'config.' in the app directory.
"""

import os
import glob

def replace_in_file(filepath):
    """Replace settings. with config. in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'settings.' in content:
            new_content = content.replace('settings.', 'config.')
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"✅ Updated {filepath}")
            return True
        return False
    except Exception as e:
        print(f"❌ Error updating {filepath}: {e}")
        return False

def main():
    """Replace settings. with config. in all Python files in app/."""
    app_dir = os.path.join(os.getcwd(), 'app')
    py_files = glob.glob(os.path.join(app_dir, '*.py'))
    
    updated_count = 0
    for filepath in py_files:
        if replace_in_file(filepath):
            updated_count += 1
    
    print(f"\n🎯 Updated {updated_count} files")
    
    # Also fix the cache.py embedding model reference
    cache_py = os.path.join(app_dir, 'cache.py')
    if os.path.exists(cache_py):
        with open(cache_py, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Fix the specific embedding model reference
        if 'config.cache_embedding_model' in content:
            new_content = content.replace(
                'config.cache_embedding_model',
                'getattr(config, "cache_embedding_model", "all-MiniLM-L6-v2")'
            )
            with open(cache_py, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print("✅ Fixed cache.py embedding model reference")

if __name__ == '__main__':
    main()
