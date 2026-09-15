"""Access to packaged data files.

Locates control set JSON files using importlib.resources (Python 3.9+),
with fallback to repository-level controls/ for development scenarios.
"""

import os
from contextlib import contextmanager
from importlib import resources


@contextmanager
def _get_resource_path(filename):
    """Context manager providing a filesystem path to a packaged resource.
    
    Uses importlib.resources.as_file() for Python 3.9+ compatibility.
    Resources are accessed through the package data structure.
    
    Args:
        filename: Name of the resource file (e.g., 'e8-2023-11.json')
    
    Yields:
        str: Filesystem path to the resource file
    
    Raises:
        FileNotFoundError: If resource cannot be located
    """
    try:
        # Python 3.9+: use importlib.resources.files() with as_file() context manager
        ref = resources.files('e8').joinpath('data', filename)
        with resources.as_file(ref) as path:
            if path.exists():
                yield str(path)
                return
    except (ModuleNotFoundError, AttributeError, TypeError):
        # Fallback: resource API unavailable or resource not found
        pass
    
    # Fallback to repository-level controls/ (for development)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fallback_path = os.path.join(repo_root, 'controls', filename)
    if os.path.exists(fallback_path):
        yield fallback_path
        return
    
    raise FileNotFoundError(
        f"Control set '{filename}' not found in package data (e8/data/) "
        f"or repository controls/ directory. Installation may be corrupted."
    )


def get_control_set_path(filename):
    """Get the filesystem path to a control set file.
    
    Returns the path from packaged resources if installed via pip,
    otherwise falls back to repository-level controls/ for development.
    
    This is a convenience wrapper that extracts the path from the
    context manager without requiring caller to use 'with' syntax.
    
    Args:
        filename: Name of the control set file (e.g., 'e8-2023-11.json')
    
    Returns:
        str: Absolute filesystem path to the control set file
    
    Raises:
        FileNotFoundError: If the control set cannot be located
    """
    with _get_resource_path(filename) as path:
        return path
