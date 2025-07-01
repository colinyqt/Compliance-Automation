# main.py
#!/usr/bin/env python3
"""
YAML Prompt Engine with Auto-Discovery Database Integration
Main entry point for the Compliance Automation system
"""

import asyncio
import os
import sys
from pathlib import Path
from core.prompt_engine import PromptEngine

def main():
    print("🚀 YAML Prompt Engine with Auto-Discovery")
    print("=" * 50)
    
    # Initialize engine
    try:
        engine = PromptEngine()
        print("✅ Prompt engine initialized")
    except Exception as e:
        print(f"❌ Failed to initialize engine: {e}")
        return 1
    
    # List available prompts
    prompts_dir = Path("prompts")
    if not prompts_dir.exists():
        print("❌ Prompts directory not found!")
        return 1
    
    yaml_files = list(prompts_dir.glob("*.yaml"))
    if not yaml_files:
        print("❌ No YAML prompt files found in prompts/ directory")
        return 1
    
    print(f"\n📋 Available prompts ({len(yaml_files)} found):")
    for i, yaml_file in enumerate(yaml_files, 1):
        print(f"  {i}. {yaml_file.stem}")
    
    # User selection
    try:
        choice = input(f"\nSelect prompt (1-{len(yaml_files)}) or press Enter for prompt 1: ").strip()
        if not choice:
            choice = "1"
        
        selected_idx = int(choice) - 1
        if selected_idx < 0 or selected_idx >= len(yaml_files):
            raise ValueError("Invalid selection")
        
        selected_prompt = yaml_files[selected_idx]
        print(f"🎯 Selected: {selected_prompt.stem}")
        
    except (ValueError, KeyboardInterrupt):
        print("❌ Invalid selection or cancelled")
        return 1
    
    # Run the analysis
    try:
        print(f"\n🔄 Running analysis with {selected_prompt.name}...")
        result = asyncio.run(engine.run_prompt(str(selected_prompt)))
        
        if result.get('success'):
            print("✅ Analysis completed successfully!")
            if result.get('output_files'):
                print("\n📄 Generated files:")
                for file_path in result['output_files']:
                    print(f"  - {file_path}")
        else:
            print(f"❌ Analysis failed: {result.get('error', 'Unknown error')}")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️ Analysis cancelled by user")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())