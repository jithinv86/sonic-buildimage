import json
import os
import glob

import pytest

from sonic_platform_pddf_base.pddf_fan_conversion import (
    FanConversion,
    FanConversionError,
)


FORMULA_CASES = [
    ('lambda dc: ((dc - 10) / 6)', 50, 7),
    ('lambda dc: ((dc*100)/625 - 1)', 50, 7),
    ('lambda dc: ((dc*100)/625 -1)', 50, 7),
    ('lambda dc: ((dc*100.0)/625 - 1)', 50, 7),
    ('lambda dc: ((dc*100.0)/625)', 50, 8),
    ('lambda dc: ((dc*255)/100)', 50, 128),
    ('lambda dc: ((dc*255.0)/100)', 50, 128),
    ('lambda dc: ((dc/100) * 255)', 50, 128),
    ('lambda dc: dc', 50, 50),
    ('lambda dc: dc*255/100', 50, 128),
    ('lambda pwm: ( (pwm * 6) + 10)', 127, 772),
    ('lambda pwm: (((pwm+1)*625)/100)', 127, 800),
    ('lambda pwm: (((pwm+1)*625+75)/100)', 127, 801),
    ('lambda pwm: (((pwm+1)*625.0)/100)', 127, 800),
    ('lambda pwm: ((pwm*100)/255)', 127, 50),
    ('lambda pwm: ((pwm*100.0)/256)', 127, 50),
    ('lambda pwm: ((pwm*625.0)/100)', 127, 794),
    ('lambda pwm: ((pwm/18000) * 100)', 127, 1),
    ('lambda pwm: ((pwm/255) * 100)', 127, 50),
    ('lambda pwm: ((pwm/34000) * 100)', 127, 0),
    ('lambda pwm: (pwm*1.0)', 127, 127),
    ('lambda pwm: pwm', 127, 127),
    ('lambda pwm: pwm*100/255', 127, 50),
    ('lambda pwm: pwm/255*100', 127, 50),
]


@pytest.mark.parametrize('expression,value,expected', FORMULA_CASES)
def test_checked_in_formula_profiles(expression, value, expected):
    converter = FanConversion(expression)
    assert int(round(converter.convert(value))) == expected


def test_all_repository_formulas_are_supported():
    repository_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')
    )
    plugin_paths = glob.glob(
        os.path.join(repository_root, 'device', '*', '*', 'pddf', 'pd-plugin.json')
    )
    formula_files = 0
    formula_count = 0

    for plugin_path in plugin_paths:
        with open(plugin_path) as plugin_file:
            fan_data = json.load(plugin_file).get('FAN', {})

        file_has_formula = False
        for field in ('pwm_to_duty_cycle', 'duty_cycle_to_pwm'):
            if field not in fan_data:
                continue
            file_has_formula = True
            formula_count += 1
            converter = FanConversion(fan_data[field])
            values = range(0, 101) if field == 'duty_cycle_to_pwm' else (
                0, 1, 50, 100, 127, 255, 256, 625, 18000, 34000
            )
            for value in values:
                converter.convert(value)

        formula_files += int(file_has_formula)

    assert formula_files == 27
    assert formula_count == 50


@pytest.mark.parametrize(
    'expression',
    [
        '',
        '1 + 2',
        'lambda: 1',
        'lambda x, y: x + y',
        'lambda x=1: x',
        'lambda *args: 1',
        'lambda **kwargs: 1',
        'lambda x: y',
        'lambda x: True',
        "lambda x: 'text'",
        'lambda x: x ** 2',
        'lambda x: x // 2',
        'lambda x: x % 2',
        'lambda x: x < 2',
        'lambda x: x and 1',
        'lambda x: x if x else 0',
        'lambda x: [x]',
        'lambda x: x[0]',
        'lambda x: x.real',
        'lambda x: sum([x])',
        "lambda x: __import__('os')",
        'lambda x: (y := x)',
    ],
)
def test_unsupported_expressions_are_rejected(expression):
    with pytest.raises(FanConversionError):
        FanConversion(expression)


def test_malicious_expression_has_no_side_effect(tmp_path):
    marker = tmp_path / 'f074-marker'
    expression = "lambda x: __import__('os').system('touch %s') or x" % marker

    with pytest.raises(FanConversionError):
        FanConversion(expression)

    assert not marker.exists()


def test_expression_resource_limits():
    with pytest.raises(FanConversionError):
        FanConversion('lambda x: x' + (' ' * 300))

    with pytest.raises(FanConversionError):
        FanConversion('lambda x: ' + ('-' * 20) + 'x')

    with pytest.raises(FanConversionError):
        FanConversion('lambda x: ' + ' + '.join(['x'] * 40))


@pytest.mark.parametrize('value', [None, True, '1', float('inf'), float('nan')])
def test_invalid_inputs_are_rejected(value):
    converter = FanConversion('lambda x: x')
    with pytest.raises(FanConversionError):
        converter.convert(value)


def test_invalid_arithmetic_is_rejected():
    with pytest.raises(FanConversionError):
        FanConversion('lambda x: 1e309')

    with pytest.raises(FanConversionError):
        FanConversion('lambda x: 1000000000001')

    converter = FanConversion('lambda x: 1 / (x - 1)')
    with pytest.raises(FanConversionError):
        converter.convert(1)

    converter = FanConversion('lambda x: x * 1000000')
    with pytest.raises(FanConversionError):
        converter.convert(1000001)
