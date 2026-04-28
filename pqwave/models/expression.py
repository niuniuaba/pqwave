#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ExprEvaluator - Infix expression evaluator for SPICE raw data

Full SPICE expression language support with ~90 functions and ~17 operators.
"""

import numpy as np

try:
    from scipy.special import erf, erfc, gamma, gammaln, jv, yv
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

# Functions that extract components from complex variables.
# When followed by (simple_var) with no operators inside, the entire
# call is captured as a VARIABLE token and routed through
# RawFile.get_variable_data(). When the argument contains operators,
# they act as regular functions via the registry.
_COMPLEX_FUNCTIONS = {'real', 'imag', 'mag', 'ph', 're', 'im', 'cph', 'phase'}

# All recognized function names
_FUNC_NAMES = {
    'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'arcsin', 'arccos', 'arctan',
    'sinh', 'cosh', 'tanh', 'asinh', 'acosh', 'atanh', 'arcsinh', 'arccosh', 'arctanh',
    'abs', 'sqrt', 'exp', 'ln', 'log', 'log10', 'log2', 'log1p',
    'ceil', 'floor', 'round', 'rint', 'trunc', 'sign', 'sgn', 'cbrt',
    're', 'real', 'im', 'imag', 'mag', 'fabs', 'ph', 'phase', 'cph',
    'db', 'exp10', 'ilogb', 'logb', 'invsqrt', 'cot',
    'd', 'dd', 'd²', 'mean', 'stddev',
    'buf', 'inv', 'uramp', 'ustep', 'isnan', 'int',
    'atan2', 'hypot', 'pow', 'pown', 'pwr', 'pwrs', 'max', 'min',
    'maxmag', 'minmag', 'if', 'limit',
    'j0', 'j1', 'jn', 'y0', 'y1', 'yn',
    'erf', 'erfc', 'gamma', 'lgamma',
    'table', 'tbl', 'taugrp', 'tg',
}

_CONSTANT_MAP = {
    'pi': np.pi, 'e': np.e, 'j': 1j,
    'k': 1.380649e-23, 'nan': np.nan, 'q': 1.602176487e-19,
}

# Multi-character operators, longest-first for greedy matching
_MULTI_CHAR_OPS = ['>=', '<=', '==', '!=', '<>', '**', '&&', '||', '^^']

# Characters that indicate an expression (not a simple variable name)
_EXPR_CHARS = set('+-*/^%&|=!<>, ')


def _is_numeric(s: str) -> bool:
    """Check if a string is a numeric literal (int, float, or scientific notation)."""
    try:
        float(s)
        return True
    except ValueError:
        return False


class ExprEvaluator:
    """Infix expression evaluator for SPICE raw data"""

    def __init__(self, raw_file, dataset_idx):
        self.raw_file = raw_file
        self.dataset_idx = dataset_idx
        self.n_points = raw_file.get_num_points(dataset_idx)

    # ---- Tokenizer ----

    def tokenize(self, expr):
        tokens = []
        i = 0
        n = len(expr)
        while i < n:
            c = expr[i]

            if c.isspace():
                i += 1
                continue

            # Numbers (including scientific notation)
            if c.isdigit() or (c == '.' and i + 1 < n and expr[i + 1].isdigit()):
                start = i
                while i < n and (expr[i].isdigit() or expr[i] == '.'):
                    i += 1
                if i < n and expr[i] in 'eE':
                    i += 1
                    if i < n and expr[i] in '+-':
                        i += 1
                    while i < n and expr[i].isdigit():
                        i += 1
                tokens.append(('NUMBER', float(expr[start:i])))
                continue

            # Multi-character operators (try longest match first)
            matched = False
            for op in _MULTI_CHAR_OPS:
                if expr[i:i + len(op)] == op:
                    tokens.append(('OPERATOR', op))
                    i += len(op)
                    matched = True
                    break
            if matched:
                continue

            # Single-character operators
            if c in '+-*/^%&|!':
                tokens.append(('OPERATOR', c))
                i += 1
                continue

            # Comparison operators (single-char forms)
            if c in '><=':
                tokens.append(('OPERATOR', c))
                i += 1
                continue

            # Comma
            if c == ',':
                tokens.append(('COMMA', None))
                i += 1
                continue

            # Parentheses
            if c == '(':
                tokens.append(('LPAREN', None))
                i += 1
                continue
            if c == ')':
                tokens.append(('RPAREN', None))
                i += 1
                continue

            # Names: functions, constants, variables (including d²)
            if c.isalpha() or c == '_':
                start = i
                while i < n and (expr[i].isalnum() or expr[i] == '_' or expr[i] == '.'):
                    i += 1
                if i < n and expr[i] == '²':
                    i += 1
                name = expr[start:i]
                lower = name.lower()

                if i < n and expr[i] == '(':
                    if lower in _COMPLEX_FUNCTIONS:
                        paren_count = 1
                        end = i + 1
                        while end < n and paren_count > 0:
                            if expr[end] == '(':
                                paren_count += 1
                            elif expr[end] == ')':
                                paren_count -= 1
                            end += 1
                        if paren_count != 0:
                            raise ValueError("Unmatched '(' in function call")
                        content = expr[i + 1:end - 1]
                        if any(ch in _EXPR_CHARS for ch in content) or _is_numeric(content):
                            tokens.append(('FUNCTION', lower))
                            tokens.append(('LPAREN', None))
                            i += 1
                        else:
                            var_name = expr[start:end]
                            tokens.append(('VARIABLE', var_name))
                            i = end
                    elif lower in _FUNC_NAMES:
                        tokens.append(('FUNCTION', lower))
                        tokens.append(('LPAREN', None))
                        i += 1
                    elif lower in _CONSTANT_MAP:
                        tokens.append(('CONSTANT', lower))
                    else:
                        paren_count = 1
                        end = i + 1
                        while end < n and paren_count > 0:
                            if expr[end] == '(':
                                paren_count += 1
                            elif expr[end] == ')':
                                paren_count -= 1
                            end += 1
                        if paren_count != 0:
                            raise ValueError("Unmatched '(' in variable name")
                        var_name = expr[start:end]
                        tokens.append(('VARIABLE', var_name))
                        i = end
                else:
                    if lower in _FUNC_NAMES:
                        tokens.append(('FUNCTION', lower))
                    elif lower in _CONSTANT_MAP:
                        tokens.append(('CONSTANT', lower))
                    else:
                        tokens.append(('VARIABLE', name))
                continue

            raise ValueError(f"Unexpected character: {c}")
        return tokens

    # ---- Public API ----

    def evaluate(self, expr):
        # Try expression parsing first so that arithmetic like v(out)+v(in)
        # always computes the sum, even when a variable with that exact name
        # exists (e.g. from a previous extraction).
        try:
            tokens = self.tokenize(expr)
            pos = 0
            result, _ = self._eval_boolean_or(tokens, pos)
            return result
        except Exception:
            pass

        # Fall back to exact variable name lookup. This handles variable
        # names that look like expressions but can't be parsed, such as
        # 'v(ac_p)-v(ac_n)' from an extracted file, or names containing
        # special characters like 'V(?1#inn)'.
        if self.raw_file is not None:
            var_data = self.raw_file.get_variable_data(expr, self.dataset_idx)
            if var_data is not None:
                if np.iscomplexobj(var_data) and np.all(var_data.imag == 0):
                    return var_data.real
                return var_data

        raise ValueError(f"Could not evaluate expression: {expr}")

    # ---- Recursive Descent Parser ----
    # Precedence (lowest to highest):
    #   expression  →  + -
    #   boolean_or  →  || |
    #   boolean_and →  && &
    #   boolean_xor →  ^^
    #   comparison  →  > >= < <= == != <>
    #   term        →  * / %
    #   factor      →  ^ **
    #   unary       →  + - !
    #   primary     →  atoms

    def _eval_expression(self, tokens, pos):
        left, pos = self._eval_term(tokens, pos)
        while pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] in '+-':
                op = tokens[pos][1]
                pos += 1
                right, pos = self._eval_term(tokens, pos)
                left = self._apply_op(left, right, op)
            else:
                break
        return left, pos

    def _eval_boolean_or(self, tokens, pos):
        left, pos = self._eval_boolean_and(tokens, pos)
        while pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] in ('||', '|'):
                pos += 1
                right, pos = self._eval_boolean_and(tokens, pos)
                left = self._apply_op(left, right, '||')
            else:
                break
        return left, pos

    def _eval_boolean_and(self, tokens, pos):
        left, pos = self._eval_boolean_xor(tokens, pos)
        while pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] in ('&&', '&'):
                pos += 1
                right, pos = self._eval_boolean_xor(tokens, pos)
                left = self._apply_op(left, right, '&&')
            else:
                break
        return left, pos

    def _eval_boolean_xor(self, tokens, pos):
        left, pos = self._eval_comparison(tokens, pos)
        while pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] == '^^':
                pos += 1
                right, pos = self._eval_comparison(tokens, pos)
                left = self._apply_op(left, right, '^^')
            else:
                break
        return left, pos

    def _eval_comparison(self, tokens, pos):
        left, pos = self._eval_expression(tokens, pos)
        while pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] in ('>', '>=', '<', '<=', '==', '!=', '<>'):
                op = tokens[pos][1]
                pos += 1
                right, pos = self._eval_expression(tokens, pos)
                left = self._apply_op(left, right, op)
            else:
                break
        return left, pos

    def _eval_term(self, tokens, pos):
        left, pos = self._eval_unary(tokens, pos)
        while pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] in '*/%':
                op = tokens[pos][1]
                pos += 1
                right, pos = self._eval_unary(tokens, pos)
                left = self._apply_op(left, right, op)
            else:
                break
        return left, pos

    def _eval_factor(self, tokens, pos):
        base, pos = self._eval_primary(tokens, pos)
        if pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] in ('^', '**'):
                pos += 1
                exp, pos = self._eval_unary(tokens, pos)
                return self._apply_op(base, exp, '^'), pos
        return base, pos

    def _eval_unary(self, tokens, pos):
        if pos < len(tokens) and tokens[pos][0] == 'OPERATOR':
            op = tokens[pos][1]
            if op == '-':
                pos += 1
                val, pos = self._eval_unary(tokens, pos)
                return -val, pos
            elif op == '+':
                pos += 1
                return self._eval_unary(tokens, pos)
            elif op == '!':
                pos += 1
                val, pos = self._eval_unary(tokens, pos)
                return (val <= 0.5).astype(float), pos
        return self._eval_factor(tokens, pos)

    def _eval_primary(self, tokens, pos):
        if pos >= len(tokens):
            raise ValueError("Unexpected end of expression")

        token_type, token_val = tokens[pos]
        pos += 1

        if token_type == 'NUMBER':
            return np.full(self.n_points, token_val), pos
        elif token_type == 'CONSTANT':
            return np.full(self.n_points, _CONSTANT_MAP[token_val]), pos
        elif token_type == 'VARIABLE':
            data = self.raw_file.get_variable_data(token_val, self.dataset_idx)
            if data is None:
                raise ValueError(f"Unknown variable: {token_val}")
            if len(data) != self.n_points:
                raise ValueError(
                    f"Variable '{token_val}' has {len(data)} points, expected {self.n_points}"
                )
            return data, pos
        elif token_type == 'FUNCTION':
            if pos < len(tokens) and tokens[pos][0] == 'LPAREN':
                pos += 1
            return self._eval_function_call(tokens, pos, token_val)
        elif token_type == 'LPAREN':
            val, pos = self._eval_expression(tokens, pos)
            if pos < len(tokens) and tokens[pos][0] == 'RPAREN':
                pos += 1
            else:
                raise ValueError("Missing closing ')'")
            return val, pos
        else:
            raise ValueError(f"Unexpected token: {token_type}")

    def _eval_function_call(self, tokens, pos, func_name):
        args = []
        arg, pos = self._eval_expression(tokens, pos)
        args.append(arg)

        while pos < len(tokens) and tokens[pos][0] == 'COMMA':
            pos += 1
            arg, pos = self._eval_expression(tokens, pos)
            args.append(arg)

        if pos < len(tokens) and tokens[pos][0] == 'RPAREN':
            pos += 1
        else:
            raise ValueError(f"Missing closing ')' after function '{func_name}'")

        return self._apply_function(func_name, args), pos

    # ---- Operators ----

    def _apply_op(self, left, right, op):
        if op == '+':
            return left + right
        elif op == '-':
            return left - right
        elif op == '*':
            return left * right
        elif op == '/':
            return left / right
        elif op == '%':
            return np.fmod(left, right)
        elif op in ('^', '**'):
            return np.power(left, right)
        elif op == '>':
            return (left > right).astype(float)
        elif op == '>=':
            return (left >= right).astype(float)
        elif op == '<':
            return (left < right).astype(float)
        elif op == '<=':
            return (left <= right).astype(float)
        elif op == '==':
            return (left == right).astype(float)
        elif op in ('!=', '<>'):
            return (left != right).astype(float)
        elif op in ('&&', '&'):
            return ((left > 0.5) & (right > 0.5)).astype(float)
        elif op in ('||', '|'):
            return ((left > 0.5) | (right > 0.5)).astype(float)
        elif op == '^^':
            return ((left > 0.5) ^ (right > 0.5)).astype(float)
        else:
            raise ValueError(f"Unknown operator: {op}")

    # ---- Functions ----

    def _apply_function(self, name, args):
        n = len(args)
        if n == 1:
            return self._apply_func_1arg(name, args[0])
        elif n == 2:
            return self._apply_func_2arg(name, args[0], args[1])
        elif n == 3:
            return self._apply_func_3arg(name, args[0], args[1], args[2])
        else:
            return self._apply_func_variadic(name, args)

    def _apply_func_1arg(self, name, x):
        # Direct numpy mappings
        _1ARG = {
            'sin': np.sin, 'cos': np.cos, 'tan': np.tan,
            'asin': np.arcsin, 'arcsin': np.arcsin,
            'acos': np.arccos, 'arccos': np.arccos,
            'atan': np.arctan, 'arctan': np.arctan,
            'sinh': np.sinh, 'cosh': np.cosh, 'tanh': np.tanh,
            'asinh': np.arcsinh, 'arcsinh': np.arcsinh,
            'acosh': np.arccosh, 'arccosh': np.arccosh,
            'atanh': np.arctanh, 'arctanh': np.arctanh,
            'abs': np.abs, 'fabs': np.abs, 'mag': np.abs,
            'sqrt': np.sqrt, 'exp': np.exp,
            'ln': np.log, 'log': np.log,
            'log10': np.log10, 'log2': np.log2, 'log1p': np.log1p,
            'ceil': np.ceil, 'floor': np.floor,
            'round': np.round, 'rint': np.rint,
            'trunc': np.trunc, 'int': np.trunc,
            'sign': np.sign, 'sgn': np.sign,
            'cbrt': np.cbrt,
            're': np.real, 'real': np.real,
            'im': np.imag, 'imag': np.imag,
        }
        if name in _1ARG:
            return _1ARG[name](x)

        # scipy special functions (1-arg)
        if name in ('erf', 'erfc', 'gamma', 'lgamma', 'j0', 'j1', 'y0', 'y1'):
            if not _HAS_SCIPY:
                raise ValueError(f"Function '{name}' requires scipy")
            return {
                'erf': erf, 'erfc': erfc, 'gamma': gamma,
                'lgamma': gammaln, 'j0': lambda x: jv(0, x),
                'j1': lambda x: jv(1, x), 'y0': lambda x: yv(0, x),
                'y1': lambda x: yv(1, x),
            }[name](x)

        # Custom implementations
        if name == 'db':
            return 20.0 * np.log10(np.abs(x) + 1e-300)
        elif name == 'exp10':
            return np.power(10.0, x)
        elif name == 'ilogb':
            return np.floor(np.log2(np.abs(x) + 1e-300))
        elif name == 'logb':
            return np.log2(np.abs(x) + 1e-300)
        elif name == 'invsqrt':
            return 1.0 / np.sqrt(np.abs(x) + 1e-300)
        elif name == 'cot':
            return 1.0 / np.tan(x)
        elif name in ('ph', 'phase'):
            return np.degrees(np.angle(x))
        elif name == 'cph':
            return np.angle(x)
        elif name == 'd':
            return np.gradient(x)
        elif name in ('dd', 'd²'):
            return np.gradient(np.gradient(x))
        elif name == 'mean':
            return np.full(self.n_points, np.mean(x))
        elif name == 'stddev':
            return np.full(self.n_points, np.std(x))
        elif name == 'buf':
            return np.where(x > 0.5, 1.0, 0.0)
        elif name == 'inv':
            return np.where(x > 0.5, 0.0, 1.0)
        elif name == 'uramp':
            return np.where(x > 0, x, 0.0)
        elif name == 'ustep':
            return np.where(x > 0, 1.0, 0.0)
        elif name == 'isnan':
            return np.isnan(x).astype(float)
        elif name in ('taugrp', 'tg'):
            return -np.gradient(np.unwrap(np.angle(x)))

        raise ValueError(f"Unknown function: {name}")

    def _apply_func_2arg(self, name, x, y):
        if name == 'atan2':
            return np.arctan2(x, y)
        elif name == 'hypot':
            return np.hypot(x, y)
        elif name == 'pow':
            return np.power(x, y)
        elif name == 'pown':
            return np.power(x, np.round(y))
        elif name == 'pwr':
            return np.power(np.abs(x), y)
        elif name == 'pwrs':
            return np.where(x >= 0, np.power(x, y), -np.power(x, y))
        elif name == 'max':
            return np.maximum(x, y)
        elif name == 'min':
            return np.minimum(x, y)
        elif name == 'maxmag':
            return np.where(np.abs(x) >= np.abs(y), x, y)
        elif name == 'minmag':
            return np.where(np.abs(x) <= np.abs(y), x, y)
        elif name == 'jn':
            if not _HAS_SCIPY:
                raise ValueError(f"Function '{name}' requires scipy")
            return jv(int(np.round(np.mean(y))), x)
        elif name == 'yn':
            if not _HAS_SCIPY:
                raise ValueError(f"Function '{name}' requires scipy")
            return yv(int(np.round(np.mean(y))), x)
        raise ValueError(f"Unknown function: {name}")

    def _apply_func_3arg(self, name, x, y, z):
        if name == 'if':
            return np.where(x > 0.5, y, z)
        elif name == 'limit':
            lo = np.minimum(y, z)
            hi = np.maximum(y, z)
            return np.clip(x, lo, hi)
        raise ValueError(f"Unknown function: {name}")

    def _apply_func_variadic(self, name, args):
        if name in ('table', 'tbl'):
            if len(args) < 3 or len(args) % 2 != 1:
                raise ValueError(
                    f"{name}() requires odd number of arguments: x, x1, y1, ..."
                )
            x = args[0]
            x_points = np.array([np.mean(a) for a in args[1::2]])
            y_points = np.array([np.mean(a) for a in args[2::2]])
            return np.interp(x, x_points, y_points)
        raise ValueError(f"Unknown function: {name}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        from .rawfile import RawFile
        rf = RawFile(sys.argv[1])
        evaluator = ExprEvaluator(rf, 0)
        print(f"Evaluator created for {sys.argv[1]}")
        print(f"Number of points: {evaluator.n_points}")
        if evaluator.n_points > 0:
            test_expr = "v(r1)"
            try:
                result = evaluator.evaluate(test_expr)
                print(f"Test expression '{test_expr}': shape = {result.shape}")
            except Exception as e:
                print(f"Error evaluating '{test_expr}': {e}")
    else:
        print("Usage: python expression.py <rawfile>")
