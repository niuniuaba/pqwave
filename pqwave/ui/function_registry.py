#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Function metadata registry for the expression evaluator.

Provides a structured catalog of all supported functions, operators, and
constants with signatures, descriptions, and categories. Used by both the
FunctionsCombo widget and the FunctionsHelpDialog.
"""

from dataclasses import dataclass


@dataclass
class FunctionInfo:
    """Metadata for a single function, operator, or constant."""
    name: str
    signature: str
    description: str
    category: str
    arg_count: int  # 0 for constants, 1, 2, 3, or -1 for variadic
    pass


# ---- Functions ----

_FUNCTIONS: list[FunctionInfo] = [
    # Math
    FunctionInfo("abs", "abs(x)", "Absolute value of x", "Math", 1),
    FunctionInfo("sqrt", "sqrt(x)", "Square root of x", "Math", 1),
    FunctionInfo("exp", "exp(x)", "Exponential, e^x", "Math", 1),
    FunctionInfo("ln", "ln(x)", "Natural logarithm of x", "Math", 1),
    FunctionInfo("log", "log(x)", "Natural logarithm (alias for ln)", "Math", 1),
    FunctionInfo("log10", "log10(x)", "Base-10 logarithm of x", "Math", 1),
    FunctionInfo("log2", "log2(x)", "Base-2 logarithm of x", "Math", 1),
    FunctionInfo("log1p", "log1p(x)", "Natural logarithm of (1+x)", "Math", 1),
    FunctionInfo("cbrt", "cbrt(x)", "Cube root of x", "Math", 1),
    FunctionInfo("exp10", "exp10(x)", "10^x", "Math", 1),
    FunctionInfo("ilogb", "ilogb(x)", "Floor of log2(|x|)", "Math", 1),
    FunctionInfo("logb", "logb(x)", "Log2 of absolute value", "Math", 1),
    FunctionInfo("invsqrt", "invsqrt(x)", "1 / sqrt(|x|)", "Math", 1),
    FunctionInfo("cot", "cot(x)", "Cotangent (1/tan(x))", "Math", 1),

    # Trig
    FunctionInfo("sin", "sin(x)", "Sine of x (radians)", "Trig", 1),
    FunctionInfo("cos", "cos(x)", "Cosine of x (radians)", "Trig", 1),
    FunctionInfo("tan", "tan(x)", "Tangent of x (radians)", "Trig", 1),
    FunctionInfo("asin", "asin(x)", "Arc sine of x (radians)", "Trig", 1),
    FunctionInfo("acos", "acos(x)", "Arc cosine of x (radians)", "Trig", 1),
    FunctionInfo("atan", "atan(x)", "Arc tangent of x (radians)", "Trig", 1),
    FunctionInfo("arcsin", "arcsin(x)", "Arc sine, alias for asin", "Trig", 1),
    FunctionInfo("arccos", "arccos(x)", "Arc cosine, alias for acos", "Trig", 1),
    FunctionInfo("arctan", "arctan(x)", "Arc tangent, alias for atan", "Trig", 1),

    # Hyperbolic
    FunctionInfo("sinh", "sinh(x)", "Hyperbolic sine of x", "Hyperbolic", 1),
    FunctionInfo("cosh", "cosh(x)", "Hyperbolic cosine of x", "Hyperbolic", 1),
    FunctionInfo("tanh", "tanh(x)", "Hyperbolic tangent of x", "Hyperbolic", 1),
    FunctionInfo("asinh", "asinh(x)", "Inverse hyperbolic sine", "Hyperbolic", 1),
    FunctionInfo("acosh", "acosh(x)", "Inverse hyperbolic cosine", "Hyperbolic", 1),
    FunctionInfo("atanh", "atanh(x)", "Inverse hyperbolic tangent", "Hyperbolic", 1),
    FunctionInfo("arcsinh", "arcsinh(x)", "Inverse hyperbolic sine, alias for asinh", "Hyperbolic", 1),
    FunctionInfo("arccosh", "arccosh(x)", "Inverse hyperbolic cosine, alias for acosh", "Hyperbolic", 1),
    FunctionInfo("arctanh", "arctanh(x)", "Inverse hyperbolic tangent, alias for atanh", "Hyperbolic", 1),

    # Rounding / Sign
    FunctionInfo("ceil", "ceil(x)", "Ceiling, round up to integer", "Rounding/Sign", 1),
    FunctionInfo("floor", "floor(x)", "Floor, round down to integer", "Rounding/Sign", 1),
    FunctionInfo("round", "round(x)", "Round to nearest integer", "Rounding/Sign", 1),
    FunctionInfo("rint", "rint(x)", "Round to nearest integer", "Rounding/Sign", 1),
    FunctionInfo("trunc", "trunc(x)", "Truncate toward zero", "Rounding/Sign", 1),
    FunctionInfo("int", "int(x)", "Truncate to integer", "Rounding/Sign", 1),
    FunctionInfo("sign", "sign(x)", "Sign of x: -1, 0, or 1", "Rounding/Sign", 1),
    FunctionInfo("sgn", "sgn(x)", "Sign of x, alias for sign", "Rounding/Sign", 1),

    # Complex
    FunctionInfo("re", "re(x)", "Real part of complex x", "Complex", 1),
    FunctionInfo("real", "real(x)", "Real part, alias for re", "Complex", 1),
    FunctionInfo("im", "im(x)", "Imaginary part of complex x", "Complex", 1),
    FunctionInfo("imag", "imag(x)", "Imaginary part, alias for im", "Complex", 1),
    FunctionInfo("mag", "mag(x)", "Magnitude (absolute value) of x", "Complex", 1),
    FunctionInfo("fabs", "fabs(x)", "Absolute value, alias for abs", "Complex", 1),
    FunctionInfo("ph", "ph(x)", "Phase in degrees", "Complex", 1),
    FunctionInfo("phase", "phase(x)", "Phase in degrees, alias for ph", "Complex", 1),
    FunctionInfo("cph", "cph(x)", "Phase in radians", "Complex", 1),

    # Differential
    FunctionInfo("d", "d(x)", "First derivative (np.gradient)", "Differential", 1),
    FunctionInfo("dd", "dd(x)", "Second derivative", "Differential", 1),
    FunctionInfo("d²", "d²(x)", "Second derivative, alias for dd", "Differential", 1),

    # Vector / Stats
    FunctionInfo("mean", "mean(x)", "Mean (average) of all points in x", "Vector/Stats", 1),
    FunctionInfo("stddev", "stddev(x)", "Standard deviation of all points in x", "Vector/Stats", 1),

    # dB / Group Delay
    FunctionInfo("db", "db(x)", "Decibel: 20*log10(|x|)", "dB/GroupDelay", 1),
    FunctionInfo("taugrp", "taugrp(x)", "Group delay: -d(phase(x))/dω", "dB/GroupDelay", 1),
    FunctionInfo("tg", "tg(x)", "Group delay, alias for taugrp", "dB/GroupDelay", 1),

    # Bessel (requires scipy)
    FunctionInfo("j0", "j0(x)", "Bessel J₀, first kind, order 0 (needs scipy)", "Bessel", 1),
    FunctionInfo("j1", "j1(x)", "Bessel J₁, first kind, order 1 (needs scipy)", "Bessel", 1),
    FunctionInfo("y0", "y0(x)", "Bessel Y₀, second kind, order 0 (needs scipy)", "Bessel", 1),
    FunctionInfo("y1", "y1(x)", "Bessel Y₁, second kind, order 1 (needs scipy)", "Bessel", 1),

    # Special (requires scipy)
    FunctionInfo("erf", "erf(x)", "Error function (needs scipy)", "Special", 1),
    FunctionInfo("erfc", "erfc(x)", "Complementary error function (needs scipy)", "Special", 1),
    FunctionInfo("gamma", "gamma(x)", "Gamma function (needs scipy)", "Special", 1),
    FunctionInfo("lgamma", "lgamma(x)", "Log-gamma function (needs scipy)", "Special", 1),

    # FFT
    FunctionInfo("fft", "fft(x)", "Fast Fourier Transform: frequency-domain analysis. Auto-creates a new panel.", "FFT", 1),

    # Conditional
    FunctionInfo("buf", "buf(x)", "Buffer: 1 if x > 0.5, else 0", "Conditional", 1),
    FunctionInfo("inv", "inv(x)", "Inverter: 0 if x > 0.5, else 1", "Conditional", 1),
    FunctionInfo("uramp", "uramp(x)", "Unit ramp: x if x > 0, else 0", "Conditional", 1),
    FunctionInfo("ustep", "ustep(x)", "Unit step: 1 if x > 0, else 0", "Conditional", 1),
    FunctionInfo("isnan", "isnan(x)", "1 if x is NaN, else 0", "Conditional", 1),

    # 2-arg
    FunctionInfo("atan2", "atan2(y, x)", "Four-quadrant arc tangent of y/x (radians)", "2-arg", 2),
    FunctionInfo("hypot", "hypot(x, y)", "Hypotenuse sqrt(x² + y²)", "2-arg", 2),
    FunctionInfo("pow", "pow(x, y)", "Power x^y", "2-arg", 2),
    FunctionInfo("pown", "pown(x, y)", "Power with integer exponent: x^round(y)", "2-arg", 2),
    FunctionInfo("pwr", "pwr(x, y)", "Power of absolute value: |x|^y", "2-arg", 2),
    FunctionInfo("pwrs", "pwrs(x, y)", "Signed power: sign(x)*|x|^y", "2-arg", 2),
    FunctionInfo("max", "max(x, y)", "Element-wise maximum of x and y", "2-arg", 2),
    FunctionInfo("min", "min(x, y)", "Element-wise minimum of x and y", "2-arg", 2),
    FunctionInfo("maxmag", "maxmag(x, y)", "Element with larger magnitude", "2-arg", 2),
    FunctionInfo("minmag", "minmag(x, y)", "Element with smaller magnitude", "2-arg", 2),
    FunctionInfo("jn", "jn(x, n)", "Bessel Jₙ of order n evaluated at x (needs scipy)", "2-arg", 2),
    FunctionInfo("yn", "yn(x, n)", "Bessel Yₙ of order n evaluated at x (needs scipy)", "2-arg", 2),

    # 3-arg
    FunctionInfo("if", "if(x, y, z)", "Conditional: y if x > 0.5, else z", "3-arg", 3),
    FunctionInfo("limit", "limit(x, lo, hi)", "Clip x between lo and hi", "3-arg", 3),

    # Variadic
    FunctionInfo("table", "table(x, x1, y1, ...)", "Table lookup by linear interpolation", "Variadic", -1),
    FunctionInfo("tbl", "tbl(x, x1, y1, ...)", "Table lookup, alias for table", "Variadic", -1),
]

# ---- Constants ----

_CONSTANTS: list[FunctionInfo] = [
    FunctionInfo("pi", "pi", "π = 3.141592653589793", "Constants", 0),
    FunctionInfo("e", "e", "Euler's number = 2.718281828459045", "Constants", 0),
    FunctionInfo("j", "j", "Imaginary unit √(-1)", "Constants", 0),
    FunctionInfo("k", "k", "Boltzmann constant = 1.380649e-23 J/K", "Constants", 0),
    FunctionInfo("nan", "nan", "Not a Number", "Constants", 0),
    FunctionInfo("q", "q", "Elementary charge = 1.602176487e-19 C", "Constants", 0),
]



def get_all_functions() -> list[FunctionInfo]:
    """Return all functions (including constants)."""
    return list(_FUNCTIONS)


def get_all_constants() -> list[FunctionInfo]:
    """Return all constants."""
    return list(_CONSTANTS)


def get_all() -> list[FunctionInfo]:
    """Return all items: functions + constants."""
    return list(_FUNCTIONS) + list(_CONSTANTS)


def lookup(name: str) -> FunctionInfo | None:
    """Look up a function, constant, or operator by name."""
    name_lower = name.lower()
    for info in _FUNCTIONS:
        if info.name == name_lower:
            return info
    for info in _CONSTANTS:
        if info.name == name_lower:
            return info
    return None
