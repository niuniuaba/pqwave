#!/usr/bin/env python3
"""Comprehensive tests for ExprEvaluator with extended SPICE expression support."""

import os
import pytest
import numpy as np

from pqwave.models.expression import ExprEvaluator
from pqwave.models.rawfile import RawFile

_TEST_RAW = os.path.join(os.path.dirname(__file__), '..', '..', 'tests', 'bridge', 'simulation', 'bridge.raw')


@pytest.fixture(scope="module")
def evaluator():
    rf = RawFile(_TEST_RAW)
    return ExprEvaluator(rf, 0)


@pytest.fixture(scope="module")
def var_names():
    rf = RawFile(_TEST_RAW)
    return rf.get_variable_names()


# --- Constants ---

def test_constant_pi(evaluator):
    result = evaluator.evaluate('pi')
    assert np.isclose(result[0], np.pi)

def test_constant_e(evaluator):
    result = evaluator.evaluate('e')
    assert np.isclose(result[0], np.e)

def test_constant_j(evaluator):
    result = evaluator.evaluate('j')
    assert np.isclose(result[0], 1j)

def test_constant_k(evaluator):
    result = evaluator.evaluate('k')
    assert np.isclose(result[0], 1.380649e-23)

def test_constant_nan(evaluator):
    result = evaluator.evaluate('nan')
    assert np.isnan(result[0])

def test_constant_q(evaluator):
    result = evaluator.evaluate('q')
    assert np.isclose(result[0], 1.602176487e-19)


# --- Arithmetic operators ---

def test_addition(evaluator):
    result = evaluator.evaluate('1 + 2')
    assert np.allclose(result, 3.0)

def test_subtraction(evaluator):
    result = evaluator.evaluate('5 - 3')
    assert np.allclose(result, 2.0)

def test_multiplication(evaluator):
    result = evaluator.evaluate('4 * 3')
    assert np.allclose(result, 12.0)

def test_division(evaluator):
    result = evaluator.evaluate('10 / 4')
    assert np.allclose(result, 2.5)

def test_exponentiation_caret(evaluator):
    result = evaluator.evaluate('2 ^ 3')
    assert np.allclose(result, 8.0)

def test_exponentiation_double_star(evaluator):
    result = evaluator.evaluate('2 ** 3')
    assert np.allclose(result, 8.0)

def test_modulo(evaluator):
    result = evaluator.evaluate('10 % 3')
    assert np.allclose(result, 1.0)

def test_unary_minus(evaluator):
    result = evaluator.evaluate('-3')
    assert np.allclose(result, -3.0)

def test_unary_plus(evaluator):
    result = evaluator.evaluate('+5')
    assert np.allclose(result, 5.0)

def test_compound_arithmetic(evaluator):
    result = evaluator.evaluate('2 + 3 * 4')
    assert np.allclose(result, 14.0)

def test_parentheses(evaluator):
    result = evaluator.evaluate('(2 + 3) * 4')
    assert np.allclose(result, 20.0)


# --- Comparison operators ---

def test_greater_than(evaluator):
    result = evaluator.evaluate('5 > 3')
    assert np.allclose(result, 1.0)

def test_greater_than_false(evaluator):
    result = evaluator.evaluate('3 > 5')
    assert np.allclose(result, 0.0)

def test_greater_equal(evaluator):
    result = evaluator.evaluate('5 >= 5')
    assert np.allclose(result, 1.0)

def test_less_than(evaluator):
    result = evaluator.evaluate('3 < 5')
    assert np.allclose(result, 1.0)

def test_less_equal(evaluator):
    result = evaluator.evaluate('3 <= 3')
    assert np.allclose(result, 1.0)

def test_equal(evaluator):
    result = evaluator.evaluate('5 == 5')
    assert np.allclose(result, 1.0)

def test_equal_false(evaluator):
    result = evaluator.evaluate('5 == 3')
    assert np.allclose(result, 0.0)

def test_not_equal_bang(evaluator):
    result = evaluator.evaluate('5 != 3')
    assert np.allclose(result, 1.0)

def test_not_equal_diamond(evaluator):
    result = evaluator.evaluate('5 <> 3')
    assert np.allclose(result, 1.0)


# --- Boolean operators ---

def test_boolean_not(evaluator):
    result = evaluator.evaluate('!0')
    assert np.allclose(result, 1.0)

def test_boolean_not_true(evaluator):
    result = evaluator.evaluate('!1')
    assert np.allclose(result, 0.0)

def test_boolean_and_double(evaluator):
    result = evaluator.evaluate('1 && 1')
    assert np.allclose(result, 1.0)

def test_boolean_and_single(evaluator):
    result = evaluator.evaluate('1 & 0')
    assert np.allclose(result, 0.0)

def test_boolean_or_double(evaluator):
    result = evaluator.evaluate('0 || 1')
    assert np.allclose(result, 1.0)

def test_boolean_or_single(evaluator):
    result = evaluator.evaluate('0 | 0')
    assert np.allclose(result, 0.0)

def test_boolean_xor(evaluator):
    result = evaluator.evaluate('1 ^^ 0')
    assert np.allclose(result, 1.0)

def test_boolean_xor_both_true(evaluator):
    result = evaluator.evaluate('1 ^^ 1')
    assert np.allclose(result, 0.0)


# --- 1-arg numpy-mapped functions ---

def test_sin(evaluator):
    result = evaluator.evaluate('sin(0)')
    assert np.allclose(result, 0.0)

def test_cos(evaluator):
    result = evaluator.evaluate('cos(0)')
    assert np.allclose(result, 1.0)

def test_tan(evaluator):
    result = evaluator.evaluate('tan(0)')
    assert np.allclose(result, 0.0)

def test_asin(evaluator):
    result = evaluator.evaluate('asin(0)')
    assert np.allclose(result, 0.0)

def test_acos(evaluator):
    result = evaluator.evaluate('acos(1)')
    assert np.allclose(result, 0.0, atol=1e-7)

def test_atan(evaluator):
    result = evaluator.evaluate('atan(0)')
    assert np.allclose(result, 0.0)

def test_arcsin(evaluator):
    result = evaluator.evaluate('arcsin(0)')
    assert np.allclose(result, 0.0)

def test_arccos(evaluator):
    result = evaluator.evaluate('arccos(1)')
    assert np.allclose(result, 0.0, atol=1e-7)

def test_arctan(evaluator):
    result = evaluator.evaluate('arctan(0)')
    assert np.allclose(result, 0.0)

def test_sinh(evaluator):
    result = evaluator.evaluate('sinh(0)')
    assert np.allclose(result, 0.0)

def test_cosh(evaluator):
    result = evaluator.evaluate('cosh(0)')
    assert np.allclose(result, 1.0)

def test_tanh(evaluator):
    result = evaluator.evaluate('tanh(0)')
    assert np.allclose(result, 0.0)

def test_asinh(evaluator):
    result = evaluator.evaluate('asinh(0)')
    assert np.allclose(result, 0.0)

def test_acosh(evaluator):
    result = evaluator.evaluate('acosh(1)')
    assert np.allclose(result, 0.0, atol=1e-7)

def test_atanh(evaluator):
    result = evaluator.evaluate('atanh(0)')
    assert np.allclose(result, 0.0)

def test_arcsinh(evaluator):
    result = evaluator.evaluate('arcsinh(0)')
    assert np.allclose(result, 0.0)

def test_arccosh(evaluator):
    result = evaluator.evaluate('arccosh(1)')
    assert np.allclose(result, 0.0, atol=1e-7)

def test_arctanh(evaluator):
    result = evaluator.evaluate('arctanh(0)')
    assert np.allclose(result, 0.0)

def test_abs(evaluator):
    result = evaluator.evaluate('abs(-5)')
    assert np.allclose(result, 5.0)

def test_fabs(evaluator):
    result = evaluator.evaluate('fabs(-5)')
    assert np.allclose(result, 5.0)

def test_sqrt(evaluator):
    result = evaluator.evaluate('sqrt(4)')
    assert np.allclose(result, 2.0)

def test_exp(evaluator):
    result = evaluator.evaluate('exp(0)')
    assert np.allclose(result, 1.0)

def test_ln(evaluator):
    result = evaluator.evaluate('ln(1)')
    assert np.allclose(result, 0.0)

def test_log(evaluator):
    result = evaluator.evaluate('log(1)')
    assert np.allclose(result, 0.0)

def test_log10(evaluator):
    result = evaluator.evaluate('log10(10)')
    assert np.allclose(result, 1.0)

def test_log2(evaluator):
    result = evaluator.evaluate('log2(2)')
    assert np.allclose(result, 1.0)

def test_log1p(evaluator):
    result = evaluator.evaluate('log1p(0)')
    assert np.allclose(result, 0.0)

def test_ceil(evaluator):
    result = evaluator.evaluate('ceil(2.3)')
    assert np.allclose(result, 3.0)

def test_floor(evaluator):
    result = evaluator.evaluate('floor(2.7)')
    assert np.allclose(result, 2.0)

def test_round(evaluator):
    result = evaluator.evaluate('round(2.5)')
    assert np.allclose(result, 2.0)  # numpy rounds to even

def test_rint(evaluator):
    result = evaluator.evaluate('rint(2.3)')
    assert np.allclose(result, 2.0)

def test_trunc(evaluator):
    result = evaluator.evaluate('trunc(2.7)')
    assert np.allclose(result, 2.0)

def test_int_func(evaluator):
    result = evaluator.evaluate('int(2.7)')
    assert np.allclose(result, 2.0)

def test_sign(evaluator):
    result = evaluator.evaluate('sign(-3)')
    assert np.allclose(result, -1.0)

def test_sgn(evaluator):
    result = evaluator.evaluate('sgn(-3)')
    assert np.allclose(result, -1.0)

def test_cbrt(evaluator):
    result = evaluator.evaluate('cbrt(8)')
    assert np.allclose(result, 2.0)


# --- 1-arg custom functions ---

def test_db(evaluator):
    result = evaluator.evaluate('db(10)')
    assert np.allclose(result, 20.0)

def test_exp10(evaluator):
    result = evaluator.evaluate('exp10(2)')
    assert np.allclose(result, 100.0)

def test_cot(evaluator):
    result = evaluator.evaluate('cot(pi/4)')
    assert np.allclose(result, 1.0, atol=1e-7)

def test_invsqrt(evaluator):
    result = evaluator.evaluate('invsqrt(4)')
    assert np.allclose(result, 0.5)

def test_buf(evaluator):
    result = evaluator.evaluate('buf(1)')
    assert np.allclose(result, 1.0)

def test_buf_false(evaluator):
    result = evaluator.evaluate('buf(0)')
    assert np.allclose(result, 0.0)

def test_inv(evaluator):
    result = evaluator.evaluate('inv(1)')
    assert np.allclose(result, 0.0)

def test_inv_false(evaluator):
    result = evaluator.evaluate('inv(0)')
    assert np.allclose(result, 1.0)

def test_uramp(evaluator):
    result = evaluator.evaluate('uramp(3)')
    assert np.allclose(result, 3.0)

def test_uramp_negative(evaluator):
    result = evaluator.evaluate('uramp(-3)')
    assert np.allclose(result, 0.0)

def test_ustep(evaluator):
    result = evaluator.evaluate('ustep(3)')
    assert np.allclose(result, 1.0)

def test_ustep_negative(evaluator):
    result = evaluator.evaluate('ustep(-3)')
    assert np.allclose(result, 0.0)

def test_isnan_true(evaluator):
    result = evaluator.evaluate('isnan(nan)')
    assert np.allclose(result, 1.0)

def test_isnan_false(evaluator):
    result = evaluator.evaluate('isnan(5)')
    assert np.allclose(result, 0.0)

def test_ilogb(evaluator):
    result = evaluator.evaluate('ilogb(8)')
    assert np.allclose(result, 3.0)

def test_logb(evaluator):
    result = evaluator.evaluate('logb(8)')
    assert np.allclose(result, 3.0)

def test_ph_real(evaluator):
    result = evaluator.evaluate('ph(5)')
    assert np.allclose(result, 0.0)  # phase of positive real is 0

def test_cph_real(evaluator):
    result = evaluator.evaluate('cph(5)')
    assert np.allclose(result, 0.0)

def test_re(evaluator):
    result = evaluator.evaluate('re(3 + 4*j)')
    assert np.allclose(result, 3.0)

def test_im(evaluator):
    result = evaluator.evaluate('im(3 + 4*j)')
    assert np.allclose(result, 4.0)

def test_mag(evaluator):
    result = evaluator.evaluate('mag(3 + 4*j)')
    assert np.allclose(result, 5.0)

def test_mean(evaluator):
    result = evaluator.evaluate('mean(5)')
    assert np.allclose(result, 5.0)

def test_stddev(evaluator):
    result = evaluator.evaluate('stddev(5)')
    assert np.allclose(result, 0.0)

def test_d_derivative(evaluator):
    result = evaluator.evaluate('d(time)')
    assert result.ndim == 1
    assert len(result) > 0
    assert np.all(np.isfinite(result))

def test_dd_second_derivative(evaluator):
    result = evaluator.evaluate('dd(time)')
    assert np.allclose(result, 0.0, atol=1e-5)


# --- 2-arg functions ---

def test_atan2(evaluator):
    result = evaluator.evaluate('atan2(1, 1)')
    assert np.allclose(result, np.pi / 4)

def test_hypot(evaluator):
    result = evaluator.evaluate('hypot(3, 4)')
    assert np.allclose(result, 5.0)

def test_pow(evaluator):
    result = evaluator.evaluate('pow(2, 3)')
    assert np.allclose(result, 8.0)

def test_pown(evaluator):
    result = evaluator.evaluate('pown(2, 3.2)')
    assert np.allclose(result, 8.0)

def test_pwr(evaluator):
    result = evaluator.evaluate('pwr(-2, 3)')
    assert np.allclose(result, 8.0)

def test_pwrs_positive(evaluator):
    result = evaluator.evaluate('pwrs(2, 3)')
    assert np.allclose(result, 8.0)

def test_pwrs_negative(evaluator):
    result = evaluator.evaluate('pwrs(-2, 3)')
    assert np.allclose(result, 8.0)

def test_max(evaluator):
    result = evaluator.evaluate('max(3, 5)')
    assert np.allclose(result, 5.0)

def test_min(evaluator):
    result = evaluator.evaluate('min(3, 5)')
    assert np.allclose(result, 3.0)

def test_maxmag(evaluator):
    result = evaluator.evaluate('maxmag(-7, 5)')
    assert np.allclose(result, -7.0)

def test_minmag(evaluator):
    result = evaluator.evaluate('minmag(-7, 5)')
    assert np.allclose(result, 5.0)


# --- 3-arg functions ---

def test_if_true(evaluator):
    result = evaluator.evaluate('if(1, 10, 20)')
    assert np.allclose(result, 10.0)

def test_if_false(evaluator):
    result = evaluator.evaluate('if(0, 10, 20)')
    assert np.allclose(result, 20.0)

def test_limit_middle(evaluator):
    result = evaluator.evaluate('limit(5, 0, 10)')
    assert np.allclose(result, 5.0)

def test_limit_low(evaluator):
    result = evaluator.evaluate('limit(-5, 0, 10)')
    assert np.allclose(result, 0.0)

def test_limit_high(evaluator):
    result = evaluator.evaluate('limit(15, 0, 10)')
    assert np.allclose(result, 10.0)


# --- Variadic functions ---

def test_table_two_segments(evaluator):
    result = evaluator.evaluate('table(0.5, 0, 0, 1, 10)')
    assert np.allclose(result, 5.0)

def test_table_left_extrap(evaluator):
    result = evaluator.evaluate('table(-0.5, 0, 0, 1, 10)')
    assert np.allclose(result, 0.0)

def test_table_right_extrap(evaluator):
    result = evaluator.evaluate('table(1.5, 0, 0, 1, 10)')
    assert np.allclose(result, 10.0)

def test_tbl_alias(evaluator):
    result = evaluator.evaluate('tbl(0.5, 0, 0, 1, 10)')
    assert np.allclose(result, 5.0)


# --- Scipy functions ---

def test_erf(evaluator):
    result = evaluator.evaluate('erf(0)')
    assert np.allclose(result, 0.0)

def test_erfc(evaluator):
    result = evaluator.evaluate('erfc(0)')
    assert np.allclose(result, 1.0)

def test_gamma(evaluator):
    result = evaluator.evaluate('gamma(2)')
    assert np.allclose(result, 1.0)  # gamma(2) = 1! = 1

def test_lgamma(evaluator):
    result = evaluator.evaluate('lgamma(2)')
    assert np.allclose(result, 0.0)  # ln(1) = 0

def test_j0(evaluator):
    result = evaluator.evaluate('j0(0)')
    assert np.allclose(result, 1.0)

def test_j1(evaluator):
    result = evaluator.evaluate('j1(0)')
    assert np.allclose(result, 0.0)

def test_y0(evaluator):
    result = evaluator.evaluate('y0(1)')
    assert np.isfinite(result[0])

def test_y1(evaluator):
    result = evaluator.evaluate('y1(1)')
    assert np.isfinite(result[0])

def test_jn(evaluator):
    result = evaluator.evaluate('jn(0, 0)')
    assert np.allclose(result, 1.0)  # J0(0) = 1

def test_yn(evaluator):
    result = evaluator.evaluate('yn(1, 0)')
    assert np.isfinite(result[0])


# --- Group delay ---

def test_tg(evaluator):
    result = evaluator.evaluate('tg(1)')
    assert result.shape == evaluator.evaluate('1').shape

def test_taugrp(evaluator):
    result = evaluator.evaluate('taugrp(1)')
    assert result.shape == evaluator.evaluate('1').shape


# --- Variable expressions using real data ---

def test_simple_var(evaluator, var_names):
    result = evaluator.evaluate('time')
    assert result.ndim == 1
    assert len(result) > 0

def test_var_arithmetic(evaluator):
    result = evaluator.evaluate('time + 1')
    assert result.ndim == 1

def test_var_function(evaluator):
    result = evaluator.evaluate('sin(time)')
    assert result.ndim == 1

def test_two_var_expression(evaluator, var_names):
    result = evaluator.evaluate('v(ac_p) + v(ac_n)')
    assert result.ndim == 1
    assert len(result) > 0

def test_complex_expr_with_operators(evaluator):
    result = evaluator.evaluate('mag(v(ac_p) + v(ac_n))')
    assert result.ndim == 1

def test_compound_with_boolean(evaluator):
    result = evaluator.evaluate('v(ac_p) > 0.5')
    assert result.ndim == 1

def test_complex_expression(evaluator):
    result = evaluator.evaluate('max(v(ac_p), v(ac_n))')
    assert result.ndim == 1


# --- Operator precedence ---

def test_precedence_compare_before_bool(evaluator):
    result = evaluator.evaluate('5 > 3 && 2 < 4')
    assert np.allclose(result, 1.0)

def test_precedence_arithmetic_before_compare(evaluator):
    result = evaluator.evaluate('2 + 2 == 4')
    assert np.allclose(result, 1.0)

def test_precedence_mult_before_add(evaluator):
    result = evaluator.evaluate('2 + 3 * 4')
    assert np.allclose(result, 14.0)

def test_precedence_unary_before_power(evaluator):
    result = evaluator.evaluate('-2 ^ 2')
    assert np.allclose(result, -4.0)

def test_precedence_power_before_mult(evaluator):
    result = evaluator.evaluate('2 * 3 ^ 2')
    assert np.allclose(result, 18.0)


# --- Edge cases ---

def test_whitespace_handling(evaluator):
    result = evaluator.evaluate('  1   +   2  ')
    assert np.allclose(result, 3.0)

def test_nested_parentheses(evaluator):
    result = evaluator.evaluate('((1 + 2) * (3 + 4))')
    assert np.allclose(result, 21.0)

def test_nested_functions(evaluator):
    result = evaluator.evaluate('abs(sin(1))')
    assert np.allclose(result, np.abs(np.sin(1)))

def test_function_as_operator_arg(evaluator):
    result = evaluator.evaluate('1 + sin(0)')
    assert np.allclose(result, 1.0)

def test_boolean_precedence_chain(evaluator):
    result = evaluator.evaluate('1 || 0 && 1')
    assert np.allclose(result, 1.0)

def test_d_squared_unicode(evaluator):
    result = evaluator.evaluate('d²(time)')
    assert np.allclose(result, 0.0, atol=1e-5)
