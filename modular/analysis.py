import json
import os
import re
import time
import ollama
from typing import List, Dict, Any

from comparison import MeterSpecificationComparison

class MeterSpecificationAnalyzer:
    def __init__(self):
        pass

    def compare_requirements_with_specs(self, requirements: List[str], meter_specs: Dict, model_number: str) -> Dict:
        """
        Compare requirements with meter specs and return compliance analysis.
        """
        # ...existing logic from _compare_requirements_with_specs...
        # Call self.post_process_compliance_logic(result, requirements) at the end
        pass

    def _compare_requirements_chunked(self, requirements: List[str], meter_specs: Dict, model_number: str, chunk_size: int) -> Dict:
        """Compare requirements in chunks to handle large requirement sets"""
        
        print(f"🔄 Processing {len(requirements)} requirements in chunks of {chunk_size}")
        
        # Split requirements into chunks
        chunks = [requirements[i:i + chunk_size] for i in range(0, len(requirements), chunk_size)]
        print(f"📦 Created {len(chunks)} chunks")
        
        all_compliance_items = []
        chunk_results = []
        
        for i, chunk in enumerate(chunks, 1):
            print(f"\n📦 Processing chunk {i}/{len(chunks)} ({len(chunk)} requirements)...")
            
            # Process this chunk
            chunk_result = self._compare_requirements_with_specs_single_chunk(chunk, meter_specs, model_number, i)
            
            if "error" in chunk_result:
                print(f"❌ Error in chunk {i}: {chunk_result['error']}")
                continue
            
            chunk_compliance = chunk_result.get("compliance_analysis", [])
            all_compliance_items.extend(chunk_compliance)
            chunk_results.append(chunk_result)
            
            print(f"✅ Chunk {i} completed: {len(chunk_compliance)} items analyzed")
            
            # Small delay between chunks to avoid overwhelming the AI
            if i < len(chunks):
                time.sleep(2)
        
        print(f"\n📊 Chunked processing complete: {len(all_compliance_items)} total items analyzed")
        
        # Combine results
        combined_result = {
            "compliance_analysis": all_compliance_items,
            "overall_compliance": True,
            "areas_exceeding_requirements": [],
            "potential_issues": []
        }
        
        # Calculate overall compliance
        compliant_count = sum(1 for item in all_compliance_items if item.get("complies", False))
        total_count = len(all_compliance_items)
        compliance_rate = compliant_count / total_count if total_count > 0 else 0
        
        combined_result["overall_compliance"] = compliance_rate >= 0.8  # 80% compliance threshold
        
        # Combine areas exceeding requirements - FIX: Handle string lists properly
        all_exceeding = []
        for chunk_result in chunk_results:
            exceeding_areas = chunk_result.get("areas_exceeding_requirements", [])
            if isinstance(exceeding_areas, list):
                all_exceeding.extend(exceeding_areas)
        
        # Remove duplicates by converting to set and back (only works with strings)
        combined_result["areas_exceeding_requirements"] = self._safe_remove_duplicates(all_exceeding)
        
        # Combine potential issues - FIX: Handle string lists properly
        all_issues = []
        for chunk_result in chunk_results:
            issues = chunk_result.get("potential_issues", [])
            if isinstance(issues, list):
                all_issues.extend(issues)

        # Remove duplicates by converting to set and back (only works with strings)
        combined_result["potential_issues"] = self._safe_remove_duplicates(all_issues)

        return combined_result

    def _compare_requirements_with_specs_single_chunk(self, requirements: List[str], meter_specs: Dict, model_number: str, chunk_num: int) -> Dict:
        """Process a single chunk of requirements"""
        
        # Format meter specs for the AI prompt
        specs_formatted = self._format_meter_specs_for_prompt(meter_specs)
        reqs_formatted = '\n'.join(f"{i+1}. {req}" for i, req in enumerate(requirements))

        # Build prompt for this chunk
        comparison_prompt = f"""
### TASK
Analyze ALL {len(requirements)} requirements in this chunk against meter specifications.

### REQUIREMENTS TO ANALYZE (Chunk {chunk_num})
{reqs_formatted}

### METER SPECIFICATIONS
Model: {model_number}
{specs_formatted}

### OUTPUT
Valid JSON with analysis for ALL {len(requirements)} requirements:

{{
  "compliance_analysis": [
    {{"requirement": "requirement text", "spec_value": "meter spec", "complies": true/false, "justification": "reason"}}
  ],
  "overall_compliance": true/false,
  "areas_exceeding_requirements": [],
  "potential_issues": []
}}

Analyze ALL {len(requirements)} requirements. Do not skip any.
"""
    
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": comparison_prompt}],
                options={
                    "temperature": 0.1,
                    "timeout": 120.0,
                    "num_ctx": 8192,
                    "num_predict": 4096
                }
            )
            
            ai_content = response['message']['content']
            result = self._extract_and_repair_json(ai_content)
            
            return result
            
        except Exception as e:
            return {"error": f"Chunk {chunk_num} failed: {str(e)}"}

    def _extract_missing_compliance_items(self, ai_content: str, existing_items: list, original_requirements: list) -> list:
        """Try to extract any missing compliance items from the AI response"""
        
        print(f"🔧 Attempting to recover missing compliance items...")
        
        # Get requirements that are already analyzed (normalize for comparison)
        analyzed_reqs = set()
        for item in existing_items:
            req_text = item.get("requirement", "").strip()
            if req_text:
                # Remove numbering and get first 50 chars for comparison
                normalized = re.sub(r'^\d+\.\s*', '', req_text).strip()[:50]
                analyzed_reqs.add(normalized)
        
        print(f"🔧 Already analyzed {len(analyzed_reqs)} requirements")
        
        # Find missing requirements
        missing_reqs = []
        for i, req in enumerate(original_requirements):
            normalized = req.strip()[:50]
            if normalized not in analyzed_reqs:
                missing_reqs.append((i, req))
        
        print(f"🔧 Found {len(missing_reqs)} potentially missing requirements")
        
        if not missing_reqs:
            return []
        
        # Try to find analysis for missing requirements in the raw response
        recovered_items = []
        
        # More aggressive patterns to find partial compliance items
        patterns = [
            # Pattern 1: Full compliance item
            r'"requirement"\s*:\s*"([^"]{20,})"[^}]*?"spec_value"\s*:\s*"([^"]*)"[^}]*?"complies"\s*:\s*(true|false)[^}]*?"justification"\s*:\s*"([^"]*)"',
            
            # Pattern 2: Partial items with just requirement and complies
            r'"requirement"\s*:\s*"([^"]{20,})"[^}]*?"complies"\s*:\s*(true|false)',
            
            # Pattern 3: Items that might be cut off
            r'(\d+)\.\s+([^"]{20,})"[^}]*?"complies"\s*:\s*(true|false)[^}]*?"justification"\s*:\s*"([^"]*)"',
        ]
        
        for pattern_idx, pattern in enumerate(patterns):
            print(f"🔧 Trying extraction pattern {pattern_idx + 1}")
            matches = re.findall(pattern, ai_content, re.DOTALL | re.IGNORECASE)
            
            for match in matches:
                if len(match) >= 2:  # At least requirement and complies
                    req_text = match[0] if pattern_idx < 2 else match[1]
                    normalized = re.sub(r'^\d+\.\s*', '', req_text).strip()[:50]
                    
                    # Check if this requirement is missing
                    if normalized not in analyzed_reqs:
                        item = {
                            "requirement": req_text.strip(),
                            "spec_value": match[1] if len(match) > 3 and pattern_idx == 0 else "Extracted from partial response",
                            "complies": match[-2].lower() == "true",  # Second to last element is usually complies
                            "justification": match[-1] if len(match) > 2 else "Partially extracted from AI response"
                        }
                        
                        recovered_items.append(item)
                        analyzed_reqs.add(normalized)
                        print(f"🔧 Recovered: {req_text[:50]}...")
        
        print(f"🔧 Recovered {len(recovered_items)} items from partial extraction")
        return recovered_items
    
    def _extract_and_repair_json(self, text: str) -> Dict:
        """Extract JSON from text and repair common issues with Qwen output"""
        # First, try to find complete JSON inside the response
        json_pattern = re.compile(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', re.DOTALL)
        matches = json_pattern.findall(text)
        
        # Try each match, from longest to shortest (assuming longer is more complete)
        if matches:
            matches.sort(key=len, reverse=True)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    pass
    
        # If no valid JSON found with regex, try more aggressive cleaning
        clean_text = text
    
        # Remove any text before the first '{'
        start_idx = clean_text.find('{')
        if start_idx >= 0:
            clean_text = clean_text[start_idx:]
    
        # Remove any text after the last '}'
        end_idx = clean_text.rfind('}')
        if end_idx >= 0:
            clean_text = clean_text[:end_idx+1]
    
        # Fix common JSON errors
        try:
            # Fix unquoted property names (the most common issue)
            clean_text = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', clean_text)
            
            # Fix single quotes used instead of double quotes
            clean_text = re.sub(r"'([^']*)'", r'"\1"', clean_text)
            
            # Fix boolean capitalization
            clean_text = re.sub(r':\s*True\b', r': true', clean_text)
            clean_text = re.sub(r':\s*False\b', r': false', clean_text)
            
            # Remove trailing commas in objects and arrays
            clean_text = re.sub(r',\s*}', '}', clean_text)
            clean_text = re.sub(r',\s*]', ']', clean_text)
            
            # Try to parse the fixed JSON
            return json.loads(clean_text)
        except json.JSONDecodeError as e:
            print(f"⚠️ Standard JSON repair failed: {e}")
        
        # Last resort: manual extraction of data
        print("Attempting manual extraction of JSON data...")
        try:
            result = {"compliance_analysis": [], "overall_compliance": False}
            
            # Find compliance_analysis section
            analysis_match = re.search(r'"compliance_analysis"\s*:\s*\[(.*?)\]', text, re.DOTALL)
            if analysis_match:
                analysis_text = analysis_match.group(1)
                
                # Extract individual items
                item_pattern = re.compile(r'{(.*?)}', re.DOTALL)
                items = item_pattern.findall(analysis_text)
                
                for item_text in items:
                    item = {}
                    
                    # Extract requirement
                    req_match = re.search(r'"requirement"\s*:\s*"([^"]*)"', item_text)
                    if req_match:
                        item["requirement"] = req_match.group(1)
                    
                    # Extract spec_value
                    spec_match = re.search(r'"spec_value"\s*:\s*"([^"]*)"', item_text)
                    if spec_match:
                        item["spec_value"] = spec_match.group(1)
                    
                    # Extract complies
                    complies_match = re.search(r'"complies"\s*:\s*(true|false)', item_text.lower())
                    if complies_match:
                        item["complies"] = complies_match.group(1) == "true"
                    
                    # Extract justification
                    just_match = re.search(r'"justification"\s*:\s*"([^"]*)"', item_text)
                    if just_match:
                        item["justification"] = just_match.group(1)
                    
                    if "requirement" in item:
                        result["compliance_analysis"].append(item)
            
            # If we extracted any items, consider it a success
            if result["compliance_analysis"]:
                return result
        except Exception as e:
            print(f"Manual extraction failed: {e}")
        
        # If everything fails, return a synthetic response
        print("Creating fallback JSON response...")
        return {
            "compliance_analysis": [],
            "overall_compliance": False,
            "areas_exceeding_requirements": [],
            "potential_issues": ["Could not parse AI response due to JSON formatting errors"]
        }

    def post_process_compliance_logic(self, result: dict, original_requirements: list) -> dict:
        """
        Correct compliance logic for accuracy classes and percentages.
        """
        analysis_items = result.get("compliance_analysis", [])
        corrected_count = 0
        exceeding_areas = []

        for item in analysis_items:
            req = item.get("requirement", "").lower()
            spec = item.get("spec_value", "").lower()
            justification = item.get("justification", "").lower()
            original_complies = item.get("complies", False)

            # --- Accuracy Class Correction ---
            req_class = re.search(r'class\s*([\d\.]+)\s*s?', req)
            spec_class = re.search(r'class\s*([\d\.]+)\s*s?', spec)
            if req_class and spec_class:
                req_val = float(req_class.group(1))
                spec_val = float(spec_class.group(1))
                if spec_val <= req_val and not original_complies:
                    item["complies"] = True
                    item["justification"] = (
                        f"CORRECTED: Meter class {spec_class.group(0)} is better than required {req_class.group(0)} (smaller class number = higher accuracy)."
                    )
                    exceeding_areas.append(f"{item.get('requirement','')} ({item.get('spec_value','')})")
                    corrected_count += 1

            # --- Percentage Accuracy Correction ---
            req_pct = re.search(r'±?(\d+\.?\d*)\s*%', req)
            spec_pct = re.search(r'±?(\d+\.?\d*)\s*%', spec)
            if req_pct and spec_pct:
                req_val = float(req_pct.group(1))
                spec_val = float(spec_pct.group(1))
                if spec_val <= req_val and not original_complies:
                    item["complies"] = True
                    item["justification"] = (
                        f"CORRECTED: Meter accuracy ±{spec_val}% is better than required ±{req_val}% (smaller percentage = higher accuracy)."
                    )
                    exceeding_areas.append(f"{item.get('requirement','')} ({item.get('spec_value','')})")
                    corrected_count += 1

            # --- Justification Phrase Correction ---
            if (
                ("more stringent than" in justification or
                 "exceeds requirement" in justification or
                 "better than" in justification or
                 "higher accuracy" in justification or
                 "surpasses" in justification)
                and not original_complies
            ):
                item["complies"] = True
                item["justification"] = f"CORRECTED: {item['justification']} (meter exceeds requirement)"
                exceeding_areas.append(f"{item.get('requirement','')} ({item.get('spec_value','')})")
                corrected_count += 1

        if corrected_count > 0:
            print(f"🔧 Corrected {corrected_count} compliance logic errors (meter exceeds requirement)")
            result["areas_exceeding_requirements"] = list(set(result.get("areas_exceeding_requirements", []) + exceeding_areas))
            # Recalculate overall compliance
            total = len(analysis_items)
            compliant = sum(1 for item in analysis_items if item.get("complies", False))
            result["overall_compliance"] = (compliant / total) >= 0.8 if total else False

        return result

    def _clean_json_output(self, content):
        """Clean up JSON output from Qwen for better parsing"""
        
        # Qwen sometimes adds markdown code fences, remove them
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*$', '', content)
        
        # Handle the case where Qwen adds explanations before or after JSON
        json_match = re.search(r'(\{.*\})', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        
        # Fix common Qwen JSON issues
        content = content.replace('true,\n}', 'true\n}')
        content = content.replace('false,\n}', 'false\n}')
        content = content.replace("'", '"')
        content = re.sub(r',\s*]', ']', content)
        content = re.sub(r',\s*}', '}', content)
        
        return content
    
    def _safe_comparison_analysis(self, requirements: List[str], meter_specs: Dict, model_number: str) -> Dict:
        """Wrapper around comparison with better error handling"""
        try:
            print(f"🔧 DEBUG: Starting comparison for {model_number}")
            print(f"🔧 DEBUG: Requirements type: {type(requirements)}, count: {len(requirements) if requirements else 0}")
            print(f"🔧 DEBUG: Meter specs type: {type(meter_specs)}, keys: {list(meter_specs.keys()) if meter_specs else 'None'}")
            
            # Check for problematic data types in requirements
            for i, req in enumerate(requirements):
                if not isinstance(req, str):
                    print(f"🔧 DEBUG: WARNING - Requirement {i} is not a string: {type(req)}")
            
            # Check for problematic data types in meter_specs
            for key, value in meter_specs.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if not isinstance(sub_key, (str, int, float)):
                            print(f"🔧 DEBUG: WARNING - Meter spec dict key is not hashable: {type(sub_key)}")
            
            result = self._compare_requirements_with_specs(requirements, meter_specs, model_number)
            
            print(f"🔧 DEBUG: Comparison completed successfully")
            return result
            
        except TypeError as e:
            print(f"🔧 DEBUG: TypeError in comparison: {e}")
            print(f"🔧 DEBUG: Error details: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Return a safe fallback
            return {
                "error": f"TypeError during comparison: {str(e)}",
                "compliance_analysis": [],
                "overall_compliance": False,
                "areas_exceeding_requirements": [],
                "potential_issues": []
            }
            
        except Exception as e:
            print(f"🔧 DEBUG: Other error in comparison: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return {
                "error": f"Comparison failed: {str(e)}",
                "compliance_analysis": [],
                "overall_compliance": False,
                "areas_exceeding_requirements": [],
                "potential_issues": []
            }
       

if __name__ == "__main__":
    print("\nMeter Specification Compliance Tool\n" + "="*35)

    # Get analysis file path
    analysis_file = input("Enter path to meter analysis file (.txt): ").strip('"\'')
    if not os.path.exists(analysis_file):
        print(f"Error: Analysis file '{analysis_file}' not found!")
        exit(1)

    # Create comparator
    comparator = MeterSpecificationComparison()

    # Extract sections first
    sections = comparator._extract_sections_from_analysis(analysis_file)
    if not sections:
        print("No sections found in the analysis file.")
        exit(1)

    # Collect per-clause overrides
    per_clause_override = {}
    print("\nReview recommended meters for each clause. Press Enter to accept or type an alternate model number.\n")
    for section in sections:
        clause_id = section.get('clause_id', 'Unknown')
        recommended = section.get('selected_meter', 'None')
        print(f"Clause {clause_id} - {recommended}")
        alt = input("Alternate Meter (Enter to default): ").strip()
        if alt:
            per_clause_override[clause_id] = alt
        else:
            per_clause_override[clause_id] = recommended

    # Ask for output format preference
    output_format = input("\nSelect output format:\n1. Markdown\n2. Excel\n3. Both\nEnter choice (1-3): ").strip()

    # Add indicator here
    print(f"[INFO] Output format selected: {output_format}. Proceeding with report generation...")

    # Generate outputs based on preference
    md_output = None
    excel_output = None

    try: 
        if output_format in ["1", "3"]:
            print("[INFO] Generating Markdown report...")
            md_output = comparator.generate_detailed_comparison(
                analysis_file,
                override_meter=None,
                per_clause_override=per_clause_override
            )
            print(f"Markdown report generated: {md_output}")

        if output_format in ["2", "3"]:
            print("[INFO] Generating Excel report...")
            excel_output = comparator.export_to_excel(
                analysis_file,
                override_meter=None,
                per_clause_override=per_clause_override
            )
            print(f"Excel report generated: {excel_output}")

        print("\nAnalysis complete!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        print("The process encountered an error. Please check your input files and database.")
