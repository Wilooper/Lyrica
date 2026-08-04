import ast
import json
import os
import glob

def parse_flask_file(file_path):
    """Parses a Python file AST to find Flask routes without executing code."""
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except SyntaxError:
            return {}

    paths = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                # Check for decorators like @app.route(...) or @blueprint.route(...)
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == "route":
                        
                        # Extract route path (first argument)
                        route_path = None
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            route_path = str(decorator.args[0].value)

                        if not route_path:
                            continue

                        # Convert Flask path format `/user/<id>` to OpenAPI `/user/{id}`
                        openapi_path = route_path.replace("<", "{").replace(">", "}")

                        # Extract HTTP methods (default to GET)
                        methods = ["get"]
                        for keyword in decorator.keywords:
                            if keyword.arg == "methods" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                                methods = [
                                    elt.value.lower() 
                                    for elt in keyword.value.elts 
                                    if isinstance(elt, ast.Constant)
                                ]

                        # Extract docstring for endpoint description
                        docstring = ast.get_docstring(node) or f"Endpoint for {node.name}"

                        if openapi_path not in paths:
                            paths[openapi_path] = {}

                        for method in methods:
                            paths[openapi_path][method] = {
                                "summary": node.name.replace("_", " ").title(),
                                "description": docstring,
                                "operationId": f"{node.name}_{method}",
                                "responses": {
                                    "200": {
                                        "description": "Successful response"
                                    }
                                }
                            }
    return paths

def generate_openapi_spec():
    all_paths = {}

    # Scan all .py files recursively
    for file_path in glob.glob("**/*.py", recursive=True):
        if any(ignored in file_path for ignored in ["venv", ".venv", "tests", "scripts", "__pycache__"]):
            continue

        file_paths = parse_flask_file(file_path)
        for path, methods in file_paths.items():
            if path not in all_paths:
                all_paths[path] = {}
            all_paths[path].update(methods)

    openapi_document = {
        "openapi": "3.1.0",
        "info": {
            "title": "Flask API Documentation",
            "version": "1.0.0",
            "description": "Auto-generated OpenAPI documentation using static AST parsing."
        },
        "paths": all_paths
    }

    with open("openapi.json", "w", encoding="utf-8") as f:
        json.dump(openapi_document, f, indent=2)

    print(f"Parsed {len(all_paths)} routes successfully into openapi.json!")

if __name__ == "__main__":
    generate_openapi_spec()
