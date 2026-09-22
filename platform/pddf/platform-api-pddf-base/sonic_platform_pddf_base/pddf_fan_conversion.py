import ast
import math


try:
    string_types = (basestring,)
    integer_types = (int, long)
except NameError:
    string_types = (str,)
    integer_types = (int,)


class FanConversionError(ValueError):
    """Raised when a fan conversion expression or result is unsafe."""


class FanConversion(object):
    """Parse and evaluate a restricted fan conversion expression."""

    MAX_EXPRESSION_LENGTH = 256
    MAX_AST_NODES = 64
    MAX_AST_DEPTH = 16
    MAX_ABS_NUMBER = 10 ** 12

    _BINARY_OPERATORS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
    _UNARY_OPERATORS = (ast.UAdd, ast.USub)
    _CONSTANT_NODE = getattr(ast, 'Constant', None)

    def __init__(self, expression):
        if not isinstance(expression, string_types):
            raise FanConversionError('Fan conversion expression must be a string')
        if not expression or len(expression) > self.MAX_EXPRESSION_LENGTH:
            raise FanConversionError('Fan conversion expression has an invalid length')

        try:
            tree = ast.parse(expression, mode='eval')
        except (SyntaxError, TypeError) as error:
            raise FanConversionError('Invalid fan conversion expression: %s' % error)

        if not isinstance(tree, ast.Expression) or not isinstance(tree.body, ast.Lambda):
            raise FanConversionError('Fan conversion expression must be a lambda')

        lambda_node = tree.body
        self._argument_name = self._validate_arguments(lambda_node.args)
        self._node_count = 0
        self._validate_node(lambda_node.body, 0)
        self._body = lambda_node.body

    @staticmethod
    def _validate_arguments(arguments):
        if (len(arguments.args) != 1 or
                getattr(arguments, 'posonlyargs', None) or
                getattr(arguments, 'kwonlyargs', None) or
                getattr(arguments, 'defaults', None) or
                getattr(arguments, 'kw_defaults', None) or
                getattr(arguments, 'vararg', None) is not None or
                getattr(arguments, 'kwarg', None) is not None):
            raise FanConversionError(
                'Fan conversion lambda must have exactly one required argument'
            )

        argument = arguments.args[0]
        argument_name = getattr(argument, 'arg', getattr(argument, 'id', None))
        if not argument_name:
            raise FanConversionError('Fan conversion lambda argument is invalid')
        return argument_name

    def _validate_node(self, node, depth):
        self._node_count += 1
        if self._node_count > self.MAX_AST_NODES:
            raise FanConversionError('Fan conversion expression is too complex')
        if depth > self.MAX_AST_DEPTH:
            raise FanConversionError('Fan conversion expression is too deeply nested')

        if isinstance(node, ast.Name):
            if node.id != self._argument_name or not isinstance(node.ctx, ast.Load):
                raise FanConversionError('Fan conversion expression contains an invalid name')
            return

        if self._is_numeric_node(node):
            self._validate_number(self._get_numeric_value(node), 'constant')
            return

        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, self._BINARY_OPERATORS):
                raise FanConversionError('Fan conversion expression contains an invalid operator')
            self._validate_node(node.left, depth + 1)
            self._validate_node(node.right, depth + 1)
            return

        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, self._UNARY_OPERATORS):
                raise FanConversionError('Fan conversion expression contains an invalid operator')
            self._validate_node(node.operand, depth + 1)
            return

        raise FanConversionError(
            'Fan conversion expression contains unsupported syntax: %s' %
            type(node).__name__
        )

    @classmethod
    def _is_numeric_node(cls, node):
        if isinstance(node, ast.Num):
            return True
        return cls._CONSTANT_NODE is not None and isinstance(node, cls._CONSTANT_NODE)

    @classmethod
    def _get_numeric_value(cls, node):
        if cls._CONSTANT_NODE is not None and isinstance(node, cls._CONSTANT_NODE):
            return node.value
        return node.n

    @classmethod
    def _validate_number(cls, value, value_type):
        if isinstance(value, bool) or not isinstance(value, integer_types + (float,)):
            raise FanConversionError('Fan conversion %s must be numeric' % value_type)
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise FanConversionError('Fan conversion %s must be finite' % value_type)
        if abs(value) > cls.MAX_ABS_NUMBER:
            raise FanConversionError('Fan conversion %s is out of range' % value_type)
        return value

    def convert(self, value):
        self._validate_number(value, 'input')
        try:
            result = self._evaluate_node(self._body, value)
        except FanConversionError:
            raise
        except (ArithmeticError, OverflowError) as error:
            raise FanConversionError('Fan conversion failed: %s' % error)
        return self._validate_number(result, 'result')

    def _evaluate_node(self, node, argument_value):
        if isinstance(node, ast.Name):
            return argument_value

        if self._is_numeric_node(node):
            return self._get_numeric_value(node)

        if isinstance(node, ast.UnaryOp):
            operand = self._evaluate_node(node.operand, argument_value)
            if isinstance(node.op, ast.UAdd):
                result = operand
            else:
                result = -operand
            return self._validate_number(result, 'intermediate result')

        if not isinstance(node, ast.BinOp):
            raise FanConversionError(
                'Fan conversion expression contains unsupported syntax: %s' %
                type(node).__name__
            )

        left = self._evaluate_node(node.left, argument_value)
        right = self._evaluate_node(node.right, argument_value)

        if isinstance(node.op, ast.Add):
            result = left + right
        elif isinstance(node.op, ast.Sub):
            result = left - right
        elif isinstance(node.op, ast.Mult):
            result = left * right
        elif isinstance(node.op, ast.Div):
            if right == 0:
                raise FanConversionError('Fan conversion attempted division by zero')
            result = left / right
        else:
            raise FanConversionError('Fan conversion expression contains an invalid operator')

        return self._validate_number(result, 'intermediate result')
