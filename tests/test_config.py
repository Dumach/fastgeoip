from collections.abc import Callable

import pytest
from pydantic import ValidationError

from fastgeoip.config import Environment, Settings


class TestFailFastValidation:
    def test_prod_without_access_key_raises(self, make_settings: Callable[..., Settings]) -> None:
        with pytest.raises(ValidationError, match="ACCESS_KEY"):
            make_settings(environment="PROD", access_key="")

    def test_debug_without_access_key_raises(self, make_settings: Callable[..., Settings]) -> None:
        with pytest.raises(ValidationError, match="ACCESS_KEY"):
            make_settings(environment="DEBUG", access_key="")

    def test_dev_without_access_key_ok(self, make_settings: Callable[..., Settings]) -> None:
        assert make_settings(environment="DEV", access_key="").access_keys == []

    def test_access_key_is_csv_split(self, make_settings: Callable[..., Settings]) -> None:
        assert make_settings(environment="DEV", access_key="a, b ,c").access_keys == ["a", "b", "c"]

    def test_ssl_half_configured_raises(self, make_settings: Callable[..., Settings]) -> None:
        with pytest.raises(ValidationError, match="together"):
            make_settings(environment="DEV", ssl_cert="/tmp/cert.pem")

    def test_ssl_missing_file_raises(self, make_settings: Callable[..., Settings], tmp_path) -> None:
        missing = str(tmp_path / "missing.pem")
        with pytest.raises(ValidationError, match="missing file"):
            make_settings(environment="DEV", ssl_cert=missing, ssl_key=missing)

    def test_environment_is_case_insensitive(self, make_settings: Callable[..., Settings]) -> None:
        assert make_settings(environment="dev").environment == Environment.DEV
