import ast


def parse():
  filepath = "./sample.py"
  
  # read the python file
  with open(filepath, "r") as f:
    # get the whole content of the file
    content = f.read().strip()

    # transform the content into a tree
    tree = ast.parse(content)

    # traverse the tree to get the nodes
    nodes = list(ast.walk(tree))
    result = []

    for node in nodes:

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
                    "name": alias.name
                })

        # From imports
        elif isinstance(node, ast.ImportFrom):
            module = node.module
            for alias in node.names:
                result.append({
                    "type": "from_import",
                    "module": module,
                    "name": alias.name
                })

        # Function calls
        elif isinstance(node, ast.Call):
            func_name = node.func.id if isinstance(node.func, ast.Name) else "<complex>"
            args = []
            for a in node.args:
                if isinstance(a, ast.Constant):
                    args.append(a.value)
                elif isinstance(a, ast.Name):
                    args.append(a.id)
            result.append({
                "type": "call",
                "function": func_name,
                "args": args
            })

    print(result)
