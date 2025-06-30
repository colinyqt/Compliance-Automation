import re
import sqlite3
import pandas as pd
import ollama
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path

@dataclass
class RequirementSpec:
    """Individual specification requirement"""
    spec_id: str
    description: str
    value: str = ""
    unit: str = ""

@dataclass
class MeterRequirement:
    """Complete meter requirement from analysis"""
    clause_id: str
    meter_type: str
    specifications: List[RequirementSpec]
    recommended_meters: List[Dict]

@dataclass
class ComplianceResult:
    """Compliance check result"""
    status: str  # "Compliant", "Partially Compliant", "Not Compliant"
    justification: str
    meter_value: str = ""
    requirement_value: str = ""

class DatabaseQueryEngine:
    """Database query engine with direct SQL (Vanna disabled for now)"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        # Disable Vanna for now to avoid API issues
        # self.vn = VannaDefault(model='chinook', api_key='your-api-key')
        # self._setup_vanna()
    
    def query_meter_spec(self, meter_model: str, spec_type: str) -> Dict:
        """Query specific meter specification using direct SQL"""
        return self._direct_query_fallback(meter_model, spec_type)
    
    def _direct_query_fallback(self, meter_model: str, spec_type: str) -> Dict:
        """Direct SQL query as fallback when Vanna fails"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get meter ID first - try multiple matching strategies
                cursor.execute("""
                    SELECT id FROM Meters 
                    WHERE model_name = ? OR device_short_name = ? OR product_name LIKE ?
                """, (meter_model, meter_model, f"%{meter_model}%"))
                
                meter_row = cursor.fetchone()
                if not meter_row:
                    print(f"⚠️ Meter not found in database: {meter_model}")
                    return {"success": False, "error": "Meter not found"}
                
                meter_id = meter_row[0]
                print(f"✅ Found meter ID {meter_id} for {meter_model}")
                
                # Query specific specification type
                if "accuracy" in spec_type.lower():
                    cursor.execute("""
                        SELECT parameter, accuracy FROM MeasurementAccuracy 
                        WHERE meter_id = ?
                    """, (meter_id,))
                    results = cursor.fetchall()
                    return {"success": True, "data": dict(results), "type": "accuracy"}
                
                elif "communication" in spec_type.lower():
                    cursor.execute("""
                        SELECT protocol, support FROM CommunicationProtocols 
                        WHERE meter_id = ?
                    """, (meter_id,))
                    results = cursor.fetchall()
                    return {"success": True, "data": dict(results), "type": "communication"}
                
                elif "measurement" in spec_type.lower():
                    cursor.execute("""
                        SELECT measurement_type FROM Measurements 
                        WHERE meter_id = ?
                    """, (meter_id,))
                    results = [row[0] for row in cursor.fetchall()]
                    return {"success": True, "data": results, "type": "measurement"}
                
                elif "environmental" in spec_type.lower():
                    cursor.execute("""
                        SELECT * FROM Meters WHERE id = ?
                    """, (meter_id,))
                    result = cursor.fetchone()
                    if result:
                        columns = [desc[0] for desc in cursor.description]
                        meter_data = dict(zip(columns, result))
                        # Extract temperature and environmental specs
                        env_data = {
                            "operating_temp_min": meter_data.get("operating_temp_min"),
                            "operating_temp_max": meter_data.get("operating_temp_max"),
                            "protection_rating": meter_data.get("protection_rating")
                        }
                        return {"success": True, "data": env_data, "type": "environmental"}
                
                else:
                    # General meter info - get all related specs
                    all_specs = {}
                    
                    # Get basic meter info
                    cursor.execute("SELECT * FROM Meters WHERE id = ?", (meter_id,))
                    result = cursor.fetchone()
                    if result:
                        columns = [desc[0] for desc in cursor.description]
                        all_specs.update(dict(zip(columns, result)))
                    
                    # Get accuracy specs
                    cursor.execute("SELECT parameter, accuracy FROM MeasurementAccuracy WHERE meter_id = ?", (meter_id,))
                    accuracy_results = cursor.fetchall()
                    if accuracy_results:
                        all_specs["accuracy_specs"] = dict(accuracy_results)
                    
                    # Get communication specs
                    cursor.execute("SELECT protocol, support FROM CommunicationProtocols WHERE meter_id = ?", (meter_id,))
                    comm_results = cursor.fetchall()
                    if comm_results:
                        all_specs["communication_specs"] = dict(comm_results)
                    
                    return {"success": True, "data": all_specs, "type": "general"}
                    
        except Exception as e:
            print(f"❌ Database query error: {e}")
            return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "No data found"}

class AnalysisParser:
    """Parse analysis_output.txt files"""
    
    def parse_analysis_file(self, file_path: str) -> List[MeterRequirement]:
        """Parse the analysis output file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        requirements = []
        
        # Split by processing requirements
        requirement_sections = re.split(r'✨ Processing requirement \d+/\d+:', content)[1:]
        
        for section in requirement_sections:
            # Extract clause ID and type
            clause_match = re.search(r'(\d+\.\d+|\d+)\.\.\.', section)
            type_match = re.search(r'📝 Type: (.+)', section)
            
            if not clause_match or not type_match:
                continue
                
            clause_id = clause_match.group(1)
            meter_type = type_match.group(1).strip()
            
            # Extract specifications - UPDATED PATTERN
            specs_section = re.search(r'📝 Specifications:(.*?)🏆 Top 3 Best-fit meters:', section, re.DOTALL)
            specifications = []
            
            if specs_section:
                spec_lines = specs_section.group(1).strip().split('\n')
                for line in spec_lines:
                    line = line.strip()
                    if line.startswith('- ') and not line.startswith('- ... and'):
                        spec_text = line[2:].strip()
                        specifications.append(self._parse_specification_line(spec_text))
            
            # Extract recommended meters - FIXED PARSING
            meters_section = re.search(r'🏆 Top 3 Best-fit meters:(.*?)(?=✨|📊)', section, re.DOTALL)
            recommended_meters = []
            
            if meters_section:
                meter_text = meters_section.group(1).strip()
                
                # Debug: Print the meter text to see what we're working with
                print(f"🔧 Debug - Meter section for {clause_id}:")
                print(f"Raw text (first 300 chars):\n{meter_text[:300]}")
                
                # IMPROVED: Find all meter entries using a more flexible pattern
                # Pattern matches: number, dot, space, then captures everything until next number or end
                meter_pattern = r'\s*(\d+)\.\s+(.*?)(?=\n\s*\d+\.\s+|\Z)'
                meter_matches = re.findall(meter_pattern, meter_text, re.DOTALL)
                
                print(f"🔧 Found {len(meter_matches)} meter matches")
                
                for rank, meter_content in meter_matches:
                    lines = meter_content.strip().split('\n')
                    
                    if not lines:
                        continue
                    
                    # First line should be the meter model
                    model_name = lines[0].strip()
                    
                    # Extract reason and score from subsequent lines
                    reason = "No reason provided"
                    score = 0
                    
                    for line in lines[1:]:
                        line = line.strip()
                        if line.startswith('Reason:'):
                            reason = line.replace('Reason:', '').strip()
                        elif line.startswith('Score:'):
                            score_text = line.replace('Score:', '').strip()
                            try:
                                score = int(score_text)
                            except ValueError:
                                score = 0
                    
                    recommended_meters.append({
                        'model': model_name,
                        'reason': reason,
                        'score': score
                    })
                    
                    print(f"🔧 Debug - Found meter: {model_name} (Score: {score})")
            
            if not recommended_meters:
                print(f"⚠️ No meters found for clause {clause_id}")
            else:
                print(f"✅ Found {len(recommended_meters)} meters for clause {clause_id}")
            
            requirements.append(MeterRequirement(
                clause_id=clause_id,
                meter_type=meter_type,
                specifications=specifications,
                recommended_meters=recommended_meters
            ))
        
        return requirements
    
    def _parse_specification_line(self, spec_text: str) -> RequirementSpec:
        """Parse individual specification line"""
        # Extract specification ID if present
        spec_id_match = re.match(r'(\d+\.\d+(?:\.\d+)?)\s+(.+)', spec_text)
        if spec_id_match:
            spec_id = spec_id_match.group(1)
            description = spec_id_match.group(2)
        else:
            spec_id = ""
            description = spec_text
        
        # Extract value and unit if present
        value = ""
        unit = ""
        
        # Look for accuracy values
        accuracy_match = re.search(r'([±]?\d+\.?\d*[%]?)', description)
        if accuracy_match:
            value = accuracy_match.group(1)
            if '%' in value:
                unit = "%"
                value = value.replace('%', '')
        
        # Look for temperature ranges
        temp_match = re.search(r'(-?\d+)°C\s+to\s+\+?(-?\d+)°C', description)
        if temp_match:
            value = f"{temp_match.group(1)} to {temp_match.group(2)}"
            unit = "°C"
        
        # Look for class specifications
        class_match = re.search(r'[Cc]lass\s+([\d\.]+[A-Za-z]?)', description)
        if class_match:
            value = class_match.group(1)
            unit = "Class"
        
        return RequirementSpec(
            spec_id=spec_id,
            description=description,
            value=value,
            unit=unit
        )

class ComplianceChecker:
    """Check compliance between requirements and meter specifications"""
    
    def __init__(self, db_engine: DatabaseQueryEngine):
        self.db_engine = db_engine
        self.model = "qwen3:8b"
    
    def check_compliance(self, requirement: RequirementSpec, meter_model: str) -> ComplianceResult:
        """Check if meter meets specific requirement"""
        
        # Query meter specifications
        meter_data = self._get_meter_specification(meter_model, requirement)
        
        if not meter_data:
            return ComplianceResult(
                status="Not Compliant",
                justification="Unable to retrieve meter specifications for comparison",
                meter_value="Unknown",
                requirement_value=requirement.value
            )
        
        # Use AI to determine compliance
        return self._ai_compliance_check(requirement, meter_model, meter_data)
    
    def _get_meter_specification(self, meter_model: str, requirement: RequirementSpec) -> Dict:
        """Get relevant meter specification data"""
        spec_type = self._categorize_requirement(requirement.description)
        result = self.db_engine.query_meter_spec(meter_model, spec_type)
        
        if result["success"]:
            return result["data"]
        else:
            return {}
    
    def _categorize_requirement(self, description: str) -> str:
        """Categorize requirement to determine what to query"""
        description_lower = description.lower()
        
        if any(word in description_lower for word in ["accuracy", "class", "±", "percent"]):
            return "accuracy"
        elif any(word in description_lower for word in ["communication", "modbus", "tcp", "ethernet", "rs485"]):
            return "communication"
        elif any(word in description_lower for word in ["measurement", "voltage", "current", "power", "frequency"]):
            return "measurement"
        elif any(word in description_lower for word in ["temperature", "operating", "environmental"]):
            return "environmental"
        else:
            return "general"
    
    def _ai_compliance_check(self, requirement: RequirementSpec, meter_model: str, meter_data: Dict) -> ComplianceResult:
        """Use AI to determine compliance status"""
        
        prompt = f"""
You are an expert in electrical meter compliance analysis. Determine if the meter meets the requirement.

Requirement: {requirement.description}
Required Value: {requirement.value} {requirement.unit}

Meter Model: {meter_model}
Meter Specifications: {meter_data}

Analyze if the meter specification meets, partially meets, or does not meet the requirement.

Respond with JSON in this exact format:
{{
    "status": "Compliant" | "Partially Compliant" | "Not Compliant",
    "justification": "Brief explanation of why",
    "meter_value": "What the meter actually provides",
    "requirement_value": "What was required"
}}

Consider:
- For accuracy: Lower values are better (e.g., ±0.1% is better than ±0.5%)
- For classes: Class 0.1 is better than Class 0.5
- For temperature ranges: Meter range should encompass required range
- For communications: Meter should support required protocols
"""
        
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "timeout": 20.0}
            )
            
            ai_content = response['message']['content']
            
            # Extract JSON
            import json
            json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
            if json_match:
                result_data = json.loads(json_match.group())
                return ComplianceResult(
                    status=result_data.get("status", "Not Compliant"),
                    justification=result_data.get("justification", "AI analysis failed"),
                    meter_value=result_data.get("meter_value", "Unknown"),
                    requirement_value=result_data.get("requirement_value", requirement.value)
                )
                
        except Exception as e:
            print(f"⚠️ AI compliance check failed: {e}")
        
        # Fallback to rule-based checking
        return self._rule_based_compliance_check(requirement, meter_model, meter_data)
    
    def _rule_based_compliance_check(self, requirement: RequirementSpec, meter_model: str, meter_data: Dict) -> ComplianceResult:
        """Fallback rule-based compliance checking"""
        
        if not meter_data:
            return ComplianceResult(
                status="Not Compliant",
                justification="No meter data available for comparison",
                meter_value="Unknown",
                requirement_value=requirement.value
            )
        
        # Simple rule-based logic for common cases
        desc_lower = requirement.description.lower()
        
        if "modbus" in desc_lower and isinstance(meter_data, dict):
            if any("modbus" in str(v).lower() for v in meter_data.values()):
                return ComplianceResult(
                    status="Compliant",
                    justification="Meter supports Modbus communication",
                    meter_value="Modbus supported",
                    requirement_value="Modbus required"
                )
        
        return ComplianceResult(
            status="Partially Compliant",
            justification="Limited data available for comprehensive analysis",
            meter_value="Available in database",
            requirement_value=requirement.value
        )

class ExcelReportGenerator:
    """Generate Excel compliance reports"""
    
    def __init__(self, db_engine: DatabaseQueryEngine):
        self.db_engine = db_engine
        self.compliance_checker = ComplianceChecker(db_engine)
    
    def generate_report(self, requirements: List[MeterRequirement], output_path: str):
        """Generate comprehensive Excel compliance report"""
        
        print("📊 Generating Excel compliance report...")
        
        if not requirements:
            print("❌ No requirements to process")
            return
        
        # Create Excel writer
        with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # Define formats
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1
            })
            
            compliant_format = workbook.add_format({
                'bg_color': '#C6EFCE',
                'font_color': '#006100',
                'border': 1
            })
            
            partial_format = workbook.add_format({
                'bg_color': '#FFEB9C',
                'font_color': '#9C5700',
                'border': 1
            })
            
            non_compliant_format = workbook.add_format({
                'bg_color': '#FFC7CE',
                'font_color': '#9C0006',
                'border': 1
            })
            
            cell_format = workbook.add_format({'border': 1, 'valign': 'top'})
            
            # Generate report for each requirement
            for req_idx, requirement in enumerate(requirements):
                sheet_name = f"Clause_{requirement.clause_id}".replace(".", "_")
                
                print(f"📋 Processing {requirement.clause_id}: {requirement.meter_type}")
                print(f"   📝 {len(requirement.specifications)} specifications")
                print(f"   🏆 {len(requirement.recommended_meters)} recommended meters")
                
                if not requirement.recommended_meters:
                    print(f"   ⚠️ Skipping - no recommended meters")
                    continue
                
                if not requirement.specifications:
                    print(f"   ⚠️ Skipping - no specifications")
                    continue
                
                # Create worksheet data
                report_data = []
                
                for meter in requirement.recommended_meters[:3]:  # Top 3 meters
                    meter_model = meter['model']
                    print(f"  🔍 Checking compliance for {meter_model}")
                    
                    for spec in requirement.specifications:
                        if not spec.description.strip():
                            continue  # Skip empty specifications
                        
                        # Skip header specifications (those that just repeat the clause number)
                        if spec.spec_id.startswith(requirement.clause_id) and len(spec.description) < 50:
                            continue
                        
                        print(f"    📋 Checking spec: {spec.spec_id} - {spec.description[:50]}...")
                        
                        compliance = self.compliance_checker.check_compliance(spec, meter_model)
                        
                        report_data.append({
                            'Meter Model': meter_model,
                            'Specification ID': spec.spec_id,
                            'Requirement': spec.description,
                            'Required Value': f"{spec.value} {spec.unit}".strip(),
                            'Meter Value': compliance.meter_value,
                            'Compliance Status': compliance.status,
                            'Justification': compliance.justification
                        })
                
                if not report_data:
                    print(f"   ⚠️ No compliance data generated for {requirement.clause_id}")
                    continue
                
                print(f"   ✅ Generated {len(report_data)} compliance rows")
                
                # Create DataFrame
                df = pd.DataFrame(report_data)
                
                # Write to Excel
                df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)
                worksheet = writer.sheets[sheet_name]
                
                # Add title
                title = f"Compliance Report - {requirement.meter_type} (Clause {requirement.clause_id})"
                worksheet.write(0, 0, title, workbook.add_format({'bold': True, 'font_size': 14}))
                
                # Format headers
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(1, col_num, value, header_format)
                
                # Format compliance status cells
                for row_num in range(len(df)):
                    status = df.iloc[row_num]['Compliance Status']
                    
                    if status == 'Compliant':
                        cell_fmt = compliant_format
                    elif status == 'Partially Compliant':
                        cell_fmt = partial_format
                    else:
                        cell_fmt = non_compliant_format
                    
                    worksheet.write(row_num + 2, 5, status, cell_fmt)  # Column 5 is Compliance Status
                    
                    # Apply border format to other cells
                    for col_num in range(len(df.columns)):
                        if col_num != 5:  # Skip status column
                            worksheet.write(row_num + 2, col_num, df.iloc[row_num, col_num], cell_format)
                
                # Auto-adjust column widths
                for col_num, column in enumerate(df.columns):
                    max_length = max(df[column].astype(str).map(len).max(), len(column)) + 2
                    worksheet.set_column(col_num, col_num, min(max_length, 50))
        
        print(f"✅ Excel report generated: {output_path}")

def main():
    """Main function"""
    print("📊 Excel Compliance Report Generator")
    print("=" * 50)
    
    # Get input file
    analysis_file = input("Enter path to analysis output file: ").strip('"\'')
    if not Path(analysis_file).exists():
        print(f"❌ File not found: {analysis_file}")
        return
    
    # Get output path
    output_file = input("Enter output Excel file path [compliance_report.xlsx]: ").strip('"\'')
    if not output_file:
        output_file = "compliance_report.xlsx"
    
    if not output_file.endswith('.xlsx'):
        output_file += '.xlsx'
    
    try:
        # Initialize components
        db_engine = DatabaseQueryEngine("testing.db")
        parser = AnalysisParser()
        report_generator = ExcelReportGenerator(db_engine)
        
        # Parse analysis file
        print(f"📄 Parsing analysis file: {Path(analysis_file).name}")
        requirements = parser.parse_analysis_file(analysis_file)
        print(f"📋 Found {len(requirements)} meter requirements")
        
        # Generate report
        report_generator.generate_report(requirements, output_file)
        
        print(f"\n🎉 Compliance report completed!")
        print(f"📁 Output file: {Path(output_file).absolute()}")
        
    except Exception as e:
        print(f"❌ Error generating report: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()