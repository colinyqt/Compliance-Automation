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
        
        # Jinja2 environment for template rendering
        self.jinja_env = Environment(loader=BaseLoader())
        
        print("🔧 Prompt engine components initialized")
    
    async def run_prompt(self, prompt_file: str) -> Dict[str, Any]:
        """Run a YAML prompt configuration end-to-end"""
        
        try:
            # 1. Load and validate YAML configuration
            print(f"📄 Loading prompt configuration: {prompt_file}")
            config = self._load_yaml_config(prompt_file)
            
            # 2. Validate configuration
            print("🔍 Validating configuration...")
            validation = self.template_analyzer.validate_template(config)
            if not validation['valid']:
                return {'success': False, 'error': f"Configuration errors: {validation['errors']}"}
            
            if validation['warnings']:
                for warning in validation['warnings']:
                    print(f"⚠️ {warning}")
            
            # 3. Process input files
            print("📁 Processing input files...")
            input_data = await self._process_inputs(config.get('inputs', []))
            
            # 4. Load databases with auto-discovery
            print("🗄️ Loading databases with auto-discovery...")
            databases = await self._load_databases_smart(config.get('databases', {}))
            
            # 5. Execute processing pipeline
            print("🔄 Executing processing pipeline...")
            pipeline_results = await self._execute_pipeline(
                config.get('processing_steps', []),
                input_data,
                databases
            )
            
            # 6. Generate outputs
            print("📤 Generating outputs...")
            output_files = await self._generate_outputs(
                config.get('outputs', []),
                pipeline_results,
                input_data,
                config
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
        """Process input files and parameters"""
        
        input_data = {}
        
        for input_spec in inputs_config:
            input_name = input_spec['name']
            input_type = input_spec['type']
            required = input_spec.get('required', False)
            
            if input_type == 'file':
                # Get file from user
                file_path = input(f"📁 Enter path for {input_name} ({input_spec.get('description', '')}): ").strip().strip('"\'')
                
                if not file_path and required:
                    raise ValueError(f"Required input '{input_name}' not provided")
                
                if file_path and Path(file_path).exists():
                    file_data = self.file_processor.process_file(file_path)
                    input_data[input_name] = file_data
                    print(f"✅ Processed {input_name}: {len(file_data['content'])} characters")
                elif required:
                    raise FileNotFoundError(f"Input file not found: {file_path}")
            
            elif input_type == 'text':
                default = input_spec.get('default', '')
                value = input(f"📝 Enter {input_name} (default: {default}): ").strip() or default
                input_data[input_name] = value
            
            elif input_type == 'option':
                options = input_spec.get('options', [])
                default = input_spec.get('default', options[0] if options else '')
                print(f"📋 Select {input_name}:")
                for i, option in enumerate(options, 1):
                    print(f"  {i}. {option}")
                
                choice = input(f"Enter choice (1-{len(options)}, default: {default}): ").strip()
                if choice and choice.isdigit():
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(options):
                        input_data[input_name] = options[choice_idx]
                    else:
                        input_data[input_name] = default
                else:
                    input_data[input_name] = default
            
            elif input_type == 'number':
                default = input_spec.get('default', 0)
                value = input(f"🔢 Enter {input_name} (default: {default}): ").strip()
                try:
                    input_data[input_name] = int(value) if value else default
                except ValueError:
                    input_data[input_name] = default
        
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
        
        return smart_databases
    
    async def _execute_pipeline(self, 
                               steps: List[Dict[str, Any]], 
                               input_data: Dict[str, Any], 
                               databases: Dict[str, SmartDatabaseWrapper]) -> Dict[str, Any]:
        """Execute the processing pipeline"""
        
        results = {}
        
        # Create template context
        context = {
            **input_data,
            'databases': databases,
            'timestamp': datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        }
        
        for step in steps:
            step_name = step['name']
            prompt_template = step['prompt_template']
            dependencies = step.get('dependencies', [])
            timeout = step.get('timeout', 120)
            
            print(f"⚙️ Executing step: {step_name}")
            
            # Check dependencies
            for dep in dependencies:
                if dep not in results:
                    raise ValueError(f"Step '{step_name}' depends on '{dep}' which hasn't been executed")
            
            # Add previous results to context
            for dep in dependencies:
                context[dep] = results[dep]

            # CHUNKED LLM STEP (example for recommend_meters)
            if step_name == "recommend_meters":
                # Get clauses from previous step result
                extract_clauses_result = results.get('extract_clauses', {})
                parsed = extract_clauses_result.get('parsed_result', {})
                context['clauses'] = parsed.get('clauses', [])
                # Get meters (you may want to limit or filter here)
                context['meters'] = databases['meters'].query("SELECT model_name, series_name, selection_blurb FROM Meters LIMIT 10")
                chunked_result = await self._execute_chunked_llm_step(
                    step, context, chunk_key="clauses", chunk_size=5, meters_key="meters"
                )
                results[step_name] = chunked_result
                print(f"✅ Step '{step_name}' completed (chunked)")
                continue

            # Normal (non-chunked) step
            # Render template
            try:
                template = self.jinja_env.from_string(prompt_template)
                rendered_prompt = template.render(**context)
                
                print(f"📝 Rendered prompt ({len(rendered_prompt)} chars)")
                
                # Execute with LLM
                step_result = await self.llm_processor.process_prompt(rendered_prompt, timeout)
                results[step_name] = step_result
                
                print(f"✅ Step '{step_name}' completed")
                
            except Exception as e:
                print(f"❌ Step '{step_name}' failed: {e}")
                raise
        
        return results
    
    async def _generate_outputs(self, 
                              outputs_config: List[Dict[str, Any]], 
                              pipeline_results: Dict[str, Any],
                              input_data: Dict[str, Any],
                              config: Dict[str, Any]) -> List[str]:
        """Generate output files"""
        
        output_files = []
        
        # Create context for output rendering
        context = {
            **input_data,
            **pipeline_results,
            'timestamp': datetime.utcnow().strftime('%Y%m%d_%H%M%S'),
            'config': config
        }
        
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
                data = output_spec.get('data', pipeline_results)
                if isinstance(data, str):
                    # Data is a template string
                    data_template = self.jinja_env.from_string(data)
                    data = data_template.render(**context)
                    try:
                        data = json.loads(data)
                    except:
                        pass
                elif isinstance(data, dict):
                    # Data is a structure with template values
                    data = self._render_template_dict(data, context)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str)
                
            elif output_type == 'markdown':
                template_file = output_spec.get('template')
                if template_file and Path(template_file).exists():
                    with open(template_file, 'r', encoding='utf-8') as f:
                        template_content = f.read()
                else:
                    template_content = output_spec.get('content', '# Results\\n\\n{{ pipeline_results | tojson(indent=2) }}')
                
                template = self.jinja_env.from_string(template_content)
                content = template.render(**context)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            elif output_type == 'text':
                content_template = output_spec.get('content', '{{ pipeline_results }}')
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
        - chunk_key: The key in context to chunk (e.g., 'clauses').
        - chunk_size: Number of items per chunk.
        - meters_key: The key for meters in context.
        Returns: Aggregated result dictionary.
        """
        prompt_template = step['prompt_template']
        timeout = step.get('timeout', 120)
        all_items = context[chunk_key]
        meters = context.get(meters_key)
        aggregated_recommendations = []

        def chunk_list(lst, n):
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        for chunk in chunk_list(all_items, chunk_size):
            chunk_context = context.copy()
            chunk_context[chunk_key] = chunk
            if meters is not None:
                chunk_context[meters_key] = meters
            template = self.jinja_env.from_string(prompt_template)
            rendered_prompt = template.render(**chunk_context)
            print(f"📝 [Chunked] Rendered prompt ({len(rendered_prompt)} chars, {len(chunk)} items)")
            chunk_result = await self.llm_processor.process_prompt(rendered_prompt, timeout)
            # Expecting chunk_result to be a dict with 'recommendations' key
            if isinstance(chunk_result, dict):
                # If recommendations are present at the top level
                if 'recommendations' in chunk_result:
                    aggregated_recommendations.extend(chunk_result['recommendations'])
                    continue
                # If raw_response is present, try to parse it as JSON
                if 'raw_response' in chunk_result:
                    try:
                        parsed = json.loads(chunk_result['raw_response'])
                        if 'recommendations' in parsed:
                            aggregated_recommendations.extend(parsed['recommendations'])
                            continue
                    except Exception as e:
                        print("⚠️ Could not parse raw_response as JSON:", e)
                print("⚠️ Chunk result missing 'recommendations', skipping this chunk.")
            else:
                print("⚠️ Chunk result is not a dict, skipping this chunk.")

        return {"recommendations": aggregated_recommendations}



