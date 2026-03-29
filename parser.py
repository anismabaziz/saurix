import ast

# Helper function to get full function name
def get_func_name(node):
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        # Recursively get the parent value
        return get_func_name(node.value) + "." + node.attr
    else:
        return "<unknown>"

def parse():
    filepath = "./sample.py"
    
    # read the python file
    with open(filepath, "r") as f:
        content = f.read().strip()
        tree = ast.parse(content)

        result = []

        # traverse all nodes
        for node in ast.walk(tree):

            # Function definitions
            if isinstance(node, ast.FunctionDef):
                result.append({
                    "type": "function",
                    "name": node.name,
                    "arguments": [arg.arg for arg in node.args.args]
                })

            # Simple imports
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    result.append({
                        "type": "import",
                        "name": alias.name,
                        "as": alias.asname  # None if no alias
                    })

            # From imports
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                for alias in node.names:
                    result.append({
                        "type": "from_import",
                        "module": module,
                        "name": alias.name,
                        "as": alias.asname
                    })

            # Function calls
            elif isinstance(node, ast.Call):
                func_name = get_func_name(node.func)

                args = []
                # Positional arguments
                for a in node.args:
                    if isinstance(a, ast.Constant):
                        args.append(a.value)
                    elif isinstance(a, ast.Name):
                        args.append(a.id)
                    else:
                        args.append("<expr>")  # anything more complex

                # Keyword arguments
                kwargs = {}
                for kw in node.keywords:
                    if isinstance(kw.value, ast.Constant):
                        kwargs[kw.arg] = kw.value.value
                    elif isinstance(kw.value, ast.Name):
                        kwargs[kw.arg] = kw.value.id
                    else:
                        kwargs[kw.arg] = "<expr>"

                result.append({
                    "type": "call",
                    "function": func_name,
                    "args": args,
                    "kwargs": kwargs
                })

        print(result)
