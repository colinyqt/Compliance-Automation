#!/usr/bin/env python3
import sys
import os

# Change these to absolute imports
from meter_analyzer.core.analyzer import MeterAnalyzer
from meter_analyzer.utils.kb_builder import create_product_knowledge_base

def main():
    """Main entry point for the meter analyzer"""
    # Use sys.argv to parse command-line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--build-kb":
        print("SCHNEIDER ELECTRIC KNOWLEDGE BASE BUILDER")
        print("=" * 45)
        
        manuals_dir = input("Enter directory containing product manuals: ").strip()
        if not os.path.isdir(manuals_dir):
            print(f"Directory not found: {manuals_dir}")
            return 1
        
        print(f"\nFound {len([f for f in os.listdir(manuals_dir) if f.endswith('.pdf') or f.endswith('.txt')])} documents")
        print("Starting extraction process...")
        
        kb_path = create_product_knowledge_base(manuals_dir)
        print(f"\nKnowledge base created at: {kb_path}")
        return 0
    
    # Configuration - use path relative to script or from environment
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_db = os.path.join(script_dir, "meters.db")
    db_path = os.environ.get("METER_DB_PATH", default_db)
    
    # Get tender file
    tender_file = input("Enter tender document path: ").strip()
    if not tender_file:
        print("No tender file specified.")
        return 1
    
    try:
        # Run analysis
        analyzer = MeterAnalyzer(db_path)
        results = analyzer.analyze_document(tender_file)
        
        # Export results to text file
        output_file = analyzer.export_to_txt(results, tender_file)
        print(f"\nAnalysis exported to: {output_file}")
        
        print(f"\nAnalysis complete. {len(results)} requirements processed.")
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())