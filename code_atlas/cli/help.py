from __future__ import annotations


def interactive_help() -> str:
    return "\n".join(
        [
            "Interactive commands:",
            "  help                                        Show this message",
            "  index <repo-or-github-url> [--out PATH] [--exclude dir1,dir2]",
            "                                              Index source to graph JSON",
            "  load [PATH]                                 Load a graph JSON file",
            "  stats                                       Show graph statistics",
            "  find <name> [--limit N]                     Find symbol by fuzzy name",
            "  callers <symbol> [--limit N]                Show callers of a symbol",
            "  related <file> [--depth N] [--limit N]      Show related files",
            "  path <from> <to> [--max-depth N]            Trace shortest path between symbols",
            "  impact <symbol> [--depth N] [--limit N]     Show blast radius for symbol changes",
            "  export graphml [--out PATH]                 Export graph to GraphML",
            "  export neo4j [--out DIR]                    Export graph to Neo4j CSV files",
            "  visual <symbol> [--depth N] [--limit N]     Open interactive browser graph",
            "  visual-all [--limit N] [--out PATH]         Open full-graph browser view",
            "  where                                       Show current graph path",
            "  raw on|off                                  Toggle JSON raw output",
            "  clear                                       Clear the screen",
            "  exit | quit                                 Leave interactive mode",
        ]
    )
