import ollama
import sqlite3
import PyPDF2
import re
import json
import os
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class MeterRequirement:
    clause_id: str
    meter_type: str
    specifications: List[str]
    content: str

@dataclass
class MeterMatch:
    model_number: str
    description: str
    score: int
    reasoning: str = ""
    product_id: str = ""
    spec_compliance: Dict[str, str] = None

class MeterDatabase:
    """Database interface for testing.db using normalized meter schema"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._validate_database()
        self.model = "qwen2.5-coder:7b"  # Default model for AI interactions

    def _validate_database(self):
        """Ensure database exists and has expected structure"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                if 'Meters' not in tables:
                    raise ValueError("Meters table not found in database")
        except Exception as e:
            raise ValueError(f"Database validation failed: {e}")

    def get_meter_specs(self, model_number: str) -> dict:
        """Fetch all specs for a meter from normalized tables"""
        if not os.path.exists(self.db_path):
            return {}
        model_number = model_number.strip().upper()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM Meters
                    WHERE UPPER(model_name) = ? OR UPPER(series_name) = ? OR UPPER(device_short_name) = ?
                    LIMIT 1
                """, (model_number, model_number, model_number))
                meter_row = cursor.fetchone()
                if not meter_row:
                    cursor.execute("""
                        SELECT * FROM Meters
                        WHERE UPPER(model_name) LIKE ? OR UPPER(series_name) LIKE ? OR UPPER(device_short_name) LIKE ?
                        LIMIT 1
                    """, (f"%{model_number}%", f"%{model_number}%", f"%{model_number}%"))
                    meter_row = cursor.fetchone()
                if not meter_row:
                    return {}

                meter_id = meter_row["id"]
                specs = dict(meter_row)

                # Helper to fetch multi-value attributes
                def fetch_list(table, column):
                    cursor.execute(f"SELECT {column} FROM {table} WHERE meter_id = ?", (meter_id,))
                    return [row[0] for row in cursor.fetchall()]

                def fetch_kv(table, key_col, val_col):
                    cursor.execute(f"SELECT {key_col}, {val_col} FROM {table} WHERE meter_id = ?", (meter_id,))
                    return {row[0]: row[1] for row in cursor.fetchall()}

                specs["applications"] = fetch_list("DeviceApplications", "application")
                specs["power_quality_features"] = fetch_list("PowerQualityAnalysis", "analysis_feature")
                specs["measurements"] = fetch_list("Measurements", "measurement_type")
                specs["accuracy_classes"] = fetch_list("AccuracyClasses", "accuracy_class")
                specs["measurement_accuracy"] = fetch_kv("MeasurementAccuracy", "parameter", "accuracy")
                specs["communication_protocols"] = fetch_kv("CommunicationProtocols", "protocol", "support")
                specs["data_recording"] = fetch_list("DataRecordings", "recording_type")
                specs["certifications"] = fetch_list("Certifications", "certification")
                specs["inputs_outputs"] = [
                    {"type": row[0], "description": row[1]}
                    for row in cursor.execute("SELECT io_type, description FROM InputsOutputs WHERE meter_id = ?", (meter_id,))
                ]
                return specs
        except Exception as e:
            print(f"Error querying database: {e}")
        return {}

    def search_meters(self, requirement: MeterRequirement) -> List[MeterMatch]:
        """AI-powered meter search using the database and Qwen/ollama for ranking (no pre-filtering by score)"""
        matches = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, model_name, selection_blurb, product_name, device_short_name
                FROM Meters
            """)
            for row in cursor.fetchall():
                model_name = row[1] or ""
                selection_blurb = row[2] or ""
                matches.append(MeterMatch(
                    model_number=model_name,
                    description=selection_blurb,
                    score=0  # Score is not used, AI will decide
                ))
        if not matches:
            return []
        # Use Qwen/ollama to rank the matches
        prompt = f"""
You are an expert in electrical metering with a specialization in tendering opportunities. Given the following meter requirement and a list of candidate meters, select and rank the best-fit meters.

Meter Series Briefing:
- ION9000: Schneider Electric's most advanced power quality and revenue meter series. Offers highest accuracy (Class 0.1S), advanced power quality analysis, compliance reporting, and extensive communications. Suitable for critical facilities and demanding applications.
- PM8000: High-performance power quality meters with advanced PQ features, Class 0.2S accuracy, event recording, and flexible communications. Suitable for industrial and commercial power monitoring.
- PM5000: Versatile, cost-effective meters for energy management and basic PQ monitoring. Class 0.5S accuracy, suitable for general energy metering and submetering.
- PM2000/EasyLogic: Entry-level, affordable meters for basic energy monitoring. Suitable for cost-sensitive applications where advanced PQ is not required.

Requirement:
Clause: {requirement.clause_id}
Type: {requirement.meter_type}
Specifications:
{chr(10).join('- ' + s for s in requirement.specifications)}

Candidate meters:
{chr(10).join(f"- {m.model_number}: {m.description}" for m in matches)}

Instructions:
- Only select meters that truly meet the key requirements. If none are suitable, return an empty list.
- Rank the meters by technical fit and value.
- For each meter, provide a score out of 100 based on how well it meets the requirements.
- If the tendering specifications call for advanced features, prefer meters that meet those.
- Consider cost-effectiveness and suitability for the specified applications.
- Output a JSON array of model numbers in order of suitability, with a brief reason for the top choice.

Example output:
{{
  "ranking": [
    {{"model": "PM5560", "reason": "Meets all requirements at moderate cost", "score": 95}},
    {{"model": "PM8240", "reason": "Advanced features, but not required", "score": 85}},
  ]
}}
If none are suitable, output:
{{
  "ranking": []
}}
"""
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2}
            )
            ai_content = response['message']['content']
            json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
            if json_match:
                ranking_data = json.loads(json_match.group())
                ranked_models = [r["model"] for r in ranking_data.get("ranking", [])]
                # Reorder matches according to AI ranking
                ranked_matches = []
                for idx, model in enumerate(ranked_models, 1):
                    for m in matches:
                        if m.model_number == model:
                            m.reasoning = next((r["reason"] for r in ranking_data["ranking"] if r["model"] == model), "")
                            m.score = next((r["score"] for r in ranking_data["ranking"] if r["model"] == model), 0)
                            ranked_matches.append(m)
                            break
                # Add any unranked matches at the end
                for m in matches:
                    if m not in ranked_matches:
                        ranked_matches.append(m)
                return ranked_matches
        except Exception as e:
            print(f"AI ranking failed, using default order. Error: {e}")
        return matches

    def _format_meter_specs_for_prompt(self, meter_specs: Dict) -> str:
        """Format meter specifications in a concise way for the AI prompt"""
        lines = []
        
        # Basic meter info
        if "model_name" in meter_specs and meter_specs["model_name"]:
            lines.append(f"Model: {meter_specs['model_name']}")
        if "product_name" in meter_specs and meter_specs["product_name"]:
            lines.append(f"Product: {meter_specs['product_name']}")
        if "series_name" in meter_specs and meter_specs["series_name"]:
            lines.append(f"Series: {meter_specs['series_name']}")
        if "selection_blurb" in meter_specs and meter_specs["selection_blurb"]:
            lines.append(f"Description: {meter_specs['selection_blurb']}")
        
        # Physical specifications
        lines.append("\nPHYSICAL SPECIFICATIONS:")
        if "display_type" in meter_specs and meter_specs["display_type"]:
            lines.append(f"- Display: {meter_specs['display_type']}")
        if "mounting_mode" in meter_specs and meter_specs["mounting_mode"]:
            lines.append(f"- Mounting: {meter_specs['mounting_mode']}")
        if "rated_current" in meter_specs and meter_specs["rated_current"]:
            lines.append(f"- Rated Current: {meter_specs['rated_current']}")
        if "network_frequency" in meter_specs and meter_specs["network_frequency"]:
            lines.append(f"- Frequency: {meter_specs['network_frequency']}")
        if "sampling_rate" in meter_specs and meter_specs["sampling_rate"]:
            lines.append(f"- Sampling Rate: {meter_specs['sampling_rate']}")
        if "memory_capacity" in meter_specs and meter_specs["memory_capacity"]:
            lines.append(f"- Memory: {meter_specs['memory_capacity']}")
        
        # Environmental specifications
        if meter_specs.get("operating_temp") or meter_specs.get("storage_temp"):
            lines.append("\nENVIRONMENTAL SPECIFICATIONS:")
            if "operating_temp" in meter_specs and meter_specs["operating_temp"]:
                lines.append(f"- Operating Temperature: {meter_specs['operating_temp']}")
            if "storage_temp" in meter_specs and meter_specs["storage_temp"]:
                lines.append(f"- Storage Temperature: {meter_specs['storage_temp']}")
            if "relative_humidity" in meter_specs and meter_specs["relative_humidity"]:
                lines.append(f"- Humidity: {meter_specs['relative_humidity']}")
                
        # Accuracy specifications (most important for compliance)
        if "measurement_accuracy" in meter_specs and meter_specs["measurement_accuracy"]:
            lines.append("\nMEASUREMENT ACCURACY:")
            accuracy_data = meter_specs["measurement_accuracy"]
            if isinstance(accuracy_data, dict):
                for param, value in accuracy_data.items():
                    lines.append(f"- {param}: {value}")
            elif isinstance(accuracy_data, (list, tuple)):
                for item in accuracy_data:
                    if isinstance(item, dict):
                        for param, value in item.items():
                            lines.append(f"- {param}: {value}")
                    else:
                        lines.append(f"- {str(item)}")
            else:
                lines.append(f"- {str(accuracy_data)}")
                
        # Accuracy classes
        if "accuracy_classes" in meter_specs and meter_specs["accuracy_classes"]:
            lines.append("\nACCURACY CLASSES:")
            accuracy_classes = meter_specs["accuracy_classes"]
            if isinstance(accuracy_classes, (list, tuple)):
                for acc_class in accuracy_classes:
                    lines.append(f"- {str(acc_class)}")
            else:
                lines.append(f"- {str(accuracy_classes)}")
                
        # Communication protocols
        if "communication_protocols" in meter_specs and meter_specs["communication_protocols"]:
            lines.append("\nCOMMUNICATION PROTOCOLS:")
            protocols = meter_specs["communication_protocols"]
            if isinstance(protocols, dict):
                for protocol, support in protocols.items():
                    support_text = f" ({support})" if support else ""
                    lines.append(f"- {protocol}{support_text}")
            elif isinstance(protocols, (list, tuple)):
                for protocol in protocols:
                    if isinstance(protocol, dict):
                        for key, value in protocol.items():
                            support_text = f" ({value})" if value else ""
                            lines.append(f"- {key}{support_text}")
                    else:
                        lines.append(f"- {str(protocol)}")
            else:
                lines.append(f"- {str(protocols)}")
                    
        # Power quality features
        if "power_quality_features" in meter_specs and meter_specs["power_quality_features"]:
            lines.append("\nPOWER QUALITY ANALYSIS:")
            pq_features = meter_specs["power_quality_features"]
            if isinstance(pq_features, (list, tuple)):
                for feature in pq_features:
                    lines.append(f"- {str(feature)}")
            else:
                lines.append(f"- {str(pq_features)}")
                
        # Measurements
        if "measurements" in meter_specs and meter_specs["measurements"]:
            lines.append("\nMEASUREMENT CAPABILITIES:")
            measurements = meter_specs["measurements"]
            if isinstance(measurements, (list, tuple)):
                for measurement in measurements:
                    lines.append(f"- {str(measurement)}")
            else:
                lines.append(f"- {str(measurements)}")
                
        # Data recording
        if "data_recording" in meter_specs and meter_specs["data_recording"]:
            lines.append("\nDATA RECORDING:")
            recordings = meter_specs["data_recording"]
            if isinstance(recordings, (list, tuple)):
                for recording in recordings:
                    lines.append(f"- {str(recording)}")
            else:
                lines.append(f"- {str(recordings)}")
            
        # Inputs/Outputs
        if "inputs_outputs" in meter_specs and meter_specs["inputs_outputs"]:
            lines.append("\nINPUTS/OUTPUTS:")
            ios = meter_specs["inputs_outputs"]
            if isinstance(ios, (list, tuple)):
                for io in ios:
                    if isinstance(io, dict):
                        io_type = io.get('type', 'Unknown')
                        io_desc = io.get('description', 'No description')
                        lines.append(f"- {io_type}: {io_desc}")
                    else:
                        lines.append(f"- {str(io)}")
            else:
                lines.append(f"- {str(ios)}")
            
        # Certifications
        if "certifications" in meter_specs and meter_specs["certifications"]:
            lines.append("\nCERTIFICATIONS:")
            certs = meter_specs["certifications"]
            if isinstance(certs, (list, tuple)):
                for cert in certs:
                    lines.append(f"- {str(cert)}")
            else:
                lines.append(f"- {str(certs)}")
            
        # Applications
        if "applications" in meter_specs and meter_specs["applications"]:
            lines.append("\nAPPLICATIONS:")
            apps = meter_specs["applications"]
            if isinstance(apps, (list, tuple)):
                for app in apps:
                    lines.append(f"- {str(app)}")
            else:
                lines.append(f"- {str(apps)}")
            
        return "\n".join(lines)

class DocumentParser:
    """LLM-powered document parsing for tender files"""

    @staticmethod
    def read_document(file_path: str) -> str:
        """Read text document (no PDF support needed for this workflow)"""
        file_path = file_path.strip('"\'')
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

    @staticmethod
    def extract_meter_requirements(text: str, manual_clauses: List[str]) -> List['MeterRequirement']:
        """Extract specified clauses using LLM for robust parsing."""
        import ollama
        requirements = []
        for clause_id in manual_clauses:
            prompt = f"""
You are an expert at reading tender documents. Extract the **full text** (including all subpoints, bullet points, and indented text) for clause "{clause_id}" from the following tender document. Return only the text for this clause, including its heading and all relevant content, but do not include any other clauses.

Tender document:
{text}
"""
            try:
                response = ollama.chat(
                    model="qwen2.5-coder:7b",
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1}
                )
                clause_text = response['message']['content'].strip()
                if clause_text:
                    requirements.append(MeterRequirement(
                        clause_id=clause_id,
                        meter_type="",  # Optionally, use LLM to extract a type/title
                        specifications=[clause_text],  # Or further split/specify if needed
                        content=clause_text
                    ))
            except Exception as e:
                print(f"LLM extraction failed for clause {clause_id}: {e}")
        return requirements

class TenderAnalyzer:
    """Main analyzer class that processes tender documents and recommends meters"""

    def __init__(self, database_path: str):
        self.database = MeterDatabase(database_path)
        self.parser = DocumentParser

    def analyze_document(self, tender_file: str, manual_clauses: List[str], output_path: str = "analysis_output.txt") -> List[Dict]:
        output_lines = []
        def write(line):
            print(line)
            output_lines.append(line)

        write(f"📄 Analyzing document: {os.path.basename(tender_file)}")
        doc_text = self.parser.read_document(tender_file)
        write(f"📄 Document loaded: {len(doc_text)} characters")
        requirements = self.parser.extract_meter_requirements(doc_text, manual_clauses)
        write(f"📋 Found {len(requirements)} meter requirements")
        results = []
        for i, req in enumerate(requirements, 1):
            write(f"\n✨ Processing requirement {i}/{len(requirements)}: {req.clause_id}...")
            write(f"📝 Type: {req.meter_type}")
            write(f"📝 Specifications:")
            for spec in req.specifications:
                # Skip lines that look like clause headings (e.g., "- Clause 8.0 – Digital Power Meter")
                if re.match(r"-?\s*Clause\s+\d+(\.\d+)*\s*[–-]", spec, re.IGNORECASE):
                    continue
                write(f"   - {spec}")
            matches = self.database.search_meters(req)

            # Deduplicate by model_number
            unique_matches = []
            seen_models = set()
            for m in matches:
                if m.model_number not in seen_models:
                    unique_matches.append(m)
                    seen_models.add(m.model_number)

            # Print the top 3 best-fit meters and their brief info
            if unique_matches:
                write(f"\n🏆 Top 3 Best-fit meters:")
                for idx, top_match in enumerate(unique_matches[:3], 1):
                    write(f"  {idx}. {top_match.model_number}")
                    if top_match.reasoning:
                        write(f"     Reason: {top_match.reasoning}")
                    write(f"     Score: {top_match.score}")
                    write(f"     Description: {top_match.description}")
            else:
                write("❌ No suitable meters found for this requirement")
        write("\n📊 Analysis complete!")

        # Write all output to file
        with open(output_path, "w", encoding="utf-8") as f:
            for line in output_lines:
                f.write(line + "\n")
        print(f"\n[INFO] Results written to {output_path}")
        return results

    def _safe_comparison_analysis(self, requirements: List[str], meter_specs: Dict, model_number: str) -> Dict:
        """Wrapper around comparison with better error handling"""
        try:
            print(f"🔧 DEBUG: Starting comparison for {model_number}")
            print(f"🔧 DEBUG: Requirements type: {type(requirements)}, count: {len(requirements) if requirements else 0}")
            print(f"🔧 DEBUG: Meter specs type: {type(meter_specs)}, keys: {list(meter_specs.keys()) if meter_specs else 'None'}")
            
            # Check for problematic data types in requirements
            for i, req in enumerate(requirements):
                if not isinstance(req, str):
                    print(f"🔧 DEBUG: WARNING - Requirement {i} is not a string: {type(req)} = {req}")
                    # Convert to string if it's not already
                    requirements[i] = str(req)
            
            # Check and clean meter_specs for problematic data types
            cleaned_specs = {}
            for key, value in meter_specs.items():
                if isinstance(value, dict):
                    cleaned_dict = {}
                    for sub_key, sub_value in value.items():
                        # Ensure dictionary keys are hashable
                        if isinstance(sub_key, (str, int, float)):
                            cleaned_dict[sub_key] = sub_value
                        else:
                            print(f"🔧 DEBUG: Converting unhashable key {type(sub_key)} to string")
                            cleaned_dict[str(sub_key)] = sub_value
                    cleaned_specs[key] = cleaned_dict
                elif isinstance(value, (list, tuple)):
                    # Ensure all list items are strings
                    cleaned_list = []
                    for item in value:
                        if isinstance(item, str):
                            cleaned_list.append(item)
                        elif isinstance(item, dict):
                            # Convert dict to string representation
                            cleaned_list.append(str(item))
                        else:
                            cleaned_list.append(str(item))
                    cleaned_specs[key] = cleaned_list
                else:
                    cleaned_specs[key] = value
            
            print(f"🔧 DEBUG: Cleaned specs, proceeding with comparison...")
            result = self._compare_requirements_with_specs(requirements, cleaned_specs, model_number)
            
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
    analyzer = TenderAnalyzer(r"C:\Users\cyqt2\Database\overhaul\databases\meters.db")

    # Prompt for tender file path
    tender_file = input("Enter the path to the tender document (e.g., tender.txt): ").strip()

    # Prompt for clause IDs (comma-separated)
    clause_input = input("Enter clause IDs to extract (comma-separated, e.g., 6.7.2,6.7.3): ").strip()
    manual_clauses = [c.strip() for c in clause_input.split(",") if c.strip()]

    analyzer.analyze_document(tender_file, manual_clauses)



