"""Tests for mask_value and is_masked utilities in web module"""
import pytest


@pytest.fixture(autouse=True)
def _prevent_bot_init(monkeypatch):
    """Prevent bot module from initializing real connections"""
    monkeypatch.setattr('bot.client', None)
    monkeypatch.setattr('bot._bot_loop', None)


class TestMaskValue:
    def test_empty_value(self):
        """Empty/None value returns empty string"""
        from web import mask_value
        assert mask_value('') == ''
        assert mask_value(None) == ''

    def test_short_value_fully_masked(self):
        """1-7 char values are fully masked"""
        from web import mask_value
        assert mask_value('abc') == '***'
        assert mask_value('1234567') == '*******'

    def test_medium_value_partial(self):
        """8-15 char values show 1 char each side"""
        from web import mask_value
        result = mask_value('12345678')
        assert result[0] == '1'
        assert result[-1] == '8'
        assert '***' in result

    def test_long_value_capped(self):
        """32+ char values show 4 chars each side with 32 asterisks"""
        from web import mask_value
        value = 'A' * 40
        result = mask_value(value)
        assert result[:4] == 'AAAA'
        assert result[-4:] == 'AAAA'
        assert '*' * 32 in result

    def test_proportional_masking(self):
        """16-23 char values show 2 chars each side"""
        from web import mask_value
        value = 'abcdefghijklmnop'  # 16 chars
        result = mask_value(value)
        assert result[:2] == 'ab'
        assert result[-2:] == 'op'


class TestIsMasked:
    def test_empty_value(self):
        """Empty/None returns False"""
        from web import is_masked
        assert is_masked('') is False
        assert is_masked(None) is False

    def test_masked_value(self):
        """Recognizes masked values"""
        from web import is_masked
        assert is_masked('a****b') is True
        assert is_masked('ab**cd') is True

    def test_unmasked_value(self):
        """Real values are not recognized as masked"""
        from web import is_masked
        assert is_masked('real_api_key_value_here_long_enough') is False
        assert is_masked('no_stars') is False

    def test_single_star_not_masked(self):
        """Single star is not considered masked"""
        from web import is_masked
        assert is_masked('a*b') is False
