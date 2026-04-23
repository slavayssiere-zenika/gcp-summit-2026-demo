import ast
import os

def find_silent_errors(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            content = f.read()
            tree = ast.parse(content)
        except Exception:
            return []
    
    issues = []
    
    class Visitor(ast.NodeVisitor):
        def visit_ExceptHandler(self, node):
            has_raise = False
            has_return = False
            # Check what's inside the except block
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Raise):
                    has_raise = True
                elif isinstance(stmt, ast.Return):
                    has_return = True
            
            # If it doesn't raise or return anything
            if not has_raise and not has_return:
                issues.append((node.lineno, "Except block does not raise or return."))
            
            # If it only contains "pass"
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                issues.append((node.lineno, "Silent pass in except block."))
                
            self.generic_visit(node)

    Visitor().visit(tree)
    return issues

if __name__ == "__main__":
    count = 0
    for root, dirs, files in os.walk("."):
        if ".venv" in root or "__pycache__" in root or "node_modules" in root or ".terraform" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                res = find_silent_errors(filepath)
                if res:
                    for r in res:
                        print(f"{filepath}:{r[0]} - {r[1]}")
                        count += 1
    print(f"Total silent errors found: {count}")
