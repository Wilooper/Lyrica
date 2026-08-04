import ast
import json
import glob
import re

class RouteVisitor(ast.NodeVisitor):
    def __init__(self):
        self.query_params = set()
        self.body_params = set()
        self.return_keys = set()

    def visit_Call(self, node):
        # 1. Catch request.args.get('param_name')
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'get':
            if isinstance(node.func.value, ast.Attribute) and node.func.value.attr == 'args':
                if node.args and isinstance(node.args[0], ast.Constant):
                    self.query_params.add(str(node.args[0].value))

        # 2. Catch request.json.get('key') or request.get_json().get('key')
        if isinstance(node.func, ast.Attribute) and node.func.attr in ('get', 'get_json'):
            if isinstance(node.func.value, ast.Attribute) and node.func.value.attr == 'json':
                if node.args and isinstance(node.args[0], ast.Constant):
                    self.body_params.add(str(node.args[0].value))

        # 3. Catch jsonify(key=value) or jsonify({"key": ...})
        if isinstance(node.func, ast.Name) and node.func.id == 'jsonify':
            for keyword in node.keywords:
                self.return_keys.add(keyword.arg)
            if node.args and isinstance(node.args[0], ast.Dict):
                for key in node.args[0].keys:
                    if isinstance(key, ast.Constant):
                        self.return_keys.add(str(key.value))

        self.generic_visit(node)

    def visit_Return(self, node):
        # Catch direct dictionary returns: return {"status": "ok"}
        if isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant):
                    self.return_keys.add(str(key.value))
        self.generic_visit(node)

def parse_flask_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except SyntaxError:
            return {}

    paths = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == "route":
                        
                        route_path = None
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            route_path = str(decorator.args[0].value)

                        if not route_path:
                            continue

                        # Extract route path variables: /user/<user_id> or /user/<int:user_id>
                        path_vars = re.findall(r'<(?:\w+:)?(\w+)>', route_path)
                        openapi_path = re.sub(r'<(?:(\w+):)?(\w+)>', r'{\2}', route_path)

                        # Extract methods
                        methods = ["get"]
                        for keyword in decorator.keywords:
                            if keyword.arg == "methods" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                                methods = [
                                    elt.value.lower() 
                                    for elt in keyword.value.elts 
                                    if isinstance(elt, ast.Constant)
                                ]

                        # Inspect function body for parameters and response structure
                        visitor = RouteVisitor()
                        visitor.visit(node)

                        docstring = ast.get_docstring(node) or f"Endpoint for {node.name}"

                        # Build parameters list (Path + Query)
                        parameters = []
                        for var in path_vars:
                            parameters.append({
                                "name": var,
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"}
                            })

                        for q_param in visitor.query_params:
                            if q_param not in path_vars:
                                parameters.append({
                                    "name": q_param,
                                    "in": "query",
                                    "required": False,
                                    "schema": {"type": "string"}
                                })

                        if openapi_path not in paths:
                            paths[openapi_path] = {}

                        for method in methods:
                            operation = {
                                "summary": node.name.replace("_", " ").title(),
                                "description": docstring,
                                "operationId": f"{node.name}_{method}",
                                "parameters": parameters,
                                "responses": {
                                    "200": {
                                        "description": "Successful response",
                                        "content": {
                                            "application/json": {
                                                "schema": {
                                                    "type": "object",
                                                    "properties": {
                                                        k: {"type": "string"} for k in visitor.return_keys
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            # Add requestBody for POST/PUT/PATCH if JSON fields were detected
                            if method in ["post", "put", "patch"] and visitor.body_params:
                                operation["requestBody"] = {
                                    "required": True,
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "type": "object",
                                                "properties": {
                                                    k: {"type": "string"} for k in visitor.body_params
                                                }
                                            }
                                        }
                                    }
                                }

                            paths[openapi_path][method] = operation
    return paths

def generate_openapi_spec():
    all_paths = {}

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
            "description": "Auto-generated OpenAPI documentation using AST static analysis."
        },
        "paths": all_paths
    }

    with open("openapi.json", "w", encoding="utf-8") as f:
        json.dump(openapi_document, f, indent=2)

    print(f"Generated complete schema with parameters & responses for {len(all_paths)} routes!")

if __name__ == "__main__":
    generate_openapi_spec()
