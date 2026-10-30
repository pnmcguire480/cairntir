"""Preserve the Python 3.11 syntax contract across AST schema versions."""

import ast
import copy


def dump_contract(node: ast.AST) -> str:
    node = copy.deepcopy(node)
    for child in ast.walk(node):
        if (
            isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and getattr(child, "type_params", None) == []
        ):
            child._fields = tuple(field for field in child._fields if field != "type_params")
    return ast.dump(node, include_attributes=False)
