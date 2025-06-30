from typing import List, Any

def safe_remove_duplicates(seq: List[Any]) -> List[Any]:
    """
    Remove duplicates from a list while preserving order.
    """
    seen = set()
    result = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Format a float as a percentage string with specified decimals.
    """
    return f"{value:.{decimals}f}%"

def truncate_text(text: str, max_length: int = 50) -> str:
    """
    Truncate text to a maximum length, adding ellipsis if needed.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

# Add any other generic utility functions here