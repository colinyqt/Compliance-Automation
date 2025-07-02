# Comprehensive API Documentation

## Table of Contents

1. [Overview](#overview)
2. [Core Engine API](#core-engine-api)
3. [Database Components](#database-components)
4. [Processing Components](#processing-components)
5. [Output Generation](#output-generation)
6. [Configuration System](#configuration-system)
7. [Legacy Components](#legacy-components)
8. [YAML Template System](#yaml-template-system)
9. [Usage Examples](#usage-examples)
10. [Integration Guide](#integration-guide)

---

## Overview

The YAML Prompt Engine is a comprehensive compliance automation system that processes tender documents, analyzes meter specifications, and generates compliance reports. The system consists of:

- **Core Engine**: Main orchestration and processing engine
- **Database Components**: Auto-discovery and smart database access
- **Processing Components**: LLM integration, file processing, and template analysis
- **Output Generation**: Excel, JSON, and text report generation
- **Legacy Components**: Comparison tools and clause extraction utilities

---

## Core Engine API

### PromptEngine

**Location**: `overhaul/core/prompt_engine.py`

The main orchestration engine that coordinates all components and executes YAML-defined workflows.

#### Constructor

```python
from core import PromptEngine

engine = PromptEngine(
    databases_dir: str = "databases",
    prompts_dir: str = "prompts", 
    outputs_dir: str = "outputs"
)
```

**Parameters:**
- `databases_dir`: Directory containing database files
- `prompts_dir`: Directory containing YAML prompt templates
- `outputs_dir`: Directory for generated outputs

#### Primary Methods

##### `run_prompt(prompt_file: str) -> Dict[str, Any]`

Executes a complete YAML prompt configuration end-to-end.

**Parameters:**
- `prompt_file`: Path to YAML configuration file

**Returns:**
```python
{
    'success': True/False,
    'pipeline_results': Dict[str, Any],  # Results from each processing step
    'output_files': List[str],           # Paths to generated files
    'error': str                         # Error message if success=False
}
```

**Example:**
```python
import asyncio
from core import PromptEngine

async def main():
    engine = PromptEngine()
    result = await engine.run_prompt("prompts/tender_analysis.yaml")
    
    if result['success']:
        print(f"✅ Analysis completed!")
        print(f"Generated files: {result['output_files']}")
    else:
        print(f"❌ Error: {result['error']}")

asyncio.run(main())
```

---

## Database Components

### DatabaseAutoDiscovery

**Location**: `overhaul/core/database_autodiscovery.py`

Automatically discovers database schema and generates intelligent queries.

#### Constructor

```python
from core import DatabaseAutoDiscovery

discovery = DatabaseAutoDiscovery()
```

#### Primary Methods

##### `discover_database(db_path: str) -> DatabaseSchema`

Analyzes database structure and returns comprehensive schema information.

**Parameters:**
- `db_path`: Path to SQLite database file

**Returns:**
```python
@dataclass
class DatabaseSchema:
    path: str
    tables: Dict[str, TableInfo]
    relationships: List[Dict[str, Any]]
    suggested_queries: Dict[str, str]
```

**Example:**
```python
from core import DatabaseAutoDiscovery

discovery = DatabaseAutoDiscovery()
schema = discovery.discover_database("databases/meters.db")

print(f"Found {len(schema.tables)} tables:")
for table_name, table_info in schema.tables.items():
    print(f"  - {table_name}: {len(table_info.columns)} columns, {table_info.row_count} rows")
```

### SmartDatabaseWrapper

**Location**: `overhaul/core/database_autodiscovery.py`

Provides intelligent database access with auto-generated queries.

#### Constructor

```python
from core import SmartDatabaseWrapper, DatabaseAutoDiscovery

discovery = DatabaseAutoDiscovery()
wrapper = SmartDatabaseWrapper("databases/meters.db", discovery)
```

#### Primary Methods

##### `get_all(table_name: str = None) -> List[Dict]`

Retrieves all records from specified table or main table.

**Example:**
```python
# Get all meters
meters = wrapper.get_all("Meters")
print(f"Found {len(meters)} meters")

# Auto-detect main table
all_records = wrapper.get_all()
```

##### `get_by_series(series_name: str) -> List[Dict]`

Gets records filtered by series name.

**Example:**
```python
pm5000_meters = wrapper.get_by_series("PM5000")
for meter in pm5000_meters:
    print(f"Model: {meter['model_name']}")
```

##### `get_specifications(model_name: str) -> Dict`

Retrieves detailed specifications with related data.

**Example:**
```python
specs = wrapper.get_specifications("PM5560")
print(f"Model: {specs['model_name']}")
print(f"Accuracy Classes: {specs.get('accuracy_classes', [])}")
print(f"Communications: {specs.get('communication_protocols', {})}")
```

##### `search(criteria: Dict[str, Any]) -> List[Dict]`

Smart search with multiple criteria.

**Example:**
```python
# Search with exact match
results = wrapper.search({"series_name": "PM5000"})

# Search with wildcards
results = wrapper.search({"model_name": "%5560%"})

# Multiple criteria
results = wrapper.search({
    "series_name": "PM5000",
    "accuracy_class": "0.5S"
})
```

##### `query(sql: str, params: tuple = None) -> List[Dict]`

Execute raw SQL queries.

**Example:**
```python
# Custom query
results = wrapper.query(
    "SELECT model_name, series_name FROM Meters WHERE accuracy_class = ?",
    ("0.2S",)
)
```

---

## Processing Components

### LLMProcessor

**Location**: `overhaul/core/llm_processor.py`

Handles LLM interactions using Ollama.

#### Constructor

```python
from core import LLMProcessor

processor = LLMProcessor(model: str = "qwen2.5-coder:7b")
```

#### Primary Methods

##### `process_prompt(prompt: str, timeout: int = 120) -> Dict[str, Any]`

Processes a prompt with the LLM and returns structured results.

**Parameters:**
- `prompt`: Text prompt to send to LLM
- `timeout`: Maximum processing time in seconds

**Returns:**
```python
{
    'raw_response': str,      # Raw LLM response
    'parsed_result': Dict,    # Extracted JSON if found
    'success': bool,          # Processing success status
    'error': str             # Error message if success=False
}
```

**Example:**
```python
from core import LLMProcessor
import asyncio

async def analyze_text():
    processor = LLMProcessor()
    
    prompt = """
    Analyze this requirement: "Meter must have ±0.2% accuracy"
    Return JSON: {"requirement": "...", "accuracy": "...", "compliant": true/false}
    """
    
    result = await processor.process_prompt(prompt)
    
    if result['success']:
        analysis = result['parsed_result']
        print(f"Requirement: {analysis.get('requirement')}")
        print(f"Compliant: {analysis.get('compliant')}")
    else:
        print(f"Error: {result['error']}")

asyncio.run(analyze_text())
```

### FileProcessor

**Location**: `overhaul/core/file_processor.py`

Handles different file types for input processing.

#### Constructor

```python
from core import FileProcessor

processor = FileProcessor()
```

#### Primary Methods

##### `process_file(file_path: str) -> Dict[str, Any]`

Processes a file and returns content with metadata.

**Parameters:**
- `file_path`: Path to file to process

**Returns:**
```python
{
    'name': str,        # File name
    'basename': str,    # Name without extension
    'extension': str,   # File extension
    'size': int,        # File size in bytes
    'content': str,     # File content as text
    'path': str         # Absolute path
}
```

**Supported Formats:**
- Text files (`.txt`, `.md`)
- PDF files (`.pdf`) - requires PyPDF2
- Other text-based files

**Example:**
```python
from core import FileProcessor

processor = FileProcessor()

# Process a tender document
file_data = processor.process_file("documents/tender.pdf")
print(f"Processed {file_data['name']}")
print(f"Size: {file_data['size']} bytes")
print(f"Content length: {len(file_data['content'])} characters")

# Access content in templates
# In YAML: {{ tender_document.content }}
```

### TemplateAnalyzer

**Location**: `overhaul/core/template_analyzer.py`

Validates YAML prompt configurations.

#### Constructor

```python
from core import TemplateAnalyzer, DatabaseFunctionRegistry

registry = DatabaseFunctionRegistry()
analyzer = TemplateAnalyzer(registry)
```

#### Primary Methods

##### `validate_template(yaml_config: Dict[str, Any]) -> Dict[str, Any]`

Validates a YAML prompt configuration.

**Parameters:**
- `yaml_config`: Parsed YAML configuration

**Returns:**
```python
{
    'valid': bool,              # Overall validation status
    'errors': List[str],        # Critical errors
    'warnings': List[str]       # Non-critical warnings
}
```

**Example:**
```python
import yaml
from core import TemplateAnalyzer, DatabaseFunctionRegistry

# Load YAML config
with open("prompts/tender_analysis.yaml", 'r') as f:
    config = yaml.safe_load(f)

# Validate
registry = DatabaseFunctionRegistry()
analyzer = TemplateAnalyzer(registry)
validation = analyzer.validate_template(config)

if validation['valid']:
    print("✅ Configuration is valid")
    for warning in validation['warnings']:
        print(f"⚠️ {warning}")
else:
    print("❌ Configuration has errors:")
    for error in validation['errors']:
        print(f"  - {error}")
```

---

## Output Generation

### ExcelGenerator

**Location**: `overhaul/core/excel_generator.py`

Generates Excel compliance reports from structured data.

#### Constructor

```python
from core.excel_generator import ExcelGenerator

generator = ExcelGenerator()
```

#### Primary Methods

##### `generate_compliance_report(output_file: str, data: Dict) -> bool`

Generates a comprehensive Excel compliance report.

**Parameters:**
- `output_file`: Path for output Excel file
- `data`: Structured compliance data

**Expected Data Structure:**
```python
{
    "summary_sheet": {
        "title": "Compliance Summary",
        "data": {
            "project_name": str,
            "selected_meter": str,
            "analysis_date": str,
            "overall_compliance": str,
            "total_requirements": int,
            "status_breakdown": {
                "fully_compliant": int,
                "partially_compliant": int,
                "non_compliant": int
            }
        }
    },
    "compliance_matrix": {
        "title": "Detailed Compliance Matrix",
        "headers": List[str],
        "data": List[List[str]]  # Rows of compliance data
    },
    "meter_specs": {
        "title": "Selected Meter Specifications", 
        "meter_details": {
            "model": str,
            "series": str,
            "specifications": Dict[str, str]
        }
    }
}
```

**Returns:**
- `True` if generation successful, `False` otherwise

**Example:**
```python
from core.excel_generator import ExcelGenerator

# Prepare data structure
compliance_data = {
    "summary_sheet": {
        "title": "Compliance Summary",
        "data": {
            "project_name": "Metro Station Power Meters",
            "selected_meter": "PM5560",
            "analysis_date": "2024-01-15",
            "overall_compliance": "85%",
            "total_requirements": 20,
            "status_breakdown": {
                "fully_compliant": 15,
                "partially_compliant": 3,
                "non_compliant": 2
            }
        }
    },
    "compliance_matrix": {
        "title": "Detailed Compliance Matrix",
        "headers": ["Clause", "Requirement", "Meter Spec", "Status"],
        "data": [
            ["1.1", "±0.5% accuracy", "±0.2% accuracy", "COMPLIANT"],
            ["1.2", "Modbus RTU", "Modbus RTU/TCP", "COMPLIANT"]
        ]
    },
    "meter_specs": {
        "title": "Selected Meter Specifications",
        "meter_details": {
            "model": "PM5560",
            "series": "PM5000",
            "specifications": {
                "accuracy": "±0.2%",
                "communication": "Modbus RTU/TCP"
            }
        }
    }
}

# Generate Excel report
generator = ExcelGenerator()
success = generator.generate_compliance_report("reports/compliance.xlsx", compliance_data)

if success:
    print("✅ Excel report generated successfully")
else:
    print("❌ Failed to generate Excel report")
```

---

## Configuration System

### DatabaseFunctionRegistry

**Location**: `overhaul/core/function_registry.py`

Manages available database functions and their metadata.

#### Constructor

```python
from core import DatabaseFunctionRegistry

registry = DatabaseFunctionRegistry()
```

#### Primary Methods

##### `register_database(db_name: str, wrapper: SmartDatabaseWrapper)`

Registers all available functions for a database.

**Example:**
```python
from core import DatabaseFunctionRegistry, SmartDatabaseWrapper, DatabaseAutoDiscovery

registry = DatabaseFunctionRegistry()
discovery = DatabaseAutoDiscovery()
wrapper = SmartDatabaseWrapper("databases/meters.db", discovery)

# Register database functions
registry.register_database("meters", wrapper)

# Get available functions
functions = registry.get_available_functions("meters")
for func_name, func_info in functions.items():
    print(f"{func_name}: {func_info['description']}")
    print(f"  Example: {func_info['example']}")
```

##### `get_available_functions(db_name: str) -> Dict[str, Any]`

Returns all available functions for a database with metadata.

**Returns:**
```python
{
    'function_name': {
        'description': str,
        'parameters': List[Dict],
        'returns': str,
        'example': str
    }
}
```

---

## Legacy Components

### MeterSpecificationComparison

**Location**: `old/comparison.py`

Advanced comparison tool for tender requirements vs meter specifications.

#### Constructor

```python
from old.comparison import MeterSpecificationComparison

comparator = MeterSpecificationComparison(db_path="databases/meters.db")
```

#### Primary Methods

##### `export_to_excel(analysis_path: str, excel_path: str = None) -> str`

Generates detailed Excel compliance reports from analysis files.

**Parameters:**
- `analysis_path`: Path to analysis output file
- `excel_path`: Optional output Excel path
- `override_meter`: Optional meter model to force selection
- `per_clause_override`: Optional clause-specific meter overrides

**Example:**
```python
from old.comparison import MeterSpecificationComparison

comparator = MeterSpecificationComparison()

# Generate Excel from analysis
excel_path = comparator.export_to_excel(
    analysis_path="outputs/analysis_output.txt",
    excel_path="reports/detailed_compliance.xlsx"
)

print(f"Generated: {excel_path}")
```

### DocumentParser & TenderAnalyzer

**Location**: `old/databasingcode.py`

Legacy document parsing and analysis components.

#### TenderAnalyzer Constructor

```python
from old.databasingcode import TenderAnalyzer

analyzer = TenderAnalyzer(database_path="databases/meters.db")
```

#### Primary Methods

##### `analyze_document(tender_file: str, manual_clauses: List[str]) -> List[Dict]`

Analyzes tender documents and recommends meters for specific clauses.

**Example:**
```python
from old.databasingcode import TenderAnalyzer

analyzer = TenderAnalyzer("databases/meters.db")

# Analyze specific clauses
results = analyzer.analyze_document(
    tender_file="documents/tender.txt",
    manual_clauses=["8.1", "8.2", "8.3"]
)

print(f"Analyzed {len(results)} requirements")
```

### ClauseExtractor

**Location**: `old/clause_extractor.py`

Standalone clause extraction utility for PDF documents.

#### Functions

##### `extract_text_from_pdf(pdf_path: str) -> str`

Extracts text content from PDF files.

##### `main()`

Interactive clause extraction workflow.

**Example Usage:**
```bash
python old/clause_extractor.py
# Enter path when prompted: documents/tender.pdf
# Results saved to: documents/tender_extracted_clauses.txt
```

---

## YAML Template System

### Template Structure

YAML templates define complete processing workflows with inputs, processing steps, and outputs.

#### Basic Template Structure

```yaml
name: "Template Name"
description: "Template description"
version: "1.0"

inputs:
  - name: "input_name"
    type: "file|text|option|number"
    required: true|false
    description: "Input description"

databases:
  db_name: "path/to/database.db"

processing_steps:
  - name: "step_name"
    description: "Step description"
    dependencies: ["previous_step"]  # Optional
    timeout: 120  # Optional, seconds
    prompt_template: |
      Template content with {{ variable }} substitution
      
outputs:
  - type: "json|excel|text|markdown"
    filename: "output_{{ timestamp }}.ext"
    content: "{{ template_content }}"
    condition: "optional_condition"  # Optional
```

### Available Templates

#### 1. Excel Generation (`excel_generation.yaml`)

Generates comprehensive Excel compliance reports.

**Usage:**
```bash
python main.py
# Select: excel_generation.yaml
# Provide analysis file when prompted
```

**Key Features:**
- Direct LLM processing of analysis files
- Complete Excel structure generation
- Robust JSON extraction and repair
- Status reporting and debugging outputs

#### 2. Tender Analysis (`tender_analysis.yaml`)

Extracts relevant meter specification clauses from tender documents.

**Usage:**
```bash
python main.py
# Select: tender_analysis.yaml
# Provide tender document when prompted
```

**Key Features:**
- Intelligent clause relevance detection
- Complete clause text extraction
- Structured output formatting
- Support for PDF and text documents

#### 3. Quick Meter Analysis (`quick_meter_analysis.yaml`)

Rapid meter recommendation for any document.

**Usage:**
```bash
python main.py
# Select: quick_meter_analysis.yaml
# Provide document when prompted
```

**Key Features:**
- Fast clause extraction
- Top 3 meter recommendations per clause
- JSON output format
- Database integration

### Template Variables

Templates can access the following variables:

#### Input Variables
- `{{ input_name.content }}` - File content
- `{{ input_name.name }}` - File name
- `{{ input_name.basename }}` - Name without extension
- `{{ text_input_name }}` - Text input value

#### Database Variables
- `{{ databases.db_name.get_all() }}` - All records
- `{{ databases.db_name.search({criteria}) }}` - Search results
- `{{ databases.db_name.query(sql) }}` - Custom query results

#### System Variables
- `{{ timestamp }}` - Current timestamp (YYYYMMDD_HHMMSS)
- `{{ config.name }}` - Template name
- `{{ config.version }}` - Template version

#### Step Results
- `{{ step_name.raw_response }}` - Raw LLM response
- `{{ step_name.parsed_result }}` - Parsed JSON result
- `{{ step_name.success }}` - Success status

---

## Usage Examples

### Example 1: Complete Compliance Analysis Workflow

```python
import asyncio
from core import PromptEngine

async def complete_analysis():
    """Complete end-to-end compliance analysis"""
    
    # Initialize engine
    engine = PromptEngine(
        databases_dir="databases",
        prompts_dir="prompts",
        outputs_dir="outputs"
    )
    
    # Step 1: Extract clauses from tender
    clause_result = await engine.run_prompt("prompts/tender_analysis.yaml")
    if not clause_result['success']:
        print(f"❌ Clause extraction failed: {clause_result['error']}")
        return
    
    print(f"✅ Extracted clauses: {clause_result['output_files']}")
    
    # Step 2: Generate Excel compliance report
    excel_result = await engine.run_prompt("prompts/excel_generation.yaml")
    if not excel_result['success']:
        print(f"❌ Excel generation failed: {excel_result['error']}")
        return
    
    print(f"✅ Generated reports: {excel_result['output_files']}")
    
    return {
        'clause_files': clause_result['output_files'],
        'excel_files': excel_result['output_files']
    }

# Run the analysis
results = asyncio.run(complete_analysis())
```

### Example 2: Custom Database Queries

```python
from core import SmartDatabaseWrapper, DatabaseAutoDiscovery

def analyze_meter_database():
    """Analyze available meters and their capabilities"""
    
    # Initialize components
    discovery = DatabaseAutoDiscovery()
    wrapper = SmartDatabaseWrapper("databases/meters.db", discovery)
    
    # Get overview
    schema = discovery.discover_database("databases/meters.db")
    print(f"Database contains {len(schema.tables)} tables:")
    
    for table_name, table_info in schema.tables.items():
        print(f"  - {table_name}: {table_info.row_count} records")
    
    # Analyze meter series
    series_summary = wrapper.get_series_summary()
    print(f"\nAvailable meter series:")
    
    for series in series_summary:
        print(f"  - {series['series_name']}: {series['model_count']} models")
    
    # Find high-accuracy meters
    accurate_meters = wrapper.search({"accuracy_class": "0.2S"})
    print(f"\nHigh-accuracy meters (0.2S): {len(accurate_meters)} found")
    
    for meter in accurate_meters[:5]:  # Show first 5
        print(f"  - {meter['model_name']} ({meter['series_name']})")
    
    # Custom analysis query
    advanced_meters = wrapper.query("""
        SELECT m.model_name, m.series_name, COUNT(pq.analysis_feature) as pq_features
        FROM Meters m
        LEFT JOIN PowerQualityAnalysis pq ON m.id = pq.meter_id
        GROUP BY m.model_name, m.series_name
        HAVING pq_features > 5
        ORDER BY pq_features DESC
    """)
    
    print(f"\nMeters with advanced power quality features:")
    for meter in advanced_meters:
        print(f"  - {meter['model_name']}: {meter['pq_features']} PQ features")

analyze_meter_database()
```

### Example 3: Custom LLM Processing

```python
import asyncio
from core import LLMProcessor, FileProcessor

async def custom_requirement_analysis():
    """Custom analysis of specific requirements"""
    
    # Initialize processors
    llm = LLMProcessor()
    file_proc = FileProcessor()
    
    # Load document
    doc_data = file_proc.process_file("documents/requirements.txt")
    
    # Create custom analysis prompt
    prompt = f"""
    Analyze the following technical requirements and extract:
    1. Accuracy specifications
    2. Communication requirements  
    3. Environmental conditions
    4. Power measurement needs
    
    Document:
    {doc_data['content']}
    
    Return JSON:
    {{
        "accuracy_requirements": ["list of accuracy specs"],
        "communication_protocols": ["list of protocols"],
        "environmental_conditions": ["list of conditions"],
        "power_measurements": ["list of measurements"],
        "compliance_critical": ["most critical requirements"]
    }}
    """
    
    # Process with LLM
    result = await llm.process_prompt(prompt, timeout=180)
    
    if result['success']:
        analysis = result['parsed_result']
        
        print("📊 Requirement Analysis Results:")
        print(f"Accuracy Requirements: {len(analysis.get('accuracy_requirements', []))}")
        print(f"Communication Protocols: {len(analysis.get('communication_protocols', []))}")
        print(f"Environmental Conditions: {len(analysis.get('environmental_conditions', []))}")
        print(f"Power Measurements: {len(analysis.get('power_measurements', []))}")
        
        print("\n🚨 Critical Requirements:")
        for req in analysis.get('compliance_critical', []):
            print(f"  - {req}")
        
        return analysis
    else:
        print(f"❌ Analysis failed: {result['error']}")
        return None

# Run custom analysis
analysis = asyncio.run(custom_requirement_analysis())
```

### Example 4: Batch Processing Multiple Documents

```python
import asyncio
from pathlib import Path
from core import PromptEngine

async def batch_process_tenders():
    """Process multiple tender documents in batch"""
    
    engine = PromptEngine()
    tender_docs = Path("documents/tenders").glob("*.txt")
    
    results = []
    
    for doc_path in tender_docs:
        print(f"\n📄 Processing: {doc_path.name}")
        
        try:
            # Create temporary config for this document
            config_data = {
                'name': f'Batch Analysis - {doc_path.stem}',
                'inputs': [
                    {
                        'name': 'tender_document',
                        'type': 'file',
                        'value': str(doc_path)  # Pre-set the file path
                    }
                ],
                'processing_steps': [
                    {
                        'name': 'quick_analysis',
                        'prompt_template': '''
                        Extract top 5 most critical meter requirements from:
                        {{ tender_document.content }}
                        
                        Return JSON: {"critical_requirements": ["req1", "req2", ...]}
                        '''
                    }
                ],
                'outputs': [
                    {
                        'type': 'json',
                        'filename': f'{doc_path.stem}_batch_analysis.json',
                        'data': '{{ quick_analysis.parsed_result }}'
                    }
                ]
            }
            
            # Save temporary config
            temp_config = f"temp_batch_{doc_path.stem}.yaml"
            with open(temp_config, 'w') as f:
                yaml.dump(config_data, f)
            
            # Process document
            result = await engine.run_prompt(temp_config)
            
            # Clean up temp config
            Path(temp_config).unlink()
            
            if result['success']:
                results.append({
                    'document': doc_path.name,
                    'status': 'success',
                    'outputs': result['output_files']
                })
                print(f"✅ Completed: {doc_path.name}")
            else:
                results.append({
                    'document': doc_path.name,
                    'status': 'failed',
                    'error': result['error']
                })
                print(f"❌ Failed: {doc_path.name}")
                
        except Exception as e:
            results.append({
                'document': doc_path.name,
                'status': 'error',
                'error': str(e)
            })
            print(f"💥 Error: {doc_path.name} - {e}")
    
    # Summary
    successful = sum(1 for r in results if r['status'] == 'success')
    print(f"\n📊 Batch Processing Summary:")
    print(f"Total documents: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {len(results) - successful}")
    
    return results

# Run batch processing
import yaml
batch_results = asyncio.run(batch_process_tenders())
```

---

## Integration Guide

### Setting Up the Environment

1. **Install Dependencies**
```bash
pip install -r requirements.txt
# Required: sqlite3, PyPDF2, openpyxl, pandas, jinja2, pyyaml, ollama
```

2. **Install Ollama and Models**
```bash
# Install Ollama (see https://ollama.ai)
ollama pull qwen2.5-coder:7b
```

3. **Database Setup**
```bash
# Ensure databases are in the correct location
mkdir -p databases
# Copy your meter database to databases/meters.db
```

### Project Structure

```
project/
├── overhaul/
│   ├── main.py              # Main entry point
│   ├── core/                # Core components
│   │   ├── __init__.py
│   │   ├── prompt_engine.py
│   │   ├── database_autodiscovery.py
│   │   ├── llm_processor.py
│   │   ├── file_processor.py
│   │   ├── excel_generator.py
│   │   └── ...
│   ├── prompts/             # YAML templates
│   │   ├── excel_generation.yaml
│   │   ├── tender_analysis.yaml
│   │   └── quick_meter_analysis.yaml
│   ├── databases/           # Database files
│   │   └── meters.db
│   └── outputs/            # Generated outputs
├── old/                    # Legacy components
│   ├── comparison.py
│   ├── databasingcode.py
│   └── clause_extractor.py
└── chroma_db/             # Vector database (optional)
```

### Basic Integration Pattern

```python
# 1. Import core components
from core import (
    PromptEngine,
    SmartDatabaseWrapper, 
    DatabaseAutoDiscovery,
    LLMProcessor,
    FileProcessor,
    ExcelGenerator
)

# 2. Initialize components
engine = PromptEngine()
llm = LLMProcessor()
file_proc = FileProcessor()

# 3. Set up database access
discovery = DatabaseAutoDiscovery()
db_wrapper = SmartDatabaseWrapper("databases/meters.db", discovery)

# 4. Process documents
doc_data = file_proc.process_file("input.pdf")

# 5. Create custom prompts or use templates
result = await engine.run_prompt("prompts/custom_analysis.yaml")

# 6. Generate outputs
if result['success']:
    excel_gen = ExcelGenerator()
    excel_gen.generate_compliance_report("output.xlsx", result['data'])
```

### Error Handling Best Practices

```python
async def robust_processing():
    """Example of robust error handling"""
    
    try:
        engine = PromptEngine()
        
        # Validate inputs
        if not Path("prompts/analysis.yaml").exists():
            raise FileNotFoundError("Analysis template not found")
        
        if not Path("databases/meters.db").exists():
            raise FileNotFoundError("Meter database not found")
        
        # Process with timeout
        result = await asyncio.wait_for(
            engine.run_prompt("prompts/analysis.yaml"),
            timeout=300  # 5 minute timeout
        )
        
        if not result['success']:
            logging.error(f"Processing failed: {result['error']}")
            return None
        
        return result
        
    except asyncio.TimeoutError:
        logging.error("Processing timed out")
        return None
    except FileNotFoundError as e:
        logging.error(f"Required file missing: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return None
```

### Performance Optimization

```python
# 1. Use chunked processing for large documents
async def process_large_document():
    """Handle large documents efficiently"""
    
    # Split large documents into chunks
    chunk_size = 5000  # characters
    doc_content = file_processor.process_file("large_doc.pdf")['content']
    
    chunks = [
        doc_content[i:i+chunk_size] 
        for i in range(0, len(doc_content), chunk_size)
    ]
    
    results = []
    for i, chunk in enumerate(chunks):
        print(f"Processing chunk {i+1}/{len(chunks)}")
        
        # Process each chunk separately
        chunk_result = await llm.process_prompt(f"Analyze: {chunk}")
        results.append(chunk_result)
        
        # Small delay to avoid overwhelming the LLM
        await asyncio.sleep(1)
    
    return results

# 2. Cache database schema discovery
class CachedDatabaseWrapper:
    """Wrapper with schema caching"""
    
    def __init__(self, db_path):
        self.db_path = db_path
        self._schema_cache = {}
        
    def get_wrapper(self, force_refresh=False):
        if self.db_path not in self._schema_cache or force_refresh:
            discovery = DatabaseAutoDiscovery()
            self._schema_cache[self.db_path] = SmartDatabaseWrapper(
                self.db_path, discovery
            )
        return self._schema_cache[self.db_path]

# 3. Parallel processing for multiple documents
async def parallel_document_processing():
    """Process multiple documents in parallel"""
    
    documents = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
    
    async def process_single_doc(doc_path):
        engine = PromptEngine()
        return await engine.run_prompt("prompts/analysis.yaml")
    
    # Process all documents concurrently
    tasks = [process_single_doc(doc) for doc in documents]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle results and exceptions
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Document {documents[i]} failed: {result}")
        else:
            print(f"Document {documents[i]} completed")
```

### Testing Framework

```python
import pytest
import tempfile
from pathlib import Path

class TestCompleteWorkflow:
    """Integration tests for complete workflows"""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create directory structure
            (workspace / "prompts").mkdir()
            (workspace / "databases").mkdir() 
            (workspace / "outputs").mkdir()
            
            yield workspace
    
    @pytest.mark.asyncio
    async def test_end_to_end_analysis(self, temp_workspace):
        """Test complete analysis workflow"""
        
        # Setup test data
        test_prompt = temp_workspace / "prompts" / "test.yaml"
        test_prompt.write_text("""
        name: "Test Analysis"
        inputs:
          - name: "test_doc"
            type: "text"
            default: "Test requirement: ±0.5% accuracy"
        processing_steps:
          - name: "analyze"
            prompt_template: "Extract accuracy from: {{ test_doc }}"
        outputs:
          - type: "text"
            filename: "test_output.txt"
            content: "{{ analyze.raw_response }}"
        """)
        
        # Initialize engine with test workspace
        engine = PromptEngine(
            prompts_dir=str(temp_workspace / "prompts"),
            outputs_dir=str(temp_workspace / "outputs")
        )
        
        # Run analysis
        result = await engine.run_prompt(str(test_prompt))
        
        # Verify results
        assert result['success']
        assert len(result['output_files']) > 0
        
        output_file = Path(result['output_files'][0])
        assert output_file.exists()
        assert "±0.5%" in output_file.read_text()

# Run tests
# pytest test_integration.py -v
```

This comprehensive documentation covers all public APIs, functions, and components in the system with practical examples and usage instructions. Each component is documented with its purpose, parameters, return values, and working code examples that can be used immediately.