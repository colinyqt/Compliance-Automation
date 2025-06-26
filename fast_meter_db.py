import json
import re
from typing import Dict, List, Any, Optional

class MeterDatabase:
    """Fast in-memory database for meter specifications with efficient lookups"""
    
    def __init__(self, json_path="testing.json"):
        """Initialize the database from a JSON file"""
        self.meters = {}  # Main storage for meter data
        self.load_data(json_path)
        
    def load_data(self, json_path):
        """Load meter data from JSON file"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Process each series
            for series_key, models in data.items():
                if isinstance(models, list):
                    for meter in models:
                        self._process_meter(meter, series_key)
        except Exception as e:
            print(f"Error loading meter data: {e}")
    
    def _process_meter(self, meter_data, series_key):
        """Process a single meter's data and add to the database"""
        if "model_name" not in meter_data:
            return
            
        model_name = meter_data["model_name"]
        
        # Create normalized keys for lookup
        keys = [model_name.upper()]
        
        # Extract device short name if available
        short_name = None
        if "specifications" in meter_data and "Main" in meter_data["specifications"]:
            main_specs = meter_data["specifications"]["Main"]
            if "Device_short_name" in main_specs:
                short_name = main_specs["Device_short_name"].strip()
                keys.append(short_name.upper())
        
        # Extract series from the key
        series_match = re.search(r'([A-Za-z]+)(\d+)', model_name)
        if series_match:
            series = series_match.group(1)
            keys.append(f"{series.upper()}")
        
        # Add the meter to our database with all its details
        processed_meter = self._normalize_meter_data(meter_data, series_key)
        
        # Store the meter data under all possible lookup keys
        for key in keys:
            self.meters[key] = processed_meter
    
    def _normalize_meter_data(self, meter_data, series_key):
        """Convert the JSON structure to a flat, normalized format for faster lookups"""
        result = {
            "model_name": meter_data.get("model_name", ""),
            "series": series_key,
            "description": meter_data.get("selection_blurb", ""),
            "measurement_accuracy": {},
            "accuracy_classes": [],
            "power_quality_features": [],
            "applications": [],
            "measurements": [],
            "certifications": [],
            "communication_protocols": {},
            "technical_details": {},
            "memory_capacity": "",
            "sampling_rate": ""
        }
        
        # Extract specifications from nested structure
        specs = meter_data.get("specifications", {})
        
        # Process main section
        if "Main" in specs:
            main = specs["Main"]
            if "Device_short_name" in main:
                result["device_short_name"] = main["Device_short_name"].strip()
            if "product_name" in main:
                result["product_name"] = main["product_name"].strip()
        
        # Process complementary section
        if "Complementary" in specs:
            comp = specs["Complementary"]
            
            # Extract device applications
            if "Device_application" in comp:
                apps = comp["Device_application"]
                result["applications"] = self._ensure_list(apps)
                
            # Extract power quality analysis features
            if "Power_quality_analysis" in comp:
                pq = comp["Power_quality_analysis"]
                result["power_quality_features"] = self._ensure_list(pq)
                
            # Extract measurements
            if "Type_of_measurement" in comp:
                measurements = comp["Type_of_measurement"]
                result["measurements"] = self._ensure_list(measurements)
            
            # Extract accuracy classes
            if "Accuracy_class" in comp:
                accuracy = comp["Accuracy_class"]
                result["accuracy_classes"] = self._ensure_list(accuracy)
            
            # Extract measurement accuracy
            if "Measurement_accuracy" in comp:
                if isinstance(comp["Measurement_accuracy"], dict):
                    result["measurement_accuracy"] = comp["Measurement_accuracy"]
            
            # Extract memory capacity
            if "Memory_capacity" in comp:
                result["memory_capacity"] = comp["Memory_capacity"]
                
            # Extract sampling rate
            if "Sampling_rate" in comp:
                result["sampling_rate"] = comp["Sampling_rate"]
                
            # Extract communication protocols
            if "Communication_port_protocol" in comp:
                protocols = comp["Communication_port_protocol"]
                if isinstance(protocols, list):
                    for protocol in protocols:
                        result["communication_protocols"][protocol] = "Supported"
                else:
                    result["communication_protocols"][protocols] = "Supported"
            
            # Extract all other technical details
            for key, value in comp.items():
                if key not in ["Device_application", "Power_quality_analysis", 
                               "Type_of_measurement", "Accuracy_class", 
                               "Measurement_accuracy", "Memory_capacity",
                               "Sampling_rate", "Communication_port_protocol"]:
                    if isinstance(value, (str, int, float, bool)):
                        result["technical_details"][key] = value
        
        return result
    
    def _ensure_list(self, value):
        """Ensure a value is a list"""
        if isinstance(value, list):
            return value
        else:
            return [value] if value else []
    
    def find_meter(self, model_number: str) -> Optional[Dict]:
        """Find a meter by its model number or device short name"""
        # Try exact match
        model_key = model_number.strip().upper()
        if model_key in self.meters:
            return self.meters[model_key]
        
        # Try with common variants
        variants = [
            model_key.replace(" ", ""),  # No spaces
            model_key + "0",             # Add trailing zero
            re.sub(r'(\d+)', r'\1', model_key)  # Remove trailing zeros
        ]
        
        for variant in variants:
            if variant in self.meters:
                return self.meters[variant]
        
        # Try partial match
        for key, meter in self.meters.items():
            if model_key in key or key in model_key:
                return meter
        
        # Try series match (e.g., "PM5000" should match "PowerLogic PM5320")
        series_match = re.match(r'([A-Za-z]+)(\d+)', model_number)
        if series_match:
            series_prefix = series_match.group(1).upper()
            for key in self.meters:
                if key.startswith(series_prefix):
                    return self.meters[key]
        
        return None