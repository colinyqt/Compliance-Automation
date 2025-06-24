import ollama
import sqlite3
import PyPDF2
import re
import json
import os
import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
import threading
import time
import functools

def process_with_timeout(prompt, timeout=30):
    """Process a prompt with ollama with a timeout"""
    result = [None]
    exception = [None]
    
    def target():
        try:
            result[0] = ollama.chat(
                model="qwen2.5-coder:7b",
                messages=[{"role": "user", "content": prompt}]
            )
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout)
    
    if thread.is_alive():
        print(f"⚠️ Request timed out after {timeout} seconds")
        thread.join(1)  # Give a moment to clean up
        raise TimeoutError(f"Request timed out after {timeout} seconds")
    
    if exception[0]:
        raise exception[0]
    
    return result[0]

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
    """Single-AI interface to meters.db using Qwen"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._validate_database()
        self.model = "qwen2.5-coder:7b"
    
    def _validate_database(self):
        """Ensure database exists and has expected structure"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                if 'Products' not in tables:
                    raise ValueError("Products table not found in database")
        except Exception as e:
            raise ValueError(f"Database validation failed: {e}")
    
    def get_meter_count(self) -> int:
        """Get total number of meters in database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Products")
            return cursor.fetchone()[0]
    
    def search_meters(self, requirement: MeterRequirement) -> List[MeterMatch]:
        """AI-enhanced meter search using both database and knowledge base"""
        print("🔍 Starting comprehensive meter search...")
        
        # Step 1: Search the database first
        database_matches = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get all potentially relevant meters from database
            candidate_meters = self._get_candidate_meters(cursor, requirement)
            
            if candidate_meters:
                print(f"📊 Found {len(candidate_meters)} potential matches in database")
                # Use AI to analyze and rank meters contextually
                database_matches = self._ai_rank_meters(requirement, candidate_meters)
            else:
                print("⚠️ No matches found in database")
        
        # Step 2: Always check the knowledge base for additional matches
        print("📚 Checking knowledge base for comprehensive coverage...")
        kb_matches = self._kb_fallback_selection(requirement)
        
        if kb_matches:
            print(f"📙 Found {len(kb_matches)} potential matches in knowledge base")
        else:
            print("⚠️ No matches found in knowledge base")
        
        # Step 3: Combine and rank all matches
        all_matches = self._combine_and_rank_matches(database_matches, kb_matches, requirement)
        
        print(f"✅ Combined search complete. Found {len(all_matches)} total matches")
        return all_matches[:5]  # Return top 5 matches
    
    def _get_candidate_meters(self, cursor, requirement: MeterRequirement) -> List[Dict]:
        """Use Qwen for intelligent SQL query generation with better error handling"""
        
        # Use Qwen to generate SQL query strategy
        search_prompt = f"""
        Generate SQL query conditions to find relevant meters from a database.
        
        Requirements:
        - Clause: {requirement.clause_id}
        - Type: {requirement.meter_type}
        - Specifications: {'; '.join(requirement.specifications)}
        
        Database schema:
        - Table: Products
        - Columns: ProductID, ModelNumber, ProductDescription, MID_Certified
        
        IMPORTANT: Only use these exact column names: ProductID, ModelNumber, ProductDescription, MID_Certified.
        Do NOT reference columns that don't exist in the schema.
        
        Available meter families:
        - PM8xxx: Advanced power quality meters with harmonics
        - PM5xxx: Versatile power meters with communication
        - PM2xxx: Basic power and energy meters
        - iEMxxx: Energy meters for billing applications
        - IONxxx: High-end power quality instruments
        
        Generate SQL WHERE conditions as JSON:
        {{
            "conditions": [
                "LOWER(ModelNumber) LIKE 'pm8%'",
                "LOWER(ProductDescription) LIKE '%harmonic%'"
            ],
            "reasoning": "Why these conditions match the requirements"
        }}
        """
        
        try:
            # Use Qwen for SQL query generation
            print("🔍 Qwen generating database query...")
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": search_prompt}],
                options={"temperature": 0.2}  # Add this parameter for more precise responses
            )
            
            ai_content = response['message']['content']
            json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
            
            if json_match:
                search_criteria = json.loads(json_match.group())
                conditions = search_criteria.get('conditions', [])
                
                # ADDED: Validate conditions to prevent SQL errors
                valid_columns = ['ProductID', 'ModelNumber', 'ProductDescription', 'MID_Certified']
                safe_conditions = []
                
                for condition in conditions:
                    is_valid = True
                    for col in valid_columns:
                        if col in condition:
                            safe_conditions.append(condition)
                            break
                
                if safe_conditions:
                    conditions = safe_conditions
                    print(f"🤖 SQL Strategy: {search_criteria.get('reasoning', 'AI-determined')}")
                else:
                    print("⚠️ Qwen generated invalid SQL conditions, using fallback")
                    conditions = self._fallback_conditions()
                    
            else:
                print("⚠️ Qwen query generation failed, using fallback")
                conditions = self._fallback_conditions()
                
        except Exception as e:
            print(f"⚠️ Qwen query generation failed: {e}")
            conditions = self._fallback_conditions()
        
        # Ensure we have valid conditions
        if not conditions:
            conditions = self._fallback_conditions()
        
        # Execute the AI-generated query
        try:
            query = f"""
            SELECT ProductID, ModelNumber, ProductDescription, MID_Certified
            FROM Products
            WHERE {' OR '.join(conditions)}
            ORDER BY ModelNumber
            LIMIT 25
            """
            
            cursor.execute(query)
            results = []
            for row in cursor.fetchall():
                results.append({
                    'ProductID': row[0],
                    'ModelNumber': row[1],
                    'ProductDescription': row[2],
                    'MID_Certified': row[3]
                })
            
            return results
        except sqlite3.Error as e:
            print(f"⚠️ SQL Error: {e}")
            print("Using basic product query fallback...")
            
            # Super safe fallback if SQL fails
            cursor.execute("""
                SELECT ProductID, ModelNumber, ProductDescription, MID_Certified
                FROM Products
                LIMIT 25
            """)
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'ProductID': row[0],
                    'ModelNumber': row[1],
                    'ProductDescription': row[2],
                    'MID_Certified': row[3]
                })
            
            return results
    def _verify_model_exists(self, model_number: str, candidates: List[Dict] = None) -> bool:
        """Verify that a model number exists in our database or predefined list"""
        # First check if it's in the provided candidates list
        if candidates:
            if any(m['ModelNumber'] == model_number for m in candidates):
                return True
        
        # Check against the database
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM Products WHERE ModelNumber = ?", (model_number,))
                if cursor.fetchone()[0] > 0:
                    return True
        except Exception as e:
            print(f"⚠️ Database verification error: {e}")
        
        # Check against known valid models list
        valid_models = [
            # ION series - only what actually exists
            "ION9000", "ION9000T", 
            
            # PM8000 series
            "PM8140", "PM8143", "PM8144",
            "PM8240", "PM8243", "PM8244",
            "PM8340", "PM8341", "PM8342", "PM8343", "PM8344",
            
            # PM5000 series  
            "PM5100", "PM5110", "PM5111",
            "PM5300", "PM5310", "PM5320", "PM5330", "PM5340", "PM5341",
            "PM5560", "PM5561", "PM5562", "PM5563", "PM5580",
            
            # PM2000 series
            "PM2100", "PM2110", "PM2120", "PM2130",
            "PM2200", "PM2210", "PM2220", "PM2230",
            
            # iEM series
            "iEM3150", "iEM3155", "iEM3250", "iEM3255",
            "iEM3350", "iEM3355", "iEM3455", "iEM3555"
        ]
        
        # Check exact match
        if model_number in valid_models:
            return True
        
        # Additional fuzzy matching for series wildcards
        if model_number.endswith("xx"):
            prefix = model_number[:-2]
            if any(m.startswith(prefix) for m in valid_models):
                return True
        
        print(f"⚠️ Model validation: {model_number} does not exist in our product lineup")
        return False

    def _fallback_conditions(self) -> List[str]:
        """Fallback SQL conditions if AI fails"""
        return [
            "LOWER(ProductDescription) LIKE '%power%'",
            "LOWER(ProductDescription) LIKE '%meter%'",
            "LOWER(ProductDescription) LIKE '%quality%'",
            "LOWER(ProductDescription) LIKE '%monitoring%'",
            "LOWER(ProductDescription) LIKE '%energy%'"
        ]
    
    def _ai_rank_meters(self, requirement: MeterRequirement, candidates: List[Dict]) -> List[MeterMatch]:
        """Use Qwen for contextual meter ranking with strict model verification"""
        
        # Format specifications clearly
        formatted_specs = "\n".join([f"- {spec}" for spec in requirement.specifications])
        
        # Format candidate meters for AI
        meter_options = "\n".join([
            f"- {m['ModelNumber']}: {m['ProductDescription'][:120]}..."
            for m in candidates
        ])
        
        # Create allowed model list for verification
        allowed_models = [m['ModelNumber'] for m in candidates]
        allowed_models_text = ", ".join(allowed_models[:20])  # Limit to first 20 for brevity
        
        prompt = f"""
You are an electrical engineer selecting the most APPROPRIATE power meters for industrial applications. 
Consider both technical compliance AND value (avoid over-engineering).

REQUIREMENT DETAILS:
Clause: {requirement.clause_id}
Application Type: {requirement.meter_type}

SPECIFICATIONS REQUIRED:
{formatted_specs}

AVAILABLE METER OPTIONS:
{meter_options}

STRICT MODEL NUMBER CONSTRAINT:
You MUST ONLY select from these EXACT model numbers: {allowed_models_text}
DO NOT modify, combine, or invent model numbers!

SELECTION CRITERIA:
1. Match complexity level to actual requirements (don't over-specify)
2. Consider cost-effectiveness in your recommendation
3. Select meter by series using these guidelines:
   - Basic monitoring applications → PM2xxx series (lowest cost)
   - Standard monitoring applications → PM5xxx series (mid-range)
   - Advanced power quality analysis → PM8xxx series (higher cost)  
   - Energy billing applications → iEMxxx series (specialized use)
   - High-end power quality/compliance → IONxxx series (premium cost)

IMPORTANT VALUE GUIDELINES:
- Prioritize cost-effective solutions unless advanced features are required
- Example: A mid-range meter that is 90% compliant is often a better engineering choice than a top-tier model that is 100% compliant but significantly more expensive.
- ONLY recommend high-cost meters when requirements CLEARLY demand those capabilities
- If requirements mention "economical", "cost-effective", or "basic monitoring", favor lower-cost models
- If requirements are silent on advanced features, prefer mid-range options (PM5000)
- ONLY select premium options (ION9000) when high-precision or advanced PQ analysis is required

Respond in JSON format:
{{
    "analysis": "Brief analysis of the application requirements and complexity level",
    "cost_consideration": "Your assessment of the appropriate price-performance point based on requirements",
    "rankings": [
        {{
            "model": "EXACT_MODEL_NUMBER_FROM_LIST",
            "score": 85,
            "value_score": 90, 
            "fit_reasoning": "Specific reasons why this meter is appropriate",
            "value_reasoning": "Why this provides the best value for these requirements",
            "specification_match": "How well it meets the key specifications"
        }}
    ]
}}

VERIFICATION STEP REQUIRED: Double-check that every model number you recommend exists EXACTLY in the available meter options list.
"""
    
        try:
            # Use Qwen for analysis and ranking
            print("🧠 Qwen analyzing meter compatibility with value consideration...")
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2}
            )
            
            # Parse AI response
            ai_content = response['message']['content']
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
            if json_match:
                ai_analysis = json.loads(json_match.group())
                
                # VALIDATION: Check that all recommended models exist in the candidates list
                invalid_models = []
                valid_rankings = []
                
                for ranking in ai_analysis.get('rankings', []):
                    model_number = ranking.get('model', '')
                    if not any(m['ModelNumber'] == model_number for m in candidates):
                        print(f"⚠️ AI recommended non-existent model: {model_number}")
                        invalid_models.append(model_number)
                    else:
                        valid_rankings.append(ranking)
                
                # Replace original rankings with validated ones
                if invalid_models:
                    print(f"⚠️ Removed {len(invalid_models)} invalid model recommendations")
                    ai_analysis['rankings'] = valid_rankings
                    
                    # If all models were invalid, fall back to simple ranking
                    if not valid_rankings:
                        print("⚠️ All AI recommended models were invalid, using fallback")
                        return self._fallback_ranking(candidates, requirement)
                
                return self._convert_ai_rankings(ai_analysis, candidates, requirement)
            else:
                print("⚠️ Qwen analysis parsing failed, using fallback ranking")
                return self._fallback_ranking(candidates, requirement)
                
        except Exception as e:
            print(f"⚠️ Qwen analysis failed ({e}), using fallback ranking")
            return self._fallback_ranking(candidates, requirement)
    
    def _convert_ai_rankings(self, ai_analysis: Dict, candidates: List[Dict], requirement: MeterRequirement) -> List[MeterMatch]:
        """Convert AI rankings to MeterMatch objects with value consideration"""
        results = []
        
        # Create lookup for candidate details
        candidate_lookup = {m['ModelNumber']: m for m in candidates}
        
        for ranking in ai_analysis.get('rankings', []):
            model_number = ranking.get('model', '')
            if model_number in candidate_lookup:
                meter_info = candidate_lookup[model_number]
                
                # Include value assessment in reasoning
                value_reasoning = ranking.get('value_reasoning', '')
                combined_reasoning = ranking.get('fit_reasoning', '')
                
                if value_reasoning:
                    combined_reasoning += f" Value consideration: {value_reasoning}"
                
                # Use normal score or combine with value score if available
                score = ranking.get('score', 50)
                value_score = ranking.get('value_score', score)
                
                # Weight technical fit and value equally
                combined_score = int((score + value_score) / 2)
                
                # Use Qwen to analyze specification compliance
                spec_compliance = self._analyze_spec_compliance_with_ai(
                    requirement.specifications, 
                    meter_info['ProductDescription']
                )
                
                results.append(MeterMatch(
                    product_id=str(meter_info['ProductID']),
                    model_number=model_number,
                    description=meter_info['ProductDescription'],
                    score=combined_score,
                    reasoning=combined_reasoning,
                    spec_compliance=spec_compliance
                ))
    
        return results
    
    def _analyze_spec_compliance_with_ai(self, requirements: List[str], meter_description: str) -> Dict[str, str]:
        """Use Qwen to analyze specification compliance with proper error handling"""
    
        compliance_prompt = f"""
Analyze how well this meter meets the specific requirements.

REQUIREMENTS:
{chr(10).join([f"- {req}" for req in requirements])}

METER DESCRIPTION:
{meter_description}

For each requirement, assess compliance and respond with JSON:
{{
    "compliance": {{
        "Requirement 1": "✓ Fully supported - explanation",
        "Requirement 2": "? Needs verification - explanation", 
        "Requirement 3": "✗ Not supported - explanation"
    }}
}}

Use:
✓ = Clearly supported
? = Needs verification/unclear
✗ = Not supported
"""
    
        try:
            # Use Qwen for compliance analysis
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": compliance_prompt}]
            )
    
            ai_content = response['message']['content']
            json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
            
            if json_match:
                compliance_data = json.loads(json_match.group())
                return compliance_data.get('compliance', {})
            else:
                return self._basic_spec_compliance(requirements, meter_description)
            
        except Exception as e:
            print(f"⚠️ AI compliance analysis failed: {e}")
            return self._basic_spec_compliance(requirements, meter_description)
    
    def _fallback_ranking(self, candidates: List[Dict], requirement: MeterRequirement) -> List[MeterMatch]:
        """Ultra-reliable fallback ranking with value consideration and strict model verification"""
        
        # Extract keywords to assess requirements complexity
        req_text = ' '.join(requirement.specifications).lower()
        
        # Check if there are keywords suggesting cost-sensitivity
        cost_sensitive = any(term in req_text for term in [
            'economic', 'cost-effective', 'basic', 'simple', 'budget', 'affordable'
        ])
        
        # Check if there are keywords suggesting high-end needs
        high_end = any(term in req_text for term in [
            'precision', 'high accuracy', 'class 0.1', 'advanced power quality', 
            'extensive analysis', 'comprehensive', 'harmonic'
        ])
        
        # Create allowed model list for verification
        allowed_models = [m['ModelNumber'] for m in candidates]
        allowed_models_text = ", ".join(allowed_models[:15])  # Limit to first 15
        
        fallback_prompt = f"""
        Rank these power meters for the given requirements with VALUE CONSIDERATION.
        
        Requirements: {requirement.meter_type}
        Key Specifications: {'; '.join(requirement.specifications[:5])}
        Cost-sensitive requirements: {"Yes" if cost_sensitive else "No"}
        High-end requirements: {"Yes" if high_end else "No"}
        
        STRICT MODEL NUMBER CONSTRAINT:
        You MUST ONLY select from these EXACT model numbers: {allowed_models_text}
        
        Available meters:
        {chr(10).join([f"- {m['ModelNumber']}: {m['ProductDescription'][:100]}..." for m in candidates[:10]])}
        
        SELECTION GUIDELINES:
        - PM2000 series: Basic monitoring (lowest cost)
        - PM5000 series: Standard monitoring (moderate cost)
        - PM8000 series: Advanced PQ monitoring (higher cost)
        - iEMxxx series: Energy/billing applications
        - ION9000 series: Premium PQ monitoring (highest cost)
        
        Respond with simple JSON:
        {{
            "rankings": [
                {{
                    "model": "EXACT_MODEL_FROM_LIST", 
                    "score": 85, 
                    "reasoning": "Good fit because...",
                    "value_assessment": "Provides good value because..."
                }}
            ]
        }}
        
        VERIFICATION REQUIRED: Ensure every model number exists EXACTLY as listed above.
        IMPORTANT: Balance technical capability with cost-effectiveness. Don't over-specify.
        """
    
        try:
            print("🔄 Using fallback AI ranking with value consideration...")
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": fallback_prompt}],
                options={"temperature": 0.2}
            )
            
            ai_content = response['message']['content']
            json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
            
            if json_match:
                fallback_analysis = json.loads(json_match.group())
                
                # VALIDATION: Check that all recommended models exist in the candidates list
                valid_rankings = []
                for ranking in fallback_analysis.get('rankings', []):
                    model_number = ranking.get('model', '')
                    if any(m['ModelNumber'] == model_number for m in candidates):
                        valid_rankings.append(ranking)
                    else:
                        print(f"⚠️ Fallback AI recommended non-existent model: {model_number}")
                
                # Replace with valid rankings
                fallback_analysis['rankings'] = valid_rankings
                
                if valid_rankings:
                    return self._convert_fallback_rankings(fallback_analysis, candidates, requirement)
        
        except Exception as e:
            print(f"⚠️ Fallback AI ranking failed: {e}")
    
        # Final emergency fallback - rule-based selection
        print("🔄 Using emergency rule-based selection")
        emergency_matches = []
        
        # Group candidates by series
        pm2_models = [m for m in candidates if "PM2" in m['ModelNumber']]
        pm5_models = [m for m in candidates if "PM5" in m['ModelNumber']]
        pm8_models = [m for m in candidates if "PM8" in m['ModelNumber']]
        ion_models = [m for m in candidates if "ION" in m['ModelNumber']]
        iem_models = [m for m in candidates if "IEM" in m['ModelNumber'].upper()]
        
        # Select based on requirement type
        if cost_sensitive:
            model_groups = [pm2_models, pm5_models, iem_models, pm8_models, ion_models]
            reasoning = "Selected for cost-effectiveness based on requirements"
        elif high_end:
            model_groups = [pm8_models, ion_models, pm5_models, pm2_models, iem_models]
            reasoning = "Selected to meet advanced technical requirements"
        else:
            model_groups = [pm5_models, pm8_models, pm2_models, ion_models, iem_models]
            reasoning = "Selected for balanced performance and value"
        
        # Take first model from each group
        for group in model_groups:
            if group:
                model = group[0]
                emergency_matches.append(MeterMatch(
                    product_id=str(model['ProductID']),
                    model_number=model['ModelNumber'],
                    description=model['ProductDescription'],
                    score=70,  # Medium confidence score
                    reasoning=reasoning,
                    spec_compliance={}
                ))
        
        # Return whatever we found (or empty list if nothing)
        return emergency_matches
    
    def _kb_fallback_selection(self, requirement: MeterRequirement) -> List[MeterMatch]:
        """Use local knowledge base with value consideration"""
        print("🔄 Using knowledge base fallback for meter selection with value assessment...")
        
        # Extract keywords to assess requirements complexity
        req_text = ' '.join(requirement.specifications).lower()
        
        # Check if there are keywords suggesting cost-sensitivity
        cost_sensitive = any(term in req_text for term in [
            'economic', 'cost-effective', 'basic', 'simple', 'budget', 'affordable'
        ])
        
        # Check if there are keywords suggesting high-end needs
        high_end = any(term in req_text for term in [
            'precision', 'high accuracy', 'class 0.1', 'advanced power quality', 
            'extensive analysis', 'comprehensive', 'harmonic'
        ])
        
        # Load knowledge base
        kb_path = "meter_specifications_kb_detailed.json"
        try:
            if not os.path.exists(kb_path):
                print(f"⚠️ Knowledge base not found at {kb_path}")
                return []
                
            with open(kb_path, 'r') as f:
                try:
                    # Fix common JSON syntax errors before parsing
                    content = f.read()
                    content = re.sub(r',\s*]', ']', content)  # Fix trailing commas in arrays
                    content = re.sub(r',\s*}', '}', content)  # Fix trailing commas in objects
                    product_kb = json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"⚠️ Error parsing knowledge base: {e}")
                    return []
        except Exception as e:
            print(f"⚠️ Error loading knowledge base: {e}")
            return []
        
        # Create a simplified matching prompt to avoid timeouts
        spec_text = "\n".join(requirement.specifications[:3])  # Only first 3 specs
        
        # Simplified series info
        series_names = list(product_kb.keys())[:5]  # Only first 5 series
        
        matching_prompt = f"""
        Match these meter requirements against our product database with VALUE CONSIDERATION.
        
        REQUIREMENTS:
        Type: {requirement.meter_type}
        Specs: {spec_text}
        Cost-sensitive requirements: {"Yes" if cost_sensitive else "No"}
        High-end requirements: {"Yes" if high_end else "No"}
        
        AVAILABLE SERIES: {', '.join(series_names)}
        
        SERIES VALUE COMPARISON:
        - PM2000: Basic monitoring (lowest cost)
        - PM5000: Standard monitoring (moderate cost)
        - PM8000: Advanced monitoring (higher cost)
        - ION9000: Premium monitoring (highest cost)
        
        Return JSON with top matches:
        {{
            "matches": [
                {{
                    "series": "PM5000_Series",
                    "model": "PM5560",
                    "score": 85,
                    "reasoning": "Brief explanation",
                    "value_assessment": "Good value - meets requirements without excessive cost"
                }}
            ]
        }}
        
        IMPORTANT: Balance technical capability with cost-effectiveness. Don't over-specify.
        If requirements mention economy or are basic, favor lower-cost options.
        """
        
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": matching_prompt}],
                options={"temperature": 0.2}  # Add this parameter for more precise responses
            )
            
            ai_content = response['message']['content']
        
            json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
            
            if json_match:
                try:
                    json_str = json_match.group()
                    # Fix any potential JSON errors in AI response
                    json_str = re.sub(r',\s*]', ']', json_str)
                    json_str = re.sub(r',\s*}', '}', json_str)
                    matching_result = json.loads(json_str)
                    matches = matching_result.get("matches", [])
                    
                    if matches:
                    # Convert to MeterMatch objects WITH VERIFICATION
                        valid_matches = []
                        for match in matches:
                            model_number = match.get("model", "Unknown Model")
                            # Verify the model exists before including it
                            if self._verify_model_exists(model_number):
                                valid_matches.append(MeterMatch(
                                    product_id="KB_" + model_number,
                                    model_number=model_number,
                                    description=f"From {match.get('series', 'Unknown Series')}",
                                    score=match.get("score", 60),
                                    reasoning=match.get("reasoning", "")
                                ))
                            else:
                                print(f"⚠️ KB recommended non-existent model: {model_number}")
                        
                        return valid_matches
                    
                except Exception as e:
                    print(f"⚠️ Error querying ollama: {e}")
                    return []
                
        except Exception as e:
            print(f"⚠️ Error querying ollama: {e}")
            return []
    
    def _combine_and_rank_matches(self, db_matches: List[MeterMatch], kb_matches: List[MeterMatch], 
                         requirement: MeterRequirement) -> List[MeterMatch]:
        """Combine and rank matches from database and knowledge base with value consideration"""
        
        # Check for value-oriented keywords in requirements
        req_text = ' '.join(requirement.specifications).lower()
        is_cost_sensitive = any(term in req_text for term in [
            'economic', 'cost-effective', 'basic', 'simple', 'budget', 'affordable'
        ])
        needs_advanced_features = any(term in req_text for term in [
            'precision', 'high accuracy', 'class 0.1', 'advanced power quality', 
            'extensive analysis', 'comprehensive', 'harmonic'
        ])
        
        # Combine all matches
        all_matches = db_matches + kb_matches
        
        if not all_matches:
            return []
        
        # If we only have matches from one source, adjust scores based on value considerations
        if not db_matches or not kb_matches:
            # Adjust scores based on value considerations
            for match in all_matches:
                # Apply value-oriented score adjustments
                original_score = match.score
                model_number = match.model_number.upper()
                
                # Value-based score adjustments
                if is_cost_sensitive:
                    # Boost lower-cost options when cost sensitivity is detected
                    if "PM2" in model_number:
                        match.score = min(100, int(original_score * 1.3))  # Boost PM2000 series
                        match.reasoning += " (Selected for cost-effectiveness)"
                    elif "PM5" in model_number:
                        match.score = min(100, int(original_score * 1.1))  # Slightly boost PM5000
                    elif "PM8" in model_number:
                        match.score = max(30, int(original_score * 0.8))  # Penalize higher cost PM8000
                    elif "ION9" in model_number:
                        match.score = max(20, int(original_score * 0.6))  # Heavily penalize premium ION9000
                    
                elif needs_advanced_features:
                    # Boost advanced options when high-end requirements detected
                    if "ION9" in model_number:
                        match.score = min(100, int(original_score * 1.3))  # Boost premium ION9000
                        match.reasoning += " (Selected for advanced capabilities)"
                    elif "PM8" in model_number:
                        match.score = min(100, int(original_score * 1.2))  # Boost advanced PM8000
                    elif "PM5" in model_number:
                        match.score = int(original_score)  # Keep PM5000 the same
                    elif "PM2" in model_number:
                        match.score = max(30, int(original_score * 0.7))  # Penalize basic PM2000
            
            return sorted(all_matches, key=lambda x: x.score, reverse=True)
        
        # When we have matches from both sources, re-rank them for fair comparison
        spec_text = "\n".join(requirement.specifications[:3])  # Only first 3 specs
        
        # Prepare match details for ranking with value consideration
        match_details = []
        for i, match in enumerate(all_matches):
            source = "Database" if match.product_id.isdigit() else "Knowledge Base"
            series = "Unknown"
            if "PM2" in match.model_number: series = "PM2000 (Basic)"
            elif "PM5" in match.model_number: series = "PM5000 (Standard)"
            elif "PM8" in match.model_number: series = "PM8000 (Advanced)"
            elif "ION9" in match.model_number: series = "ION9000 (Premium)"
            elif "IEM" in match.model_number.upper(): series = "iEM (Energy)"
            
            match_details.append({
                "index": i,
                "model": match.model_number,
                "series": series,
                "description": match.description[:200],  # Limit length for prompt
                "score": match.score,
                "source": source
            })
        
        # Create prompt for fair ranking with value consideration
        ranking_prompt = f"""
        Rank these meter models based on both TECHNICAL FIT and VALUE FOR MONEY.

        REQUIREMENTS:
        Type: {requirement.meter_type}
        Specifications (partial):
        {spec_text}
        Cost-sensitive requirements: {"Yes" if is_cost_sensitive else "No"}
        Needs advanced features: {"Yes" if needs_advanced_features else "No"}

        AVAILABLE METERS:
        {json.dumps(match_details, indent=2)}

        SERIES VALUE COMPARISON:
        - PM2000: Basic monitoring (lowest cost)
        - PM5000: Standard monitoring (moderate cost)
        - PM8000: Advanced monitoring (higher cost)
        - ION9000: Premium monitoring (highest cost)

        Return a JSON array of models in descending order of OVERALL SUITABILITY:
        [
            {{"index": 2, "final_score": 95, "value_reasoning": "Best balance of features and cost"}},
            {{"index": 0, "final_score": 85, "value_reasoning": "Over-specified for these basic requirements"}}
        ]
        
        IMPORTANT: Don't just select the highest spec meter! Balance technical capability with cost-effectiveness.
        If requirements are basic, favor lower-cost options like PM2000/PM5000.
        If requirements need advanced features, then consider PM8000/ION9000.
        """
        
        try:
            print("🏆 Re-ranking combined matches with value consideration...")
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": ranking_prompt}],
                options={"temperature": 0.2}
            )
            
            ai_content = response['message']['content']
            json_match = re.search(r'\[.*\]', ai_content, re.DOTALL)
            
            if json_match:
                # Get the re-ranked indices
                final_ranking = json.loads(json_match.group())
                
                # Build the final sorted list using the indices and new scores
                final_matches = []
                for rank_info in final_ranking:
                    idx = rank_info.get("index")
                    if 0 <= idx < len(all_matches):
                        match = all_matches[idx]
                        # Update the score with the new value
                        match.score = rank_info.get("final_score", match.score)
                        
                        # Add value reasoning if provided
                        value_reasoning = rank_info.get("value_reasoning", "")
                        if value_reasoning:
                            match.reasoning += f" Value assessment: {value_reasoning}"
                        
                        final_matches.append(match)
                
                # Add any remaining matches not explicitly ranked
                ranked_indices = {r.get("index") for r in final_ranking}
                for i, match in enumerate(all_matches):
                    if i not in ranked_indices:
                        final_matches.append(match)
                        
                return final_matches
                
            else:
                # Apply basic value-oriented scoring as fallback
                for match in all_matches:
                    model_number = match.model_number.upper()
                    original_score = match.score
                    
                    if is_cost_sensitive:
                        if "PM2" in model_number:
                            match.score = min(100, int(original_score * 1.3))
                        elif "ION9" in model_number:
                            match.score = max(20, int(original_score * 0.6))
                
                # Sort by adjusted scores
                return sorted(all_matches, key=lambda x: x.score, reverse=True)
                
        except Exception as e:
            print(f"⚠️ Error during match re-ranking: {e}")
            # Fallback: sort by original scores
            return sorted(all_matches, key=lambda x: x.score, reverse=True)

class DocumentParser:
    """Clean document parsing for tender files using Qwen"""
    
    @staticmethod
    def read_document(file_path: str) -> str:
        """Read text document (no PDF support needed for this workflow)"""
        file_path = file_path.strip('"\'')
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

    @staticmethod
    def extract_meter_requirements(text: str, manual_clauses: List[str]) -> List['MeterRequirement']:
        """Extract only the specified clauses from the document."""
        lines = text.split('\n')
        section_pattern = re.compile(r'^([A-Za-z]?\d+(\.\d+)*)([)\.]|\s)\s*(.+)?$')
        manual_clauses_set = set(str(c).strip() for c in manual_clauses)
        clause_positions = []
        for idx, line in enumerate(lines):
            match = section_pattern.match(line.strip())
            if match:
                section_id = match.group(1)
                title = match.group(4) or ""
                if section_id in manual_clauses_set:
                    clause_positions.append((section_id, idx, title.strip()))
        clause_positions.sort(key=lambda x: x[1])
        requirements = []
        for i, (section_id, start_idx, title) in enumerate(clause_positions):
            end_idx = clause_positions[i+1][1] if i+1 < len(clause_positions) else len(lines)
            content = "\n".join(lines[start_idx:end_idx])
            # Use your Qwen-powered extraction for each clause section
            req = DocumentParser._parse_meter_section({
                "clause_id": section_id,
                "title": title,
                "content": content,
                "meter_category": "Unknown"
            })
            if req:
                requirements.append(req)
        return requirements

    @staticmethod
    def _find_meter_sections(text: str) -> List[Dict]:
        """Efficient, dynamic section detection and grouping for tender documents."""
        lines = text.split('\n')
        section_headers = []
        section_pattern = re.compile(r'^([A-Za-z]?\d+(\.\d+)*)([)\.]|\s)\s*(.+)?$')
        for idx, line in enumerate(lines):
            match = section_pattern.match(line.strip())
            if match:
                section_id = match.group(1)
                title = match.group(4) or ""
                context = " ".join(lines[max(0, idx-2):min(len(lines), idx+3)]).lower()
                if any(k in context for k in [
                    "meter", "power quality", "energy", "monitor", "instrument", "specification", "digital"
                ]):
                    section_headers.append({
                        "clause_id": section_id,
                        "title": title.strip(),
                        "line_number": idx
                    })

        # Group by top-level (e.g., 6, 7, 8) or by major clause (e.g., 6.5)
        grouped = {}
        for sh in section_headers:
            # Use first two levels as parent (e.g., 6.5 for 6.5.1)
            parent = ".".join(sh["clause_id"].split('.')[:2])
            grouped.setdefault(parent, []).append(sh)

        # Only keep the parent section if it has multiple children or is long
        sections = []
        for parent, subs in grouped.items():
            # If only one sub, just use it
            if len(subs) == 1:
                sh = subs[0]
                start = sh["line_number"]
                end = subs[1]["line_number"] if len(subs) > 1 else len(lines)
                content = "\n".join(lines[start:end])
                sections.append({
                    "clause_id": sh["clause_id"],
                    "title": sh["title"],
                    "content": content,
                    "meter_category": "Unknown"
                })
            else:
                # Combine all subs under the parent
                start = subs[0]["line_number"]
                end = subs[-1]["line_number"] + 1
                content = "\n".join(lines[start:end])
                sections.append({
                    "clause_id": parent,
                    "title": f"Combined requirements for {parent}",
                    "content": content,
                    "meter_category": "Unknown"
                })
        return sections

    @staticmethod
    def _parse_meter_section(section: Dict) -> Optional[MeterRequirement]:
        """Improved parsing with better hierarchical structure handling"""
        content = section['content']
        clause_id = section['clause_id']
        title = section['title']
        
        print(f"\n--- Parsing {clause_id} ---")
        print(f"Content length: {len(content)} characters")
        print(f"First 100 chars: {content[:100].replace('\n', ' ')}")

        # Determine if this is a main section or subsection
        section_level = len(clause_id.split('.'))
        
        # Extract meter type from section title if present
        explicit_meter_type = None
        title_lower = title.lower()
        
        # Check for explicit meter types in the title
        meter_type_patterns = {
            "Power Quality Meter": ["power quality meter", "pqm", "quality"],
            "Digital Power Meter": ["digital power meter", "dpm", "digital meter"],
            "Multi-Function Meter": ["multi-function", "multifunction", "multi function"],
            "Energy Meter": ["energy meter", "billing meter", "revenue meter"],
            "Basic Power Meter": ["basic meter", "basic power"]
        }
        
        for meter_type, patterns in meter_type_patterns.items():
            if any(pattern in title_lower for pattern in patterns):
                explicit_meter_type = meter_type
                print(f"📌 Explicit meter type found in title: {explicit_meter_type}")
                break
        
        # Special case for top-level sections like "6.0 POWER QUALITY METER SPECIFICATIONS"
        if "specification" in title_lower:
            for meter_type, patterns in meter_type_patterns.items():
                if any(pattern in title_lower for pattern in patterns):
                    explicit_meter_type = meter_type
                    print(f"📌 Specification section found for: {explicit_meter_type}")
                    break
        
        # Use Qwen to extract specifications with improved prompt
        parsing_prompt = f"""
Analyze this tender clause {clause_id} and extract the electrical meter specifications.

Clause ID: {clause_id}
Clause Title: {title}
Clause Content:
{content}

CONTEXT:
This appears to be {'a main section' if section_level <= 2 else 'a subsection'} in a tender document.
{f"The title indicates this is about a {explicit_meter_type}" if explicit_meter_type else ""}

TASK:
1. Extract ONLY the technical specifications for electrical meters from this section
2. Format each specification as a clear, concise requirement
3. Combine related sub-points into a single coherent specification where appropriate
4. Focus on electrical, communication, accuracy & certification requirements

IMPORTANT NOTES:
- For main sections like "6.0" or "8.0", focus on extracting the key requirements
- For subsections like "6.5" or "8.2", extract the detailed specifications
- If the section contains multiple sub-clauses (e.g., 6.5.1, 6.5.2), combine them logically
- Skip any general or procedural text that doesn't directly specify meter requirements 

REQUIRED OUTPUT FORMAT:
Return JSON with the specifications and meter type:
{{
    "specifications": [
        "Voltage Accuracy ±0.1%",
        "Current Accuracy ±0.1%",
        "Frequency Accuracy ±0.005Hz",
        "Class A Power Analyzer with IEC 61000-4-30 compliance"
    ],
    "meter_type": "Power Quality Meter",
    "has_sufficient_specs": true,
    "reasoning": "This section clearly describes a power quality meter with detailed accuracy requirements"
}}

If the title explicitly mentions a specific meter type, prefer that type unless the specifications clearly indicate otherwise.
"""

        try:
            response = ollama.chat(
                model="qwen2.5-coder:7b",
                messages=[{"role": "user", "content": parsing_prompt}]
            )
            
            ai_content = response['message']['content']
            
            # Clean up response
            ai_content_clean = ai_content.strip()
            if ai_content_clean.startswith('```json'):
                ai_content_clean = ai_content_clean.replace('```json', '').replace('```', '').strip()
            
            json_match = re.search(r'\{.*\}', ai_content_clean, re.DOTALL)
            
            if json_match:
                parsing_result = json.loads(json_match.group())
                
                specs = parsing_result.get('specifications', [])
                has_sufficient = parsing_result.get('has_sufficient_specs', False)
                
                # Use explicit meter type from title if available, otherwise use AI's determination
                meter_type = explicit_meter_type if explicit_meter_type else parsing_result.get('meter_type', 'Power Meter')
                reasoning = parsing_result.get('reasoning', 'AI analysis')
                
                # Initialize unique_specs
                unique_specs = []
                
                # Validate specs for common issues like cross-contamination
                if has_sufficient and specs:
                    # Check for duplicate/redundant specifications
                    seen_keywords = set()
                    
                    for spec in specs:
                        # Create a simplified version for duplicate detection
                        simple_spec = re.sub(r'[^\w\s]', '', spec.lower())
                        simple_tokens = set(simple_spec.split())
                        
                        # Check if this spec is too similar to ones we've seen
                        if not any(len(simple_tokens.intersection(prev)) > len(simple_tokens) * 0.7 
                                  for prev in seen_keywords):
                            unique_specs.append(spec)
                            seen_keywords.add(frozenset(simple_tokens))
                else:
                    # If there are no sufficient specs, just use what we have
                    unique_specs = specs
        
            print(f"🤖 Qwen extracted {len(unique_specs)}/{len(specs)} unique specifications for {section['clause_id']}")
            print(f"   Meter Type: {meter_type}")
            print(f"   Reasoning: {reasoning}")
            print(f"   Has sufficient specs: {has_sufficient}")
        
            return MeterRequirement(
                clause_id=section['clause_id'],
                meter_type=meter_type,
                specifications=unique_specs,
                content=content
            )
    
        except Exception as e:
            print(f"⚠️ Qwen parsing failed for {section['clause_id']}: {e}")
            return None
        
    @staticmethod
    def extract_variant_specs(model_number: str, variant_sections: List[str], product_info: Dict):
        """Extract detailed specifications for a specific model variant"""
        
        print(f"  Extracting specifications for {model_number}...")
        
        # Format for new organized JSON structure
        series_id = re.sub(r'(\d+)[A-Z0-9]*$', r'\1_Series', model_number)
        
        # Initialize with empty structure if this series doesn't exist yet
        if series_id not in product_info:
            product_info[series_id] = {
                "model": series_id,
                "summary": "",
                "model_breakdown": [],
                "performance_and_accuracy": [],
                "electrical_characteristics": {},
                "communication": {},
                "display": {},
                "inputs_outputs": {},
                "physical_specifications": {},
                "environmental_conditions": {},
                "certifications": []
            }
        
        # Process each content section specific to this variant
        for i, section in enumerate(variant_sections):
            print(f"    Processing section {i+1}/{len(variant_sections)}...")
            
            # Build the prompt for this section
            spec_prompt = f"""
            # Detailed Specification Extraction for {model_number}
            
            Extract technical specifications for the {model_number} from this document section.
            
            ## DOCUMENT SECTION {i+1}/{len(variant_sections)}:
            {section[:3500]}
            
            ## EXTRACTION INSTRUCTIONS:
            1. Extract ONLY factual specifications for model {model_number} or its series
            2. Use EXACT values and terminology from the document
            3. ONLY extract specifications from THIS document section
            4. Focus on technical specifications, not marketing claims
            
            ## OUTPUT FORMAT:
            Return a structured JSON with the following format:
            
            ```json
            {{
                "series_summary": "Brief overview of the series capabilities and applications",
                "model_variants": [
                    {{
                        "model_name": "{model_number}",
                        "key_differentiator": "Key feature that distinguishes this variant"
                    }},
                    {{
                        "model_name": "Other model in same series",
                        "key_differentiator": "Its distinguishing feature"
                    }}
                ],
                "performance_and_accuracy": [
                    {{
                        "parameter": "Active energy (kWh)",
                        "standard": "IEC 62053-22",
                        "class_or_accuracy": "Class 0.5S"
                    }},
                    {{
                        "parameter": "Reactive energy (kvarh)",
                        "standard": "IEC 62053-23",
                        "class_or_accuracy": "Class 2"
                    }}
                ],
                "electrical_characteristics": {{
                    "nominal_voltage": "100-415 V AC L-L",
                    "operating_frequency": "50/60 Hz",
                    "burden": "< 0.2 VA per phase"
                }},
                "communication": {{
                    "ports": ["RS-485", "Ethernet"],
                    "protocols": ["Modbus RTU", "Modbus TCP"],
                    "baud_rates": ["9600", "19200", "38400"]
                }},
                "display": {{
                    "type": "Backlit LCD",
                    "parameters_displayed": ["Voltage", "Current", "Power", "Energy"]
                }},
                "inputs_outputs": {{
                    "digital_inputs": "4",
                    "digital_outputs": "2",
                    "relay_outputs": "0"
                }},
                "physical_specifications": {{
                    "dimensions": "96 x 96 x 77 mm",
                    "mounting": ["Panel Mount"],
                    "weight": "380 g"
                }},
                "environmental_conditions": {{
                    "operating_temperature": "-25°C to +70°C",
                    "storage_temperature": "-40°C to +85°C",
                    "humidity": "5% to 95% RH non-condensing"
                }},
                "certifications": [
                    {{
                                "type": "Safety",
                                "standard": "IEC 61010-1",
                                "details": "CAT III 300V"
                            }}
                        ]
                    }}
                    ```
                    """
                    
            try:
                print(f"    Analyzing section {i+1}...")
                response = ollama.chat(
                    model="qwen2.5-coder:7b",
                    messages=[{"role": "user", "content": spec_prompt}]
                )
                
                ai_content = response['message']['content']
                json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
                
                if json_match:
                    section_specs = json.loads(json_match.group())
                    
                    # Update the overall series structure
                    series_data = product_info[series_id]
                    
                    # Update series summary if available
                    if "series_summary" in section_specs and not series_data.get("summary"):
                        series_data["summary"] = section_specs["series_summary"]
                    
                    # Merge model variants
                    if "model_variants" in section_specs:
                        existing_models = {item.get("model_name", "") for item in series_data["model_breakdown"]}
                for variant in section_specs["model_variants"]:
                    if variant.get("model_name") not in existing_models:
                        series_data["model_breakdown"].append(variant)
                        existing_models.add(variant.get("model_name", ""))
            
            # Merge performance and accuracy data
                if "performance_and_accuracy" in section_specs:
                    existing_params = {item.get("parameter", "") for item in series_data["performance_and_accuracy"]}
                    for item in section_specs["performance_and_accuracy"]:
                        if item.get("parameter") not in existing_params:
                            series_data["performance_and_accuracy"].append(item)
                            existing_params.add(item.get("parameter", ""))
                
                # Update dictionary-based properties
                dict_properties = ["electrical_characteristics", "communication", 
                                    "display", "inputs_outputs", "physical_specifications", 
                                    "environmental_conditions"]
                
                for prop in dict_properties:
                    if prop in section_specs:
                        if prop not in series_data:
                            series_data[prop] = {}
                        series_data[prop].update(section_specs[prop])
                
                # Merge certifications
                if "certifications" in section_specs:
                    existing_certs = {f"{cert.get('type')}:{cert.get('standard')}" 
                                        for cert in series_data["certifications"]}
                    
                    for cert in section_specs["certifications"]:
                        cert_key = f"{cert.get('type')}:{cert.get('standard')}"
                        if cert_key not in existing_certs:
                            series_data["certifications"].append(cert)
                            existing_certs.add(cert_key)

                    print(f"    ✓ Updated specifications from section {i+1}")
                else:
                    print(f"    ⚠️ Could not extract specifications from section {i+1}")
            except Exception as e:
                print(f"    ⚠️ Error extracting specs from section {i+1}: {e}")


def create_product_knowledge_base(manuals_dir: str) -> str:
    """Create a consolidated knowledge base with improved model variant detection"""
    output_file = "meter_specifications_kb_detailed.json"
    
    # Structure to store extracted product info
    product_info = {}
    # Track which series we've already processed to avoid duplicates
    processed_series = {}
    
    # Process each manual file
    for filename in os.listdir(manuals_dir):
        if filename.endswith(".pdf") or filename.endswith(".txt"):
            file_path = os.path.join(manuals_dir, filename)
            
            # Extract model series from filename
            model_match = re.search(r'(PM\d+|iEM\d+|ION\d+)', filename)
            if not model_match:
                print(f"⚠️ Couldn't determine model series from {filename}, skipping")
                continue
            
            model_series = model_match.group(1)
            print(f"\n==== Processing manual for {model_series} series ====")
            
            # Read document content
            if filename.endswith(".pdf"):
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = "\n".join(page.extract_text() for page in pdf_reader.pages)
                    print(f"  PDF loaded: {len(pdf_reader.pages)} pages, {len(text)} characters")
            else:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                    text = file.read()
                    print(f"  Text file loaded: {len(text)} characters")
            
            # Step 1: Identify model variants in the document - WITH SERIES VALIDATION
            # Extract the series prefix (e.g., "PM8" from "PM8000")
            series_prefix = re.match(r'([A-Za-z]+\d+)', model_series).group(1)
            
            model_variant_prompt = f"""
            # Model Variant Detection Task
            
            Analyze this product documentation for the {model_series} series and identify ALL specific model variants mentioned.
            
            ## TEXT EXCERPT (first section):
            {text[:4000]}
            
            ## INSTRUCTIONS:
            1. Find ONLY model numbers that belong to the {model_series} series
              
               - Valid examples: {model_series}0, {model_series}1, {model_series}2, etc.
               - Models MUST start with "{series_prefix}"
            2. For each variant, extract its brief description if available
            3. DO NOT include generic mentions of the series (like "{model_series} series")
            4. DO NOT include models from other series (e.g. DO NOT include PM8000 models when analyzing ION9000)
            5. Focus on actual product model numbers, not accessories or other products
            
            ## REQUIRED OUTPUT FORMAT:
            ```json
            {{
                "series": "{model_series}",
                "variants": [
                    {{
                        "model": "{model_series}240",
                        "brief_description": "Advanced model with additional features"
                    }},
                    {{
                        "model": "{model_series}243",
                        "brief_description": "Standard model with basic capabilities"
                    }}
                ]
            }}
            ```
            
            IMPORTANT: List ONLY models that belong to the {model_series} series. Models MUST start with "{series_prefix}".
            """
            
            try:
                # If we've already processed this series and found variants, skip model detection
                if model_series in processed_series and processed_series[model_series]:
                    print(f"  ℹ️ Using previously detected variants for {model_series} series")
                    variants_to_process = processed_series[model_series]
                else:
                    print(f"  Identifying model variants in {model_series} series...")
                    response = ollama.chat(
                        model="qwen2.5-coder:7b", 
                        messages=[{"role": "user", "content": model_variant_prompt}],
                        options={"temperature": 0.2}  # Add this parameter for more precise responses
                    )
                    
                    ai_content = response['message']['content']
                    json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
                    
                    variants_to_process = []
                    if json_match:
                        variants_data = json.loads(json_match.group())
                        variants = variants_data.get("variants", [])
                        
                        # Validate that models actually belong to the correct series
                        valid_variants = []
                        for variant in variants:
                            model_num = variant.get("model", "")
                            # Check if model starts with the correct series prefix
                            if model_num.startswith(series_prefix):
                                valid_variants.append(variant)
                            else:
                                print(f"  ⚠️ Ignoring invalid model: {model_num} (not in {model_series} series)")
                        
                        if valid_variants:
                            print(f"  ✓ Found {len(valid_variants)} valid model variants: {', '.join(v['model'] for v in valid_variants)}")
                            variants_to_process = valid_variants
                            # Store for future reference
                            processed_series[model_series] = valid_variants
                        else:
                            print(f"  ⚠️ No valid model variants found, using series model {model_series}")
                            variants_to_process = [{"model": model_series, "brief_description": "Base model"}]
                        processed_series[model_series] = variants_to_process
                    else:
                        print(f"  ⚠️ Failed to parse model variants, using series model {model_series}")
                        variants_to_process = [{"model": model_series, "brief_description": "Base model"}]
                        processed_series[model_series] = variants_to_process
            except Exception as e:
                print(f"  ⚠️ Exception occurred during model variant detection for {model_series}: {e}")
                variants_to_process = [{"model": model_series, "brief_description": "Base model"}]
                processed_series[model_series] = variants_to_process
            
            # Step 2: Process each variant individually
            for variant in variants_to_process:
                model_number = variant["model"]
                
                # Skip if we've already processed this specific model number
                if model_number in product_info:
                    print(f"\n  ℹ️ Skipping already processed model: {model_number}")
                    continue
                    
                print(f"\n  Processing model variant: {model_number}")
                
                # Search for sections specifically about this variant
                variant_sections = []
                
                # Look for sections with this specific model number
                model_pattern = re.escape(model_number)
                matches = list(re.finditer(model_pattern, text))
                
                if matches:
                    print(f"  ✓ Found {len(matches)} mentions of {model_number} in the document")
                    
                    # Extract content around each match (3000 chars before and after)
                    for match in matches[:5]:  # Limit to first 5 matches to avoid excessive processing
                        start_pos = max(0, match.start() - 3000)
                        end_pos = min(len(text), match.start() + 3000)
                        variant_sections.append(text[start_pos:end_pos])
                
                # If no specific sections, use relevant parts of the full text
                if not variant_sections:
                    print(f"  ⚠️ No specific sections for {model_number}, using general text")
                    
                    # Split document into chunks and analyze each
                    chunk_size = 1500
                    overlap = 400
                    for i in range(0, len(text), chunk_size - overlap):
                        chunk = text[i:i+chunk_size]
                        variant_sections.append(chunk)
                
                # Step 3: Extract detailed specifications for this variant
                DocumentParser.extract_variant_specs(model_number, variant_sections, product_info)
    
    # Save the consolidated knowledge base
    with open(output_file, 'w') as f:
        json.dump(product_info, f, indent=2)
    
    print(f"\n✓ Enhanced knowledge base created with {len(product_info)} model variants")
    print(f"  Saved to: {output_file}")


class TenderAnalyzer:
    """Main analyzer class that processes tender documents and recommends meters"""
    
    def __init__(self, database_path: str):
        self.database = MeterDatabase(database_path)
        self.parser = DocumentParser
    
    def analyze_document(self, tender_file: str, manual_clauses: List[str]) -> List[Dict]:
        print(f"📄 Analyzing document: {os.path.basename(tender_file)}")
        doc_text = self.parser.read_document(tender_file)
        print(f"📄 Document loaded: {len(doc_text)} characters")
        requirements = self.parser.extract_meter_requirements(doc_text, manual_clauses)
        print(f"📋 Found {len(requirements)} meter requirements")
        results = []
        for i, req in enumerate(requirements, 1):
            print(f"\n✨ Processing requirement {i}/{len(requirements)}: {req.clause_id}...")
            print(f"📝 Type: {req.meter_type}")
            print(f"📝 Specifications: {len(req.specifications)} items")
            matches = self.database.search_meters(req)
            result = {
                'clause_id': req.clause_id,
                'meter_type': req.meter_type,
                'specifications': req.specifications,
                'selected_meter': matches[0] if matches else None,
                'alternatives': matches[1:3] if len(matches) > 1 else []
            }
            results.append(result)
            if matches:
                top_match = matches[0]
                print(f"✅ Top match: {top_match.model_number} (Score: {top_match.score})")
                print(f"   Reasoning: {top_match.reasoning[:100]}...")
                # Print runner-up if available
                if len(matches) > 1:
                    runner_up = matches[1]
                    print(f"🥈 Runner-up: {runner_up.model_number} (Score: {runner_up.score})")
                    print(f"   Reasoning: {runner_up.reasoning[:100]}...")
            else:
                print("❌ No suitable meters found for this requirement")
        output_file = self.export_to_txt(results, tender_file)
        print(f"\n📊 Analysis complete! Report saved to: {output_file}")
        return results

    def export_to_txt(self, results: List[Dict], tender_file: str) -> str:
        """Export analysis results to a text file with detailed compliance comparison"""
        tender_filename = os.path.basename(tender_file)
        tender_name = os.path.splitext(tender_filename)[0]
        output_filename = f"{tender_name}_meter_analysis.txt"
        
        # Use UTF-8 encoding to handle special characters
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write("# METER SELECTION AND COMPLIANCE ANALYSIS\n\n")
            
            for i, result in enumerate(results, 1):
                clause_id = result['clause_id']
                meter_type = result['meter_type']
                specs = result['specifications']
                
                # Section header with clause ID and requirement type
                f.write(f"## {i}. Clause {clause_id}: {meter_type} Requirements\n\n")
                
                # Display the tender requirements
                f.write("### Tender Requirements\n")
                for spec in specs:
                    f.write(f"- {spec}\n")
                f.write("\n")
                
                # Selected meter analysis
                if result['selected_meter']:
                    meter = result['selected_meter']
                    f.write(f"### Selected Meter: {meter.model_number}\n\n")
                    
                    # Basic meter information
                    f.write(f"**Description**: {meter.description}\n\n")
                    
                    # Specification compliance analysis
                    f.write("### Compliance Analysis\n\n")
                    
                    # If we have detailed spec compliance data
                    if meter.spec_compliance and isinstance(meter.spec_compliance, dict):
                        f.write("| Tender Requirement | Meter Specification | Compliance | Notes |\n")
                        f.write("|-------------------|---------------------|------------|-------|\n")
                        
                        for req in specs:
                            # Find matching spec info if available
                            compliance_info = meter.spec_compliance.get(req, "")
                            
                            # Fix: Handle both dict and string types for compliance_info
                            if isinstance(compliance_info, dict):
                                meter_spec = compliance_info.get('meter_spec', 'No specific information')
                                is_compliant = compliance_info.get('compliant', 'Unknown')
                                notes = compliance_info.get('notes', '')
                            else:
                                # If it's a string, use it directly as compliance info
                                meter_spec = 'Not specified'
                                # Check if the compliance string indicates compliance
                                is_compliant = '✓' in compliance_info if compliance_info else 'Unknown'
                                notes = compliance_info if compliance_info else ''
                            
                            # Format compliance status
                            status = "✅ Compliant" if is_compliant == True or is_compliant == '✓' else "❌ Non-compliant" if is_compliant == False or is_compliant == '✗' else "❓ Unknown"
                            
                            f.write(f"| {req} | {meter_spec} | {status} | {notes} |\n")
                    else:
                        # Simpler format if detailed compliance not available
                        f.write("**Overall Assessment**: The selected meter appears to meet the technical requirements with the following considerations:\n\n")
                        
                        # Extract justifications from reasoning
                        reasoning_points = meter.reasoning.split(". ")
                        for point in reasoning_points:
                            if len(point) > 10:  # Skip very short fragments
                                f.write(f"- {point.strip()}.\n")
                        f.write("\n")
                    
                    # Areas for improvement
                    f.write("### Potential Areas for Improvement\n\n")
                    if "improvement" in meter.reasoning.lower() or "limitation" in meter.reasoning.lower():
                        # Extract improvement notes from reasoning
                        improvements = []
                        lower_reasoning = meter.reasoning.lower()
                        
                        # Look for common phrases that indicate improvements
                        for phrase in ["could be improved", "consider", "recommend", "limit", "issue", "problem"]:
                            if phrase in lower_reasoning:
                                # Find the sentence containing this phrase
                                sentences = re.findall(r'[^.!?]*' + re.escape(phrase) + r'[^.!?]*[.!?]', meter.reasoning, re.IGNORECASE)
                                improvements.extend(sentences)
                        
                        if improvements:
                            for imp in improvements:
                                f.write(f"- {imp.strip()}\n")
                        else:
                            f.write("- No specific improvements suggested, but consider reviewing specifications.\n")
                    else:
                        f.write("- No immediate areas for improvement detected.\n")
                else:
                    f.write("### Selected Meter: **None**\n")
                    f.write("❌ No suitable meter found that meets the requirements.\n")
                
                f.write("\n" + "-"*80 + "\n\n")
        
        return output_filename


# Main execution block with CLI
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Schneider Electric Meter Selection Tool")
    parser.add_argument("--build-kb", action="store_true", 
                       help="Build the knowledge base from product manuals")
    args = parser.parse_args()
    
    # Handle knowledge base creation mode
    if args.build_kb:
        manuals_dir = input("Enter the directory containing meter manuals (PDF/TXT): ")
        if os.path.isdir(manuals_dir):
            create_product_knowledge_base(manuals_dir)
        else:
            print(f"Error: Directory '{manuals_dir}' not found")
        exit(0)
    
    # Normal tender analysis mode
    try:
        # Prompt for the tender document
        tender_file = input("Enter the path to the clause document (TXT): ")
        if not os.path.isfile(tender_file):
            print(f"Error: File '{tender_file}' not found!")
            exit(1)
        
        print("Please enter the clause numbers you want to analyze, separated by commas (e.g. 7.0,8.0):")
        clause_input = input("Clauses: ")
        manual_clauses = [c.strip() for c in clause_input.split(",") if c.strip()]
        
        # Initialize analyzer and process document
        analyzer = TenderAnalyzer("meters.db")
        analyzer.analyze_document(tender_file, manual_clauses)
        
        # Keep console window open for viewing results
        input("\nPress Enter to exit...")
        
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")

def _safe_json_extract(json_text: str) -> Dict:
    """Ultra-robust JSON extraction"""
    # Clean the text aggressively
    cleaned_text = re.sub(r'```json|```', '', json_text)
    cleaned_text = cleaned_text.strip()
    
    # Try multiple patterns to extract JSON
    patterns = [
        r'\{.*\}',  # Standard JSON object
        r'\[.*\]',  # JSON array
        r'(\{[^{]*\})'  # First complete JSON object
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, cleaned_text, re.DOTALL)
        if matches:
            for potential_json in matches:
                try:
                    # Additional cleaning
                    fixed = re.sub(r',\s*([}\]])', r'\1', potential_json)
                    fixed = re.sub(r'([{,]\s*)([a-zA-Z_][^:]*?):', r'\1"\2":', fixed)
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    continue
    
    # Create structured data from unstructured text as last resort
    try:
        # Extract key-value pairs with regex
        specs = re.findall(r'"?([^":]+)"?\s*:\s*"?([^",}]+)"?', cleaned_text)
        if specs:
            return {k.strip('"'): v.strip('"') for k, v in specs}
    except:
        pass
    
    return {"error": "JSON extraction failed", "text": cleaned_text[:100]}

def _extract_accuracy_from_text(text: str):
    """Extract accuracy values from text descriptions for better comparisons"""
    # Check for class X specifications
    class_match = re.search(r'class\s+(\d+\.\d+)\s*s?', text.lower())
    if class_match:
        # Class X.Y means ±X.Y%
        return float(class_match.group(1))
    
    # Check for percentage specifications
    pct_match = re.search(r'[±⁑]\s*(\d+\.?\d*)%', text)
    if pct_match:
        return float(pct_match.group(1))
    
    # Return None if no accuracy specification found
    return None

def _is_accuracy_compliant(requirement: str, specification: str) -> bool:
    """Properly compare accuracy requirements for compliance"""
    req_value = _extract_accuracy_from_text(requirement)
    spec_value = _extract_accuracy_from_text(specification)
    
    if req_value is None or spec_value is None:
        return "Unknown"  # Can't determine compliance
    
    # Lower is better for accuracy (0.2% is better than 0.5%)
    # Meter complies if its accuracy is equal or better than required
    return spec_value <= req_value



