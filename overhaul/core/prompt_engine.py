# core/prompt_engine.py
import os
import yaml
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from jinja2 import Environment, BaseLoader, Template

from .database_autodiscovery import DatabaseAutoDiscovery, SmartDatabaseWrapper
from .function_registry import DatabaseFunctionRegistry  
from .template_analyzer import TemplateAnalyzer
from .file_processor import FileProcessor
from .llm_processor import LLMProcessor
from .excel_generator import ExcelGenerator
from .llamaindex_query_engine import LlamaIndexQueryEngine

class PromptEngine:
    """Main YAML prompt engine with auto-discovery database integration"""
    
    def __init__(self, 
                 databases_dir: str = "databases", 
                 prompts_dir: str = "prompts",
                 outputs_dir: str = "outputs"):
        self.databases_dir = Path(databases_dir)
        self.prompts_dir = Path(prompts_dir)
        self.outputs_dir = Path(outputs_dir)
        
        # Ensure output directory exists
        self.outputs_dir.mkdir(exist_ok=True)
        
        # Initialize components
        self.discovery_engine = DatabaseAutoDiscovery()
        self.function_registry = DatabaseFunctionRegistry()
        self.template_analyzer = TemplateAnalyzer(self.function_registry)
        self.file_processor = FileProcessor()
        self.llm_processor = LLMProcessor()
        
        # Initialize database schemas storage
        self._database_schemas = {}
        
        # Jinja2 environment for template rendering
        self.jinja_env = Environment(loader=BaseLoader())
        
        # New: Initialize LlamaIndex query engines
        self.llamaindex_engines = {}
        
        print("🔧 Prompt engine components initialized")
    
    async def run_prompt(self, prompt_file: str) -> Dict[str, Any]:
        """Run a YAML prompt configuration end-to-end"""
        try:
            print(f"📄 Loading prompt configuration: {prompt_file}")
            config = self._load_yaml_config(prompt_file)

            print("🔍 Validating configuration...")
            validation = self.template_analyzer.validate_template(config)
            if not validation['valid']:
                return {'success': False, 'error': f"Configuration errors: {validation['errors']}"}
            if validation['warnings']:
                for warning in validation['warnings']:
                    print(f"⚠️ {warning}")

            # --- Improved Input Handling ---
            inputs_config = config.get('inputs', [])
            if inputs_config:
                print("\n📝 Required Inputs:")
                for inp in inputs_config:
                    req = 'required' if inp.get('required', False) else 'optional'
                    desc = inp.get('description', '')
                    print(f"- {inp['name']} ({inp['type']}, {req}): {desc}")
            print()
            input_data = await self._process_inputs(inputs_config)

            print("🗄️ Loading databases with auto-discovery...")
            databases = await self._load_databases_smart(config.get('databases', {}))

            # --- Build Unified Context ---
            context = {
                'inputs': input_data,
                'databases': databases,
                'database_schemas': {name: db.get_schema_info() for name, db in databases.items()},
                'step_results': {},
                'timestamp': datetime.utcnow().strftime('%Y%m%d_%H%M%S'),
                'config': config
            }

            print("🔄 Executing processing pipeline...")
            pipeline_results = await self._execute_pipeline(
                config.get('processing_steps', []),
                context
            )
            context['step_results'] = pipeline_results

            print("📤 Generating outputs...")
            output_files = await self._generate_outputs(
                config.get('outputs', []),
                context
            )

            return {
                'success': True,
                'pipeline_results': pipeline_results,
                'output_files': output_files
            }
        except Exception as e:
            print(f"❌ Error running prompt: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def _load_yaml_config(self, prompt_file: str) -> Dict[str, Any]:
        """Load and parse YAML configuration"""
        
        prompt_path = Path(prompt_file)
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        
        with open(prompt_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if not config:
            raise ValueError("Empty or invalid YAML configuration")
        
        print(f"✅ Loaded configuration: {config.get('name', 'Unnamed')}")
        return config
    
    async def _process_inputs(self, inputs_config: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process input files and parameters (extended types and validation)"""
        input_data = {}
        for input_spec in inputs_config:
            input_name = input_spec['name']
            input_type = input_spec['type']
            required = input_spec.get('required', False)
            desc = input_spec.get('description', '')
            default = input_spec.get('default', None)
            value = None
            if input_type == 'file':
                file_path = input(f"📁 Enter path for {input_name} ({desc}): ").strip().strip('"\'')
                if not file_path and required:
                    raise ValueError(f"Required input '{input_name}' not provided")
                if file_path and Path(file_path).exists():
                    file_data = self.file_processor.process_file(file_path)
                    input_data[input_name] = file_data
                    print(f"✅ Processed {input_name}: {len(file_data['content'])} characters")
                elif required:
                    raise FileNotFoundError(f"Input file not found: {file_path}")
            elif input_type == 'text':
                value = input(f"📝 Enter {input_name} (default: {default}): ").strip() or default
                input_data[input_name] = value
            elif input_type == 'option':
                options = input_spec.get('options', [])
                print(f"📋 Select {input_name}:")
                for i, option in enumerate(options, 1):
                    print(f"  {i}. {option}")
                choice = input(f"Enter choice (1-{len(options)}, default: {default}): ").strip()
                if choice and choice.isdigit():
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(options):
                        value = options[choice_idx]
                    else:
                        value = default
                else:
                    value = default
                input_data[input_name] = value
            elif input_type == 'number':
                value = input(f"🔢 Enter {input_name} (default: {default}): ").strip()
                try:
                    if value:
                        input_data[input_name] = float(value)
                    elif default is not None:
                        input_data[input_name] = float(default)
                    else:
                        input_data[input_name] = 0.0
                except (ValueError, TypeError):
                    input_data[input_name] = float(default) if default is not None else 0.0
            elif input_type == 'boolean':
                value = input(f"[y/n] {input_name} (default: {default}): ").strip().lower()
                if value in ['y', 'yes', 'true', '1']:
                    input_data[input_name] = True
                elif value in ['n', 'no', 'false', '0']:
                    input_data[input_name] = False
                else:
                    input_data[input_name] = bool(default)
            # Extend here for more types (date, list, etc.)
        return input_data
    
    async def _load_databases_smart(self, database_config: Dict[str, str]) -> Dict[str, SmartDatabaseWrapper]:
        """Load databases with auto-discovery"""
        
        smart_databases = {}
        
        for db_name, db_path in database_config.items():
            if not Path(db_path).exists():
                print(f"⚠️ Database not found: {db_path}, skipping {db_name}")
                continue
            
            # Create smart wrapper with auto-discovery
            wrapper = SmartDatabaseWrapper(db_path, self.discovery_engine)
            smart_databases[db_name] = wrapper
            
            # Register functions for template validation
            self.function_registry.register_database(db_name, wrapper)
            
            available_functions = len(self.function_registry.get_available_functions(db_name))
            print(f"✅ {db_name}: {available_functions} functions auto-discovered")
        
        # NEW: Store for LlamaIndex access
        self._last_loaded_databases = smart_databases
        
        return smart_databases
    
    async def _execute_pipeline(self, steps: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the processing pipeline with unified context passing"""
        results = {}
        for step in steps:
            step_name = step['name']
            prompt_template = step['prompt_template']
            dependencies = step.get('dependencies', [])
            timeout = step.get('timeout', 120)
            print(f"⚙️ Executing step: {step_name}")

            # Add dependencies to context
            for dep in dependencies:
                if dep not in results:
                    raise ValueError(f"Step '{step_name}' depends on '{dep}' which hasn't been executed")
            
            # Build step context
            step_context = context.copy()
            step_context['step_results'] = results.copy()
            for dep in dependencies:
                step_context[dep] = results[dep]

            # LlamaIndex step detection (by convention) - MOVE THIS BEFORE TEMPLATE RENDERING
            if step_name.startswith("llamaindex_"):
                db_path = context['databases']['meters'].db_path
                llamaindex_engine = self.get_llamaindex_engine(db_path)
                # Render the prompt as the natural language query
                template = self.jinja_env.from_string(prompt_template)
                nl_query = template.render(**step_context)
                print(f"🦙 LlamaIndex NL Query: {nl_query}")
                result = await llamaindex_engine.query(nl_query)
                results[step_name] = {"llamaindex_result": result}
                print(f"✅ Step '{step_name}' completed (LlamaIndex)")
                continue

            # Render template with full context
            template = self.jinja_env.from_string(prompt_template)
            rendered_prompt = template.render(**step_context)
            print(f"📝 Rendered prompt ({len(rendered_prompt)} chars)")
            
            # DEBUG: Print context keys/types and preview of rendered prompt
            print(f"\n=== DEBUG: Step '{step_name}' context keys/types ===")
            for k, v in step_context.items():
                print(f"  {k}: {type(v)} (len={len(v) if hasattr(v, '__len__') else 'n/a'})")
            print(f"\n=== DEBUG: Step '{step_name}' rendered prompt preview ===\n{rendered_prompt[:2000]}\n--- END PREVIEW ---\n")
            
            # Execute with LLM
            step_result = await self.llm_processor.process_prompt(rendered_prompt, timeout)
            results[step_name] = step_result
            print(f"✅ Step '{step_name}' completed")

        return results
    
    async def _generate_outputs(self, outputs_config: List[Dict[str, Any]], context: Dict[str, Any]) -> List[str]:
        """Generate output files using unified context"""
        output_files = []
        for output_spec in outputs_config:
            output_type = output_spec['type']
            filename_template = output_spec['filename']
            
            # Check condition if specified
            condition = output_spec.get('condition')
            if condition:
                try:
                    template = self.jinja_env.from_string(f"{{{{ {condition} }}}}")
                    should_generate = template.render(**context).strip().lower() in ['true', '1', 'yes']
                    if not should_generate:
                        continue
                except:
                    print(f"⚠️ Could not evaluate condition: {condition}")
                    continue
            
            # Render filename
            filename_tmpl = self.jinja_env.from_string(filename_template)
            filename = filename_tmpl.render(**context)
            output_path = self.outputs_dir / filename
            
            # Generate content based on type
            if output_type == 'json':
                data = output_spec.get('data', context['step_results'])
                if isinstance(data, str):
                    data_template = self.jinja_env.from_string(data)
                    data = data_template.render(**context)
                    try:
                        data = json.loads(data)
                    except:
                        pass
                elif isinstance(data, dict):
                    data = self._render_template_dict(data, context)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str)
            
            elif output_type == 'excel':
                data = output_spec.get('data', context['step_results'])
                if isinstance(data, str):
                    data_template = self.jinja_env.from_string(data)
                    data = data_template.render(**context)
                    try:
                        data = json.loads(data)
                    except:
                        pass
                elif isinstance(data, dict):
                    data = self._render_template_dict(data, context)
                
                # Generate Excel file
                excel_generator = ExcelGenerator()
                try:
                    if excel_generator.generate_compliance_report(str(output_path), data):
                        print(f"✅ Excel file generated: {output_path}")
                    else:
                        print(f"❌ Failed to generate Excel file: {output_path}")
                except Exception as e:
                    print(f"❌ Excel generation error: {e}")

            elif output_type == 'custom_excel':
                # Handle custom Excel generation with direct LLM processing
                llm_step = output_spec.get('llm_step')
                if llm_step and llm_step in context['step_results']:
                    llm_result = context['step_results'][llm_step]
                    raw_response = llm_result.get('raw_response', '')
                    
                    # Try to extract JSON from raw response
                    excel_data = self._extract_and_fix_json_from_raw_response(raw_response)
                    
                    # Generate Excel file
                    if excel_data is not None:
                        excel_generator = ExcelGenerator()
                        try:
                            if excel_generator.generate_compliance_report(str(output_path), excel_data):
                                print(f"✅ Custom Excel file generated: {output_path}")
                            else:
                                print(f"❌ Failed to generate Excel file: {output_path}")
                        except Exception as e:
                            print(f"❌ Excel generation error: {e}")
                    else:
                        print(f"❌ Could not extract valid JSON from LLM response - check raw output file")
                else:
                    print(f"❌ LLM step '{llm_step}' not found in pipeline results")
            
            elif output_type == 'markdown':
                template_file = output_spec.get('template')
                if template_file and Path(template_file).exists():
                    with open(template_file, 'r', encoding='utf-8') as f:
                        template_content = f.read()
                else:
                    template_content = output_spec.get('content', '# Results\\n\\n{{ step_results | tojson(indent=2) }}')
                
                template = self.jinja_env.from_string(template_content)
                content = template.render(**context)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            elif output_type == 'text':
                content_template = output_spec.get('content', '{{ step_results }}')
                template = self.jinja_env.from_string(content_template)
                content = template.render(**context)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            output_files.append(str(output_path))
            print(f"📄 Generated: {output_path}")
        return output_files
    
    def _render_template_dict(self, data: Any, context: Dict[str, Any]) -> Any:
        """Recursively render template strings in a dictionary"""
        
        if isinstance(data, dict):
            return {k: self._render_template_dict(v, context) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._render_template_dict(item, context) for item in data]
        elif isinstance(data, str) and '{{' in data:
            try:
                template = self.jinja_env.from_string(data)
                return template.render(**context)
            except:
                return data
        else:
            return data
    
    def _extract_and_fix_json_from_raw_response(self, raw_response: str) -> dict:
        """Extract and fix JSON from raw LLM response"""
        
        print(f"🔧 Extracting JSON from {len(raw_response)} character response...")
        
        import re
        import json
        
        # Remove any markdown code block markers
        clean_response = raw_response.strip()
        if clean_response.startswith('```json'):
            clean_response = clean_response[7:]  # Remove ```json
        if clean_response.startswith('```'):
            clean_response = clean_response[3:]   # Remove ```
        if clean_response.endswith('```'):
            clean_response = clean_response[:-3]  # Remove trailing ```
        
        clean_response = clean_response.strip()
        
        # Try to parse the entire response as JSON first
        try:
            data = json.loads(clean_response)
            
            # Validate that it has the required sections
            required_sections = ['summary_sheet', 'compliance_matrix', 'meter_specs']
            missing_sections = [s for s in required_sections if s not in data]
            
            if not missing_sections:
                print("✅ Found complete valid Excel structure in LLM response")
                return data
            else:
                print(f"⚠️ Found JSON but missing sections: {missing_sections}")
                
        except json.JSONDecodeError as e:
            print(f"⚠️ Direct JSON parse failed: {e}")
        
        # Try to find JSON blocks with improved regex
        json_pattern = re.compile(r'\{(?:[^{}]|{[^{}]*})*\}', re.DOTALL)
        matches = json_pattern.findall(clean_response)
        
        # Try each match, from longest to shortest
        if matches:
            matches.sort(key=len, reverse=True)
            for i, match in enumerate(matches):
                try:
                    data = json.loads(match)
                    
                    # Validate that it has the required sections
                    required_sections = ['summary_sheet', 'compliance_matrix', 'meter_specs']
                    missing_sections = [s for s in required_sections if s not in data]
                    
                    if not missing_sections:
                        print(f"✅ Found valid Excel structure in match {i+1}")
                        return data
                    else:
                        print(f"⚠️ Match {i+1} missing sections: {missing_sections}")
                        
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON parse error in match {i+1}: {e}")
                    continue
        
        # If we get here, something went wrong - but we know the LLM response was good
        # Let's try a more aggressive approach
        print("🔄 Attempting aggressive JSON extraction...")
        
        # Find the opening brace and try to parse from there
        start_idx = clean_response.find('{')
        if start_idx != -1:
            # Find the last closing brace
            end_idx = clean_response.rfind('}')
            if end_idx != -1 and end_idx > start_idx:
                json_candidate = clean_response[start_idx:end_idx+1]
                try:
                    data = json.loads(json_candidate)
                    required_sections = ['summary_sheet', 'compliance_matrix', 'meter_specs']
                    missing_sections = [s for s in required_sections if s not in data]
                    
                    if not missing_sections:
                        print("✅ Aggressive extraction successful!")
                        return data
                        
                except json.JSONDecodeError:
                    pass
        
        print("❌ All JSON extraction methods failed")
        # Return empty dict to indicate failure - let the calling code handle fallback
        return {}
    
    async def _execute_chunked_llm_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        chunk_key: str,
        chunk_size: int = 5,
        meters_key: str = "meters"
    ) -> Dict[str, Any]:
        """
        Execute an LLM step in chunks, aggregating results.
        - step: The step dict from YAML.
        - context: The current template context.
        - chunk_key: The key in context to chunk (e.g., 'clauses' or 'items').
        - chunk_size: Number of items per chunk.
        - meters_key: The key for meters in context, if needed.
          If your step doesn't need 'meters', you can ignore or remove this.
        - chunk_aggregator_key: The dict key to aggregate from each chunk.
          Defaults to "recommendations" but can be overridden in your step config.
        
        Returns: Aggregated result dict of the form:
          { <chunk_aggregator_key>: [...] }
        """
        prompt_template = step['prompt_template']
        timeout = step.get('timeout', 120)
        all_items = context.get(chunk_key, [])
        meters = context.get(meters_key, None)

        # New: dynamic aggregator key
        aggregator_key = step.get('chunk_aggregator_key', 'recommendations')
        aggregated_items = []

        def chunk_list(lst, n):
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        for chunk in chunk_list(all_items, chunk_size):
            # Prepare chunk context
            chunk_context = context.copy()
            chunk_context[chunk_key] = chunk
            if meters is not None:
                chunk_context[meters_key] = meters

            # Render prompt
            template = self.jinja_env.from_string(prompt_template)
            rendered_prompt = template.render(**chunk_context)
            print(f"📝 [Chunked] Rendered prompt ({len(rendered_prompt)} chars, {len(chunk)} items)")

            # Get chunk result
            chunk_result = await self.llm_processor.process_prompt(rendered_prompt, timeout)

            # Check if chunk_result is the correct structure
            if isinstance(chunk_result, dict):
                # 1. Direct aggregator key
                if aggregator_key in chunk_result:
                    aggregated_items.extend(chunk_result[aggregator_key])
                    continue

                # 2. If "raw_response" is present, try JSON parse
                if 'raw_response' in chunk_result:
                    try:
                        parsed = json.loads(chunk_result['raw_response'])
                        if aggregator_key in parsed:
                            aggregated_items.extend(parsed[aggregator_key])
                            continue
                    except Exception as e:
                        print("⚠️ Could not parse raw_response as JSON:", e)

                print(f"⚠️ Chunk result missing '{aggregator_key}', skipping this chunk.")
            else:
                print("⚠️ Chunk result is not a dict, skipping this chunk.")

        # Return the merged aggregator
        return {aggregator_key: aggregated_items}

    def get_llamaindex_engine(self, db_path):
        if db_path not in self.llamaindex_engines:
            # NEW: Find the smart wrapper for this database
            smart_wrapper = None
            for db_name, wrapper in self._last_loaded_databases.items():
                if wrapper.db_path == db_path:
                    smart_wrapper = wrapper
                    break
        
            self.llamaindex_engines[db_path] = LlamaIndexQueryEngine(db_path, smart_wrapper=smart_wrapper)
        return self.llamaindex_engines[db_path]