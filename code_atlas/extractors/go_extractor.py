from __future__ import annotations

import re

from .regex_lang import RegexLangExtractor


class GoExtractor(RegexLangExtractor):
    def __init__(self) -> None:
        super().__init__(
            language="go",
            import_pattern=re.compile(r"import\s+(?:\(\s*)?(?:[\w\.]+\s+)?\"(?P<target>[^\"]+)\"", re.MULTILINE),
            function_pattern=re.compile(r"func\s+(?:\([^\)]*\)\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE),
            call_pattern=re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("),
        )
