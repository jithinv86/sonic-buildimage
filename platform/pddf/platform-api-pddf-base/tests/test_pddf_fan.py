import sys
import types

import pytest


if 'sonic_platform_base.fan_base' not in sys.modules:
    sonic_platform_base = types.ModuleType('sonic_platform_base')
    sonic_platform_base.__path__ = []
    fan_base = types.ModuleType('sonic_platform_base.fan_base')

    class FanBase(object):
        def __init__(self):
            pass

    fan_base.FanBase = FanBase
    sonic_platform_base.fan_base = fan_base
    sys.modules['sonic_platform_base'] = sonic_platform_base
    sys.modules['sonic_platform_base.fan_base'] = fan_base


from sonic_platform_pddf_base.pddf_fan import PddfFan
from sonic_platform_pddf_base.pddf_fan_conversion import FanConversionError


class FakePddfData(object):
    def __init__(self, pwm='127'):
        self.pwm = pwm
        self.writes = []

    def get_platform(self):
        return {
            'num_fantrays': 1,
            'num_fans_pertray': 1,
        }

    def get_attr_name_output(self, device, attribute):
        if attribute == 'fan1_pwm':
            return {'status': self.pwm}
        return None

    def set_attr_name_output(self, device, attribute, value):
        self.writes.append((device, attribute, value))
        return {'status': True}


def make_fan(pddf_data=None, fan_data=None):
    if pddf_data is None:
        pddf_data = FakePddfData()
    if fan_data is None:
        fan_data = {
            'pwm_to_duty_cycle': 'lambda pwm: pwm*100/255',
            'duty_cycle_to_pwm': 'lambda dc: dc*255/100',
        }
    plugin_data = {'FAN': fan_data}
    return PddfFan(0, 0, pddf_data, plugin_data), pddf_data


def test_get_speed_uses_safe_converter():
    fan, _ = make_fan()
    assert fan.get_speed() == 50
    assert fan.get_target_speed() == 50


def test_set_speed_uses_safe_converter():
    fan, pddf_data = make_fan()
    assert fan.set_speed(50) is True
    assert pddf_data.writes == [('FAN-CTRL', 'fan1_pwm', 128)]


def test_invalid_expression_is_rejected_during_initialization(tmp_path):
    marker = tmp_path / 'f074-fan-marker'
    fan_data = {
        'pwm_to_duty_cycle':
            "lambda pwm: __import__('os').system('touch %s') or pwm" % marker,
    }

    with pytest.raises(FanConversionError):
        make_fan(fan_data=fan_data)

    assert not marker.exists()


def test_conversion_failure_prevents_hardware_write():
    pddf_data = FakePddfData()
    fan_data = {
        'pwm_to_duty_cycle': 'lambda pwm: pwm',
        'duty_cycle_to_pwm': 'lambda dc: 1 / (dc - 50)',
    }
    fan, _ = make_fan(pddf_data=pddf_data, fan_data=fan_data)

    with pytest.raises(FanConversionError):
        fan.set_speed(50)

    assert pddf_data.writes == []


def test_missing_read_converter_is_reported():
    fan, _ = make_fan(fan_data={})
    with pytest.raises(ValueError, match='pwm_to_duty_cycle'):
        fan.get_speed()


@pytest.mark.parametrize('speed', [-1, 101])
def test_invalid_speed_remains_rejected(speed):
    fan, pddf_data = make_fan()
    assert fan.set_speed(speed) is False
    assert pddf_data.writes == []
