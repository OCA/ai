import ast
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class AIExtraParameter(models.Model):
    _name = "ai.extra.parameter"
    _description = "AI Bridge Extra Parameter"

    name = fields.Char(required=True)
    expression = fields.Char()
    formula = fields.Text(
        default="if object:\n" "    result = {'result_key': object.property}\n",
    )
    parameter_type = fields.Selection(
        [
            ("record", "Record"),
            ("self", "Bridge Self"),
        ],
        required=True,
        default="record",
        help="Defines the context in which this parameter is evaluated. "
        "'record' means it will be evaluated in the context of the record being processed, "
        "'self' means it will be evaluated in the context of the AI bridge itself.",
    )

    evaluate_type = fields.Selection(
        [
            ("expression", "Expression"),
            ("formula", "Formula"),
        ],
        required=True,
        default="expression",
        help="Defines how the parameter is evaluated. "
        "'expression' means it will be evaluated as a Python expression, "
        "'formula' means it will be evaluated as a formula expression.",
    )
    FORBIDDEN_PATTERNS = [
        r"\.cr\b",
        r"\._cr\b",
        r"\.execute\s*\(",
        r"\.commit\s*\(",
        r"\.rollback\s*\(",
        r"\.sudo\s*\(",
        r"\.with_context\s*\(",
        r"\.write\s*\(",
        r"\.unlink\s*\(",
        r"\.invalidate_cache\s*\(",
        r"\.flush\s*\(",
        r"\.flush_all\s*\(",
        r"\bimport\b",
        r"\b(exec|eval)\s*\(",
        r"\bopen\s*\(",
        r"\bgetattr\s*\(",
        r"__\w+__",
    ]

    ALLOWED_EXPRESSION_NAMES = {
        "object",
        "True",
        "False",
        "None",
        "str",
        "int",
        "float",
        "bool",
        "len",
        "list",
        "map",
        "filter",
        "zip",
        "sum",
        "min",
        "max",
        "sorted",
        "enumerate",
        "range",
    }

    ALLOWED_FORMULA_CONTEXT_VARS = {
        "object",
        "record",
        "True",
        "False",
        "None",
        "str",
        "int",
        "float",
        "bool",
        "len",
        "list",
        "dict",
        "set",
        "tuple",
        "enumerate",
        "range",
        "zip",
        "map",
        "filter",
        "sum",
        "min",
        "max",
        "sorted",
        "abs",
        "round",
        "hasattr",
        "isinstance",
        "type",
        "Exception",
        "AttributeError",
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
        "ZeroDivisionError",
    }

    @staticmethod
    def _extract_variables_base(code, parse_mode, extractor_class, variable_attr):
        try:
            tree = ast.parse(code, mode=parse_mode)
            extractor = extractor_class()
            extractor.visit(tree)
            return getattr(extractor, variable_attr)
        except Exception:
            return set()

    @staticmethod
    def _extract_variables(expr):
        return AIExtraParameter._extract_variables_base(
            expr, "eval", ExpressionVariableExtractor, "variables"
        )

    @staticmethod
    def _extract_variables_from_code(code):
        return AIExtraParameter._extract_variables_base(
            code, "exec", FormulaVariableExtractor, "external_vars"
        )

    @classmethod
    def _validate_code_base(cls, code, parse_mode):
        try:
            ast.parse(code, mode=parse_mode)
        except SyntaxError as e:
            return False, f"Invalid Python syntax: {e}"
        except Exception as e:
            return False, f"Invalid {parse_mode}: {e}"

        for pattern in cls.FORBIDDEN_PATTERNS:
            if re.search(pattern, code):
                if r"\(" in pattern:
                    op_match = re.search(r"\\\.([\w_]+)", pattern)
                else:
                    op_match = re.search(r"\\\.([\w_]+)", pattern)
                operation = op_match.group(1) if op_match else "restricted operation"
                return False, f"Access to '{operation}' is not allowed"

        return True, ""

    @classmethod
    def _validate_expression(cls, expr):
        is_valid, error_msg = cls._validate_code_base(expr, "eval")
        if not is_valid:
            return is_valid, error_msg
        variables = cls._extract_variables(expr)
        invalid_vars = variables - cls.ALLOWED_EXPRESSION_NAMES

        if invalid_vars:
            return (
                False,
                f"Only 'object' variable is allowed, found: {', '.join(invalid_vars)}",
            )

        return True, ""

    @classmethod
    def _validate_formula(cls, formula):
        is_valid, error_msg = cls._validate_code_base(formula, "exec")
        if not is_valid:
            return is_valid, error_msg
        external_vars = cls._extract_variables_from_code(formula)

        invalid_vars = external_vars - cls.ALLOWED_FORMULA_CONTEXT_VARS
        if invalid_vars:
            return (
                False,
                f"Undefined variables: {', '.join(invalid_vars)}. "
                f"Available context variables are 'object' and 'record'.",
            )

        result_assigned = False
        tree = ast.parse(formula, mode="exec")
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "result":
                        result_assigned = True
                        break

        if not result_assigned:
            return False, "Formula must assign a value to 'result' variable"

        return True, ""

    def evaluate_parameter(self, obj=None):
        self.ensure_one()

        if self.evaluate_type == "expression":
            return self._evaluate_expression(obj)
        elif self.evaluate_type == "formula":
            result = self._evaluate_formula(obj)
            if isinstance(result, (str, int, float, bool, type(None), dict, list)):
                return result
            else:
                return str(result)
        else:
            raise ValidationError(_("Invalid evaluate_type"))

    def _evaluate_expression(self, obj=None):
        expression = self.expression or ""

        if expression.count("{") != expression.count("}"):
            raise ValidationError(_("Unbalanced braces in parameter expression."))

        if "{" not in expression or "}" not in expression:
            return expression

        pattern = r"\{([^{}]+(?:\{[^{}]*\}[^{}]*)*)\}"

        def evaluate_single_expression(match):
            expr = match.group(1).strip()

            is_valid, error_msg = self._validate_expression(expr)
            if not is_valid:
                raise ValidationError(_(f"Expression validation failed: {error_msg}"))

            eval_context = {
                "object": obj,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "len": len,
                "True": True,
                "False": False,
                "None": None,
            }

            try:
                result = safe_eval(expr, eval_context, mode="eval", nocopy=True)
                return str(result) if result is not None else ""
            except Exception as e:
                raise ValidationError(
                    _(f"Error evaluating expression '{expr}': {str(e)}")
                ) from e

        try:
            result = re.sub(pattern, evaluate_single_expression, expression)
            return result
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(
                _(f"Error processing parameter expression: {str(e)}")
            ) from e

    def _evaluate_formula(self, obj=None):
        formula = self.formula or ""

        if not formula.strip():
            raise ValidationError(_("Formula cannot be empty"))

        is_valid, error_msg = self._validate_formula(formula)
        if not is_valid:
            raise ValidationError(_(f"Formula validation failed: {error_msg}"))

        eval_context = {
            "object": obj,
            "record": obj,
            "result": None,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "len": len,
            "enumerate": enumerate,
            "range": range,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sum": sum,
            "min": min,
            "max": max,
            "sorted": sorted,
            "abs": abs,
            "round": round,
            "hasattr": hasattr,
            "isinstance": isinstance,
            "type": type,
            "Exception": Exception,
            "AttributeError": AttributeError,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "ZeroDivisionError": ZeroDivisionError,
            "True": True,
            "False": False,
            "None": None,
        }

        try:
            safe_eval(formula, eval_context, mode="exec", nocopy=True)
            return eval_context.get("result")
        except Exception as e:
            raise ValidationError(_(f"Error executing formula: {str(e)}")) from e

    def validate_parameter_expression(self):
        self.ensure_one()
        expression = self.expression or ""

        if expression.count("{") != expression.count("}"):
            raise ValidationError(_("Unbalanced braces in parameter expression."))

        expressions = []
        i = 0
        while i < len(expression):
            if expression[i] == "{":
                brace_count = 1
                j = i + 1
                while j < len(expression) and brace_count > 0:
                    if expression[j] == "{":
                        brace_count += 1
                    elif expression[j] == "}":
                        brace_count -= 1
                    j += 1
                if brace_count == 0:
                    expressions.append(expression[i + 1 : j - 1])
                i = j
            else:
                i += 1

        for expr in expressions:
            is_valid, error_msg = self._validate_expression(expr.strip())
            if not is_valid:
                raise ValidationError(_(f"Invalid expression '{expr}': {error_msg}"))

        return True

    def validate_parameter_formula(self):
        self.ensure_one()
        formula = self.formula or ""

        if not formula.strip():
            raise ValidationError(_("Formula cannot be empty"))

        is_valid, error_msg = self._validate_formula(formula)
        if not is_valid:
            raise ValidationError(_(f"Invalid formula: {error_msg}"))

        return True

    @api.constrains("expression", "formula", "evaluate_type")
    def _check_expression_or_formula(self):
        for record in self:
            try:
                if record.evaluate_type == "expression":
                    if record.expression:
                        record.validate_parameter_expression()
                elif record.evaluate_type == "formula":
                    if record.formula:
                        record.validate_parameter_formula()
            except ValidationError as e:
                raise ValidationError(_(f"Parameter '{record.name}': {e}")) from e


class ExpressionVariableExtractor(ast.NodeVisitor):
    """
    AST visitor that extracts external variables from Python expressions.

    This class is designed to analyze simple Python expressions (evaluated with eval())
    and identify which variables are referenced but not defined within the expression itself.
    It helps determine what external context variables are needed for expression evaluation.

    The extractor tracks:
    - Variables being read/accessed (ast.Load context)
    - Locally defined variables (function parameters, lambda arguments, etc.)
    - Attribute access on variables (e.g., object.property)

    Usage:
        tree = ast.parse("object.name + some_var", mode="eval")
        extractor = ExpressionVariableExtractor()
        extractor.visit(tree)
        external_vars = extractor.variables  # {'object', 'some_var'}

    Attributes:
        defined_vars (set): Variables defined locally within the expression scope
        variables (set): External variables that need to be provided in eval context
    """

    def __init__(self):
        self.defined_vars = set()
        self.variables = set()

    def visit_Lambda(self, node):
        old_defined_vars = self.defined_vars.copy()
        if hasattr(node, "args") and node.args:
            for arg in node.args.args:
                self.defined_vars.add(arg.arg)

        self.generic_visit(node)
        self.defined_vars = old_defined_vars

    def visit_FunctionDef(self, node):
        self.defined_vars.add(node.name)
        old_defined_vars = self.defined_vars.copy()

        for arg in node.args.args:
            self.defined_vars.add(arg.arg)

        self.generic_visit(node)
        self.defined_vars = old_defined_vars

    def visit_ExceptHandler(self, node):
        if node.name:
            self.defined_vars.add(node.name)
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            if node.id not in self.defined_vars:
                self.variables.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name):
            if node.value.id not in self.defined_vars:
                self.variables.add(node.value.id)
        self.generic_visit(node)


class FormulaVariableExtractor(ast.NodeVisitor):
    """
    AST visitor that extracts external variables from complex Python code.

    This class analyzes complete Python code blocks (executed with exec()) to identify
    which variables are referenced but not defined within the code itself. It handles
    complex Python constructs including assignments, loops, functions, lambdas, and
    comprehensions with proper scope tracking.

    The extractor handles:
    - Variable assignments and definitions (visit_Assign, visit_For)
    - Function and lambda parameter scoping (visit_FunctionDef, visit_Lambda)
    - List/dict/set comprehensions with isolated variable scopes
    - Exception handler variable binding (visit_ExceptHandler)
    - Proper scope restoration for nested constructs

    Unlike ExpressionVariableExtractor, this class maintains a scope stack to handle
    complex nested structures like comprehensions where variables have limited scope.

    Usage:
        code = "result = object.name if hasattr(object, 'name') else 'default'"
        tree = ast.parse(code, mode="exec")
        extractor = FormulaVariableExtractor()
        extractor.visit(tree)
        external_vars = extractor.external_vars  # {'object', 'hasattr'}

    Attributes:
        defined_vars (set): Variables defined in the current scope
        comp_vars_stack (list): Stack of comprehension-scoped variables
        external_vars (set): External variables that need to be provided in exec context
    """

    def __init__(self):
        self.defined_vars = set()
        self.comp_vars_stack = []
        self.external_vars = set()

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.defined_vars.add(target.id)
        self.generic_visit(node)

    def visit_For(self, node):
        if isinstance(node.target, ast.Name):
            self.defined_vars.add(node.target.id)
        elif isinstance(node.target, ast.Tuple):
            for elt in node.target.elts:
                if isinstance(elt, ast.Name):
                    self.defined_vars.add(elt.id)
        self.generic_visit(node)

    def visit_Lambda(self, node):
        old_defined_vars = self.defined_vars.copy()
        if hasattr(node, "args") and node.args:
            for arg in node.args.args:
                self.defined_vars.add(arg.arg)

        self.generic_visit(node)
        self.defined_vars = old_defined_vars

    def visit_FunctionDef(self, node):
        self.defined_vars.add(node.name)
        old_defined_vars = self.defined_vars.copy()

        for arg in node.args.args:
            self.defined_vars.add(arg.arg)

        self.generic_visit(node)
        self.defined_vars = old_defined_vars

    def visit_ExceptHandler(self, node):
        if node.name:
            self.defined_vars.add(node.name)
        self.generic_visit(node)

    def _visit_comprehension(self, node):
        comp_vars = set()
        generators = getattr(node, "generators", [])
        for generator in generators:
            if isinstance(generator.target, ast.Name):
                comp_vars.add(generator.target.id)
            elif isinstance(generator.target, ast.Tuple):
                for elt in generator.target.elts:
                    if isinstance(elt, ast.Name):
                        comp_vars.add(elt.id)

        self.comp_vars_stack.append(comp_vars)
        self.generic_visit(node)
        self.comp_vars_stack.pop()

    def visit_ListComp(self, node):
        self._visit_comprehension(node)

    def visit_DictComp(self, node):
        self._visit_comprehension(node)

    def visit_SetComp(self, node):
        self._visit_comprehension(node)

    def visit_GeneratorExp(self, node):
        self._visit_comprehension(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            in_comp_scope = False
            for comp_vars in self.comp_vars_stack:
                if node.id in comp_vars:
                    in_comp_scope = True
                    break

            if node.id not in self.defined_vars and not in_comp_scope:
                self.external_vars.add(node.id)
        self.generic_visit(node)
