# my_package/__init__.py (dynamic __all__)
from pathlib import Path

__all__ = [
    module.stem for module in Path(__file__).parent.glob("*.py") if module.name != "__init__.py"
]