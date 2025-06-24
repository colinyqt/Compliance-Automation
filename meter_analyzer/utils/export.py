import os
import datetime
from typing import List, Dict

def export_to_txt(results: List[Dict], tender_file: str) -> str:
    """Export analysis results to a text file"""
    # Create filename based on tender file
    tender_filename = os.path.basename(tender_file)
    tender_name = os.path.splitext(tender_filename)[0]
    output_filename = f"{tender_name}_meter_analysis.txt"
    
    with open(output_filename, "w") as f:
        # Write header
        f.write("SCHNEIDER ELECTRIC METER ANALYSIS REPORT\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Tender Document: {tender_filename}\n")
        f.write(f"Date of Analysis: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Total Requirements Analyzed: {len(results)}\n\n")
        
        # Rest of export implementation...
    
    return output_filename