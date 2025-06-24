from dataclasses import dataclass
from typing import List, Dict, Optional

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