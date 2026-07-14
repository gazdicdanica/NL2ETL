import ast

FORBIDDEN = {
    "eval",
    "exec",
    "__import__",
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "shutil",
    "sys",
}

FORBIDDEN_ATTRS = {"system", "popen", "rmtree", "remove", "unlink"}


class SafeVisitor(ast.NodeVisitor):
    def __init__(self):
        self.violations = []

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN:
            self.violations.append(f"Forbidden function call: {node.func.id}")
        elif isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRS:
            self.violations.append(f"Forbidden attribute call: {node.func.attr}")
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name.split(".")[0] in FORBIDDEN:
                self.violations.append(f"Forbidden import: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module and node.module.split(".")[0] in FORBIDDEN:
            self.violations.append(f"Forbidden import: {node.module}")
        self.generic_visit(node)


def validate_code(code: str) -> tuple[bool, list[str]]:
    print("\nValidating generated code for safety...")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"Syntax error: {e}"]

    visitor = SafeVisitor()
    visitor.visit(tree)

    if visitor.violations:
        return False, visitor.violations
    return True, []
