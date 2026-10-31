"""Strict compatibility controls for the Python 3.11 protected AST contract."""

from __future__ import annotations

import ast
import hashlib
import json
import runpy
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _ROOT / "tests/acceptance/ideation_assembler_unit"
_CONTRACT_HASH = "88a10c5b5d76d898263efdd3712072d4c378d5c34b9c2cd1bbe08703ef830a45"
_ARGUMENTS = "arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[])"
_FUNCTION = (
    f"FunctionDef(name='sample', args={_ARGUMENTS}, "
    "body=[Return(value=Constant(value=7))], decorator_list=[])"
)
_ASYNC_FUNCTION = (
    f"AsyncFunctionDef(name='sample', args={_ARGUMENTS}, "
    "body=[Return(value=Constant(value=7))], decorator_list=[])"
)
_CLASS = "ClassDef(name='Sample', bases=[], keywords=[], body=[Pass()], decorator_list=[])"
_DECLARATIONS = (
    ("def sample():\n    return 7\n", _FUNCTION),
    ("async def sample():\n    return 7\n", _ASYNC_FUNCTION),
    ("class Sample:\n    pass\n", _CLASS),
)
_NESTED_SOURCE = (
    "class Outer:\n"
    "    def inner():\n"
    "        async def again():\n"
    "            return 7\n"
    "        return 9\n"
)
_NESTED_DUMP = (
    "ClassDef(name='Outer', bases=[], keywords=[], body=["
    f"FunctionDef(name='inner', args={_ARGUMENTS}, body=["
    f"AsyncFunctionDef(name='again', args={_ARGUMENTS}, "
    "body=[Return(value=Constant(value=7))], decorator_list=[]), "
    "Return(value=Constant(value=9))], decorator_list=[])], decorator_list=[])"
)


class TypeVar(ast.AST):
    _fields = ("name", "bound")


def _dump(node: ast.AST) -> str:
    return runpy.run_path(str(_PACKAGE / "ast_contract.py"))["dump_contract"](node)


def _definition(source: str) -> ast.AST:
    node = ast.parse(source).body[0]
    for child in ast.walk(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if "type_params" not in child._fields:
                child._fields = (*child._fields, "type_params")
            child.type_params = []
    return node


class TestASTContractCompatibility(unittest.TestCase):
    def test_empty_version_added_fields_match_exact_legacy_dumps(self) -> None:
        for source, expected in _DECLARATIONS:
            with self.subTest(source=source):
                self.assertEqual(_dump(_definition(source)), expected)

    def test_nested_definition_fields_match_exact_legacy_dump(self) -> None:
        self.assertEqual(_dump(_definition(_NESTED_SOURCE)), _NESTED_DUMP)

    def test_nonempty_generic_parameters_are_retained(self) -> None:
        for source, expected in _DECLARATIONS:
            with self.subTest(source=source):
                node = _definition(source)
                node.type_params = [
                    getattr(ast, "TypeVar", TypeVar)(
                        name="T", bound=ast.Name(id="Base", ctx=ast.Load())
                    )
                ]
                expected_generic = (
                    expected[:-1]
                    + ", type_params=[TypeVar(name='T', bound=Name(id='Base', ctx=Load()))])"
                )
                self.assertEqual(_dump(node), expected_generic)
                self.assertNotEqual(_dump(node), expected)

    def test_body_constant_drift_remains_exactly_visible(self) -> None:
        for source, expected in _DECLARATIONS[:2]:
            with self.subTest(source=source):
                changed = _definition(source.replace("return 7", "return 8"))
                self.assertEqual(_dump(changed), expected.replace("value=7", "value=8"))
                self.assertNotEqual(_dump(changed), expected)

    def test_decorators_and_annotations_are_retained(self) -> None:
        node = _definition("@guard\ndef sample() -> int:\n    return 7\n")
        expected = (
            f"FunctionDef(name='sample', args={_ARGUMENTS}, "
            "body=[Return(value=Constant(value=7))], "
            "decorator_list=[Name(id='guard', ctx=Load())], returns=Name(id='int', ctx=Load()))"
        )
        self.assertEqual(_dump(node), expected)
        self.assertNotEqual(_dump(node), _FUNCTION)

    def test_type_params_text_inside_constants_is_retained(self) -> None:
        node = _definition("def sample():\n    return ', type_params=[]'\n")
        expected = _FUNCTION.replace("Constant(value=7)", "Constant(value=', type_params=[]')")
        self.assertEqual(_dump(node), expected)
        self.assertEqual(
            _dump(ast.Constant(value=", type_params=[]")), "Constant(value=', type_params=[]')"
        )

    def test_same_named_field_on_unrelated_node_is_retained(self) -> None:
        node = ast.Constant(value=7)
        node._fields = (*node._fields, "type_params")
        node.type_params = []
        self.assertEqual(_dump(node), "Constant(value=7, type_params=[])")

    def test_other_empty_fields_on_definition_are_retained(self) -> None:
        node = _definition(_DECLARATIONS[0][0])
        node._fields = (*node._fields, "future_empty")
        node.future_empty = []
        self.assertEqual(_dump(node), _FUNCTION[:-1] + ", future_empty=[])")

    def test_input_ast_and_field_definitions_are_unchanged(self) -> None:
        node = _definition(_NESTED_SOURCE)
        before = ast.dump(node, include_attributes=True)
        fields_before = [(type(child), child._fields) for child in ast.walk(node)]
        self.assertEqual(_dump(node), _NESTED_DUMP)
        self.assertEqual(ast.dump(node, include_attributes=True), before)
        self.assertEqual([(type(child), child._fields) for child in ast.walk(node)], fields_before)
        self.assertEqual(_dump(node), _NESTED_DUMP)

    def test_original_golden_bytes_and_constants_are_unchanged(self) -> None:
        raw = (_PACKAGE / "V1-CONTRACT.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), _CONTRACT_HASH)
        self.assertEqual(
            json.loads(raw)["constants"],
            {
                "options": {"num_predict": 4096, "num_ctx": 16384, "temperature": 0},
                "prefix_sha256": "aa8e1ff6ec2764fe252a5ba74f9c7622ae8a6c46ada9a6074ade4f68927e767e",
            },
        )

    def test_all_nine_original_runtime_ast_goldens_match(self) -> None:
        baseline = json.loads((_PACKAGE / "V1-CONTRACT.json").read_bytes())
        self.assertEqual(
            set(baseline["protected_v1_ast"]),
            {
                "OllamaOutlinesAdapter",
                "_identity",
                "_schema",
                "_wire",
                "_output",
                "_envelope",
                "_prepared",
                "_load",
                "_replay",
            },
        )
        tree = ast.parse((_ROOT / "src/cairntir/ideation_outlines.py").read_bytes())
        definitions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        for name, expected in baseline["protected_v1_ast"].items():
            with self.subTest(name=name):
                self.assertEqual(_dump(definitions[name]), expected)


if __name__ == "__main__":
    unittest.main()
