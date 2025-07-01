# core/llm_processor.py
import json
import re
import asyncio
from typing import Dict, Any, Optional

class LLMProcessor:
    """Handle LLM interactions using ollama"""
    
    def __init__(self, model: str = "qwen2.5-coder:7b"):
        self.model = model
    
    async def process_prompt(self, prompt: str, timeout: int = 120) -> Dict[str, Any]:
        """Process a prompt with the LLM and return structured result"""
        
        try:
            # Import ollama here to avoid dependency issues if not installed
            import ollama
            
            print(f"🤖 Processing with {self.model}...")
            
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": 0.1,
                    "timeout": timeout,
                    "num_ctx": 8192,
                    "num_predict": 4096
                }
            )
            
            ai_content = response['message']['content']
            
            # Try to extract JSON from response
            json_result = self._extract_json_from_response(ai_content)
            
            return {
                'raw_response': ai_content,
                'parsed_result': json_result,
                'success': True
            }
            
        except ImportError:
            # Fallback if ollama not available
            print("⚠️ Ollama not available, using mock response")
            return {
                'raw_response': f"Mock response for prompt: {prompt[:100]}...",
                'parsed_result': {"mock": True, "message": "Ollama not available"},
                'success': True
            }
        except Exception as e:
            print(f"❌ LLM processing failed: {e}")
            return {
                'error': str(e),
                'success': False
            }
    
    def _extract_json_from_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response"""
        
        # Try to find JSON in the response
        json_pattern = re.compile(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', re.DOTALL)
        matches = json_pattern.findall(text)
        
        # Try each match, from longest to shortest
        if matches:
            matches.sort(key=len, reverse=True)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        
        # If no JSON found, return the text as a message
        return {"message": text}