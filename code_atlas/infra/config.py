from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AtlasConfig:
    """Central configuration for Code Atlas."""
    
    # Default paths
    app_data_dir: Path = field(default_factory=lambda: Path(os.getenv("CODE_ATLAS_DATA_DIR", "~/.code-atlas")).expanduser())
    default_graph_name: str = "code-atlas.graph.json"
    default_cache_name: str = "code-atlas.cache.json"
    
    # Indexing settings
    exclude_dirs: set[str] = field(default_factory=lambda: {
        ".git", ".hg", ".svn", "tmp", ".venv", "venv", "node_modules",
        "dist", "build", "target", "__pycache__", ".mypy_cache",
        ".pytest_cache", ".idea", ".vscode",
    })
    
    # Resource limits
    max_visual_nodes: int = 800
    default_find_limit: int = 20
    default_callers_limit: int = 50
    default_impact_depth: int = 3
    default_path_max_depth: int = 12

    @property
    def tmp_dir(self) -> Path:
        """Get or create the temporary directory for artifacts."""
        tmp = Path("tmp")
        tmp.mkdir(exist_ok=True)
        return tmp.resolve()

    @property
    def default_graph_path(self) -> Path:
        return self.tmp_dir / self.default_graph_name

config = AtlasConfig()
