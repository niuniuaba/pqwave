#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ExprEvaluator - Infix expression evaluator for SPICE raw data
"""

import numpy as np


class ExprEvaluator:
    """Infix expression evaluator for SPICE raw data"""

    def __init__(self, raw_file, dataset_idx):
        self.raw_file = raw_file
        self.dataset_idx = dataset_idx
        self.n_points = raw_file.get_num_points(dataset_idx)

    def tokenize(self, expr):
        """Tokenize expression"""
        tokens = []
        i = 0
        while i < len(expr):
            c = expr[i]

            if c.isspace():
                i += 1
                continue

            if c.isdigit() or (c == '.' and i + 1 < len(expr) and expr[i+1].isdigit()):
                start = i
                while i < len(expr) and (expr[i].isdigit() or expr[i] == '.' or expr[i] in 'eE+-'):
                    i += 1
                num_str = expr[start:i]
                val = float(num_str)
                tokens.append(('NUMBER', val))
            elif c.isalpha() or c == '_':
                start = i
                while i < len(expr) and (expr[i].isalnum() or expr[i] == '_' or expr[i] == '.'):
                    i += 1
                name = expr[start:i]
                lower = name.lower()

                if i < len(expr) and expr[i] == '(':
                    # Check if it's a complex-related function
                    if lower in ['real', 'imag', 'mag', 'ph']:
                        # Find the matching closing parenthesis
                        paren_count = 1
                        end = i + 1
                        while end < len(expr) and paren_count > 0:
                            if expr[end] == '(':
                                paren_count += 1
                            elif expr[end] == ')':
                                paren_count -= 1
                            end += 1
                        if paren_count == 0:
                            # Extract the entire function call as a variable
                            var_name = expr[start:end]
                            tokens.append(('VARIABLE', var_name))
                            i = end
                        else:
                            raise ValueError("Unmatched '(' in function call")
                    elif self.is_function_name(lower):
                        tokens.append(('FUNCTION', lower))
                        tokens.append(('LPAREN', None))
                        i += 1
                    elif self.is_constant_name(lower):
                        tokens.append(('CONSTANT', lower))
                    else:
                        var_start = start
                        while i < len(expr) and expr[i] != ')':
                            i += 1
                        if i >= len(expr):
                            raise ValueError("Unmatched '(' in variable name")
                        i += 1
                        var_name = expr[var_start:i]
                        tokens.append(('VARIABLE', var_name))
                else:
                    if self.is_function_name(lower):
                        tokens.append(('FUNCTION', lower))
                    elif self.is_constant_name(lower):
                        tokens.append(('CONSTANT', lower))
                    else:
                        tokens.append(('VARIABLE', name))
            elif c == '(':
                tokens.append(('LPAREN', None))
                i += 1
            elif c == ')':
                tokens.append(('RPAREN', None))
                i += 1
            elif c in '+-*/^':
                tokens.append(('OPERATOR', c))
                i += 1
            else:
                raise ValueError(f"Unexpected character: {c}")
        return tokens

    def is_function_name(self, name):
        """Check if name is a function"""
        functions = ['sin', 'cos', 'tan', 'abs', 'sqrt', 'log', 'log10', 'exp', 'min', 'max', 'asin', 'acos', 'atan', 'mag', 'real', 'imag', 'ph']
        return name in functions

    def is_constant_name(self, name):
        """Check if name is a constant"""
        constants = ['pi', 'e']
        return name in constants

    def evaluate(self, expr):
        """Evaluate expression"""
        tokens = self.tokenize(expr)
        pos = 0
        result, _ = self.eval_expression(tokens, pos)
        return result

    def eval_expression(self, tokens, pos):
        """Evaluate expression"""
        left, pos = self.eval_term(tokens, pos)

        while pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR':
                op = tokens[pos][1]
                if op in '+-':
                    pos += 1
                    right, pos = self.eval_term(tokens, pos)
                    left = self.apply_op_vector(left, right, op)
                else:
                    break
            else:
                break
        return left, pos

    def eval_term(self, tokens, pos):
        """Evaluate term"""
        left, pos = self.eval_power(tokens, pos)

        while pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR':
                op = tokens[pos][1]
                if op in '*/':
                    pos += 1
                    right, pos = self.eval_power(tokens, pos)
                    left = self.apply_op_vector(left, right, op)
                else:
                    break
            else:
                break
        return left, pos

    def eval_power(self, tokens, pos):
        """Evaluate power"""
        base, pos = self.eval_unary(tokens, pos)

        if pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] == '^':
                pos += 1
                exp, pos = self.eval_unary(tokens, pos)
                return self.apply_op_vector(base, exp, '^'), pos
        return base, pos

    def eval_unary(self, tokens, pos):
        """Evaluate unary"""
        if pos < len(tokens):
            if tokens[pos][0] == 'OPERATOR' and tokens[pos][1] == '-':
                pos += 1
                val, pos = self.eval_unary(tokens, pos)
                return -val, pos
            elif tokens[pos][0] == 'OPERATOR' and tokens[pos][1] == '+':
                pos += 1
                return self.eval_unary(tokens, pos)
        return self.eval_primary(tokens, pos)

    def eval_primary(self, tokens, pos):
        """Evaluate primary"""
        if pos >= len(tokens):
            raise ValueError("Unexpected end of expression")

        token_type, token_val = tokens[pos]
        pos += 1

        if token_type == 'NUMBER':
            return np.full(self.n_points, token_val), pos
        elif token_type == 'CONSTANT':
            if token_val == 'pi':
                return np.full(self.n_points, np.pi), pos
            elif token_val == 'e':
                return np.full(self.n_points, np.e), pos
            else:
                raise ValueError(f"Unknown constant: {token_val}")
        elif token_type == 'VARIABLE':
            # Get variable data directly from RawFile
            data = self.raw_file.get_variable_data(token_val, self.dataset_idx)
            if data is not None:
                if len(data) == self.n_points:
                    return data, pos
                else:
                    raise ValueError(f"Variable '{token_val}' has {len(data)} points, expected {self.n_points}")
            else:
                raise ValueError(f"Unknown variable: {token_val}")
        elif token_type == 'FUNCTION':
            arg, pos = self.eval_expression(tokens, pos)
            if pos < len(tokens) and tokens[pos][0] == 'RPAREN':
                pos += 1
            return self.apply_function(token_val, arg), pos
        elif token_type == 'LPAREN':
            val, pos = self.eval_expression(tokens, pos)
            if pos < len(tokens) and tokens[pos][0] == 'RPAREN':
                pos += 1
            else:
                raise ValueError("Missing closing \"")
            return val, pos
        else:
            raise ValueError(f"Unexpected token: {token_type}")

    def apply_op_vector(self, left, right, op):
        """Apply operator to vectors"""
        if len(left) != len(right):
            raise ValueError(f"Vector length mismatch: {len(left)} vs {len(right)}")

        if op == '+':
            return left + right
        elif op == '-':
            return left - right
        elif op == '*':
            return left * right
        elif op == '/':
            if np.any(right == 0):
                raise ValueError("Division by zero")
            return left / right
        elif op == '^':
            return np.power(left, right)
        else:
            raise ValueError(f"Unknown operator: {op}")

    def apply_function(self, name, arg):
        """Apply function to vector"""
        if name == 'sin':
            return np.sin(arg)
        elif name == 'cos':
            return np.cos(arg)
        elif name == 'tan':
            return np.tan(arg)
        elif name == 'asin':
            return np.arcsin(arg)
        elif name == 'acos':
            return np.arccos(arg)
        elif name == 'atan':
            return np.arctan(arg)
        elif name == 'abs':
            return np.abs(arg)
        elif name == 'sqrt':
            if np.any(arg < 0):
                raise ValueError("sqrt of negative number")
            return np.sqrt(arg)
        elif name == 'log':
            if np.any(arg <= 0):
                raise ValueError("log of non-positive number")
            return np.log(arg)
        elif name == 'log10':
            if np.any(arg <= 0):
                raise ValueError("log10 of non-positive number")
            return np.log10(arg)
        elif name == 'exp':
            return np.exp(arg)
        elif name == 'mag':
            # For complex variables, mag() should be handled by get_variable_data
            # but if it's called as a function, use absolute value
            return np.abs(arg)
        elif name == 'real':
            # For complex variables, real() should be handled by get_variable_data
            # but if it's called as a function, return the argument as is
            return arg
        elif name == 'imag':
            # For complex variables, imag() should be handled by get_variable_data
            # but if it's called as a function, return zeros (this is a fallback)
            return np.zeros_like(arg)
        elif name == 'ph':
            # For complex variables, ph() should be handled by get_variable_data
            # but if it's called as a function, return angle in degrees
            return np.degrees(np.arctan2(np.zeros_like(arg), arg))
        else:
            raise ValueError(f"Unknown function: {name}")


if __name__ == "__main__":
    # Simple test
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