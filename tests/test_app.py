from pathlib import Path
from typing_extensions import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from fastgeoip.app import create_app
from fastgeoip.config import Environment, Settings


def make_mock_city(
    ip: str,
    country_code: str = "US",
    country_name: str = "United States",
    region_name: str = "California",
    city: str = "San Francisco",
):
    """Create a mock geoip2 City response object."""
    mock_city = MagicMock()
    mock_city.ip = ip

    mock_country = MagicMock()
    mock_country.iso_code = country_code
    mock_country.name = country_name
    mock_city.country = mock_country

    mock_subdivision = MagicMock()
    mock_subdivision.name = region_name
    mock_subdivisions = MagicMock()
    mock_subdivisions.most_specific = mock_subdivision
    mock_city.subdivisions = mock_subdivisions

    mock_city_obj = MagicMock()
    mock_city_obj.name = city
    mock_city.city = mock_city_obj

    return mock_city


@pytest.fixture()
def client_prod() -> TestClient:
    settings  = Settings(environment="PROD", access_key="test-key-123")
    return  TestClient(create_app(settings))


@pytest.fixture()
def client_dev() -> TestClient:
    return TestClient(create_app(Settings(environment="DEV")))


@pytest.fixture()
def mock_geoip_reader() -> Generator[MagicMock]:
    """Fixture that provides a properly mocked geoip2 database reader."""
    with patch("fastgeoip.app.geoip2.database.Reader") as mock_reader_class:
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader
        yield mock_reader


class TestSettings:
    def test_defaults(self) -> None:
        s = Settings(_env_file=None)
        assert s.environment == Environment.PROD
        assert s.host == "127.0.0.1"
        assert s.port == 8080
        assert s.log_path == Path("./logs")
        assert s.db_path == Path("./db/GeoLite2-City.mmdb")
        assert s.access_keys == []
        assert s.workers == 1
        assert s.log_level == "info"

    def test_environment_is_case_insensitive(self) -> None:
        assert Settings(_env_file=None, environment="dev").environment == Environment.DEV
        assert Settings(_env_file=None, environment="Debug").environment == Environment.DEBUG
        assert Settings(_env_file=None, environment="prod").environment == Environment.PROD

    def test_access_keys_csv_split(self) -> None:
        s = Settings(_env_file=None, access_key="key-1, key-2 ,,key-3")
        assert s.access_keys == ["key-1", "key-2", "key-3"]

    def test_log_level_only_debug_in_debug_mode(self) -> None:
        assert Settings(_env_file=None, environment="DEBUG").log_level == "debug"
        assert Settings(_env_file=None, environment="DEV").log_level == "info"

    def test_single_worker_outside_prod(self) -> None:
        assert Settings(_env_file=None, environment="DEV").workers == 1

    def test_empty_ssl_values_become_none(self) -> None:
        s = Settings(_env_file=None, ssl_cert="", ssl_key="")
        assert s.ssl_cert is None
        assert s.ssl_key is None


class TestAppFactory:
    def test_lazy_module_level_app_bridge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`uvicorn fastgeoip.app:app` resolves `app` lazily from the module."""
        from fastgeoip import app as app_module

        monkeypatch.setattr(
            app_module,
            "get_settings",
            lambda: Settings(_env_file=None, environment="PROD", access_key="bridge-key"),
        )
        assert isinstance(app_module.app, FastAPI)


class TestHealthEndpoint:
    def test_health_success(self, client_prod: TestClient, mock_geoip_reader: MagicMock) -> None:
        mock_geoip_reader.city.return_value = make_mock_city("1.1.1.1")
        response = client_prod.get("/geoip/health")
        assert response.status_code == 200
        assert response.json() == {"detail": "healthy", "database": "ok"}

    def test_health_failure(self, client_prod: TestClient, mock_geoip_reader: MagicMock) -> None:
        mock_geoip_reader.city.side_effect = Exception("DB error")
        response = client_prod.get("/geoip/health")
        assert response.status_code == 503
        assert response.json() == {"detail": "unhealthy"}

    def test_health_no_auth_required(self, client_prod: TestClient, mock_geoip_reader: MagicMock) -> None:
        mock_geoip_reader.city.return_value = make_mock_city("1.1.1.1")
        response = client_prod.get("/geoip/health")
        assert response.status_code == 200


class TestGetMyIpEndpoint:
    def test_get_myip_valid_ip(self, client_dev: TestClient, mock_geoip_reader: MagicMock) -> None:
        mock_geoip_reader.city.return_value = make_mock_city("8.8.8.8")
        with patch("fastgeoip.app.get_ip_header", return_value="8.8.8.8"):
            response = client_dev.get("/geoip/")
            assert response.status_code == 200
            data = response.json()
            assert data["ip"] == "8.8.8.8"
            assert data["country_code"] == "US"

    def test_get_myip_localhost(self, client_dev: TestClient, mock_geoip_reader: MagicMock) -> None:
        with patch("fastgeoip.app.get_ip_header", return_value="127.0.0.1"):
            response = client_dev.get("/geoip/")
            assert response.status_code == 200
            assert response.json() == {"detail": "You are on localhost"}

    def test_get_myip_private_ip(self, client_dev: TestClient, mock_geoip_reader: MagicMock) -> None:
        with patch("fastgeoip.app.get_ip_header", return_value="192.168.1.1"):
            response = client_dev.get("/geoip/")
            assert response.status_code == 200
            assert response.json() == {"detail": "You are on a private network"}

    def test_get_myip_invalid_format(self, client_dev: TestClient, mock_geoip_reader: MagicMock) -> None:
        with patch("fastgeoip.app.get_ip_header", return_value="not-an-ip"):
            response = client_dev.get("/geoip/")
            assert response.status_code == 200
            assert "incorrect format" in response.json()["detail"]

    def test_get_myip_requires_auth_in_prod(self, client_prod: TestClient, mock_geoip_reader: MagicMock) -> None:
        with patch("fastgeoip.app.get_ip_header", return_value="8.8.8.8"):
            response = client_prod.get("/geoip/")
            assert response.status_code == 403


class TestGeolookupEndpoint:
    def test_geolookup_valid_ip(self, client_prod: TestClient, mock_geoip_reader: MagicMock) -> None:
        mock_geoip_reader.city.return_value = make_mock_city("1.1.1.1", "AU", "Australia", "New South Wales", "Sydney")
        response = client_prod.get("/geoip/geolookup", params={"ip": "1.1.1.1"}, headers={"X-API-KEY": "test-key-123"})
        assert response.status_code == 200
        data = response.json()
        assert data["ip"] == "1.1.1.1"
        assert data["country_code"] == "AU"

    def test_geolookup_invalid_ip(self, client_prod: TestClient, mock_geoip_reader: MagicMock) -> None:
        response = client_prod.get("/geoip/geolookup", params={"ip": "invalid"}, headers={"X-API-KEY": "test-key-123"})
        assert response.status_code == 200
        assert "incorrect format" in response.json()["detail"]

    def test_geolookup_localhost(self, client_prod: TestClient, mock_geoip_reader: MagicMock) -> None:
        response = client_prod.get(
            "/geoip/geolookup", params={"ip": "127.0.0.1"}, headers={"X-API-KEY": "test-key-123"}
        )
        assert response.status_code == 200
        assert response.json() == {"detail": "You are on localhost"}

    def test_geolookup_requires_auth(self, client_prod: TestClient, mock_geoip_reader: MagicMock) -> None:
        response = client_prod.get("/geoip/geolookup", params={"ip": "8.8.8.8"})
        assert response.status_code == 403


class TestAuthMiddleware:
    def test_valid_api_key(self, client_prod: TestClient, mock_geoip_reader: MagicMock) -> None:
        mock_geoip_reader.city.return_value = make_mock_city("8.8.8.8")
        with patch("fastgeoip.app.get_ip_header", return_value="8.8.8.8"):
            response = client_prod.get("/geoip/", headers={"X-API-KEY": "test-key-123"})
            assert response.status_code == 200

    def test_invalid_api_key_in_prod(self) -> None:
        client = TestClient(create_app(Settings(_env_file=None, environment="PROD", access_key="valid-key")))
        with patch("fastgeoip.app.geoip2.database.Reader"):
            response = client.get("/geoip/", headers={"X-API-KEY": "wrong-key"})
        assert response.status_code == 403

    def test_missing_api_key_in_prod(self) -> None:
        client = TestClient(create_app(Settings(_env_file=None, environment="PROD", access_key="valid-key")))
        with patch("fastgeoip.app.geoip2.database.Reader"):
            response = client.get("/geoip/")
        assert response.status_code == 403

    def test_dev_mode_bypasses_auth(self, client_dev: TestClient, mock_geoip_reader: MagicMock) -> None:
        mock_geoip_reader.city.return_value = make_mock_city("8.8.8.8")
        with patch("fastgeoip.app.get_ip_header", return_value="8.8.8.8"):
            response = client_dev.get("/geoip/")
            assert response.status_code == 200


class TestRateLimiting:
    def test_rate_limit_works(self, client_dev: TestClient, mock_geoip_reader: MagicMock) -> None:
        """Test that rate limiting is enforced (5 requests per minute for /geoip/)."""
        mock_geoip_reader.city.return_value = make_mock_city("1.1.1.1")
        with patch("fastgeoip.app.get_ip_header", return_value="1.1.1.1"):
            # Make 5 requests - should succeed
            for _ in range(5):
                response = client_dev.get("/geoip/")
                assert response.status_code == 200
            # 6th request should be rate limited
            response = client_dev.get("/geoip/")
            assert response.status_code == 429


class TestIpValidation:
    def test_valid_ipv4(self) -> None:
        from fastgeoip.app import validIPAddress

        assert validIPAddress("8.8.8.8") is True
        assert validIPAddress("192.168.1.1") is True

    def test_valid_ipv6(self) -> None:
        from fastgeoip.app import validIPAddress

        assert validIPAddress("2001:0db8:85a3:0000:0000:8a2e:0370:7334") is True
        assert validIPAddress("::1") is True

    def test_invalid_ip(self) -> None:
        from fastgeoip.app import validIPAddress

        assert validIPAddress("not-an-ip") is False
        assert validIPAddress("999.999.999.999") is False
        assert validIPAddress("") is False


class TestValidateIp:
    def test_loopback(self) -> None:
        from fastgeoip.app import validate_ip

        assert validate_ip("127.0.0.1") == "You are on localhost"
        assert validate_ip("::1") == "You are on localhost"

    def test_private_ipv4(self) -> None:
        from fastgeoip.app import validate_ip

        assert validate_ip("192.168.1.1") == "You are on a private network"
        assert validate_ip("10.0.0.1") == "You are on a private network"
        assert validate_ip("172.16.0.1") == "You are on a private network"

    def test_public_ip(self) -> None:
        from fastgeoip.app import validate_ip

        assert validate_ip("8.8.8.8") == ""
        assert validate_ip("1.1.1.1") == ""
