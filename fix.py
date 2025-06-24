def fix_json_file(filepath):
    """Fix common JSON syntax errors like trailing commas"""
    import re
    
    print(f"Fixing JSON syntax in {filepath}...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix trailing commas in arrays
    content = re.sub(r',\s*]', ']', content)
    # Fix trailing commas in objects
    content = re.sub(r',\s*}', '}', content)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ JSON file fixed: {filepath}")

# Run this with your knowledge base file
fix_json_file("meter_specifications_kb_detailed.json")