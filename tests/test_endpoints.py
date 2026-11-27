from collections.abc import Callable
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestHealth:
    def test_returns_200_when_lookup_works(
        self,
        client_prod: TestClient,
        mock_geoip_reader: MagicMock,
        make_mock_city: Callable[..., MagicMock],
    ) -> None:
        mock_geoip_reader.city.return_value = make_mock_city("1.1.1.1")
        response = client_prod.get("/health")
        assert response.status_code == 200
        assert response.json() == {"detail": "healthy", "database": "ok"}

    def test_returns_503_on_lookup_failure(self, client_prod: TestClient, mock_geoip_reader: MagicMock) -> None:
        mock_geoip_reader.city.side_effect = Exception("DB error")
        response = client_prod.get("/health")
        assert response.status_code == 503
        assert response.json() == {"detail": "unhealthy"}


class TestGetMyIpEndpoint:
    def test_valid_ip(
        self, client_dev: TestClient, mock_geoip_reader: MagicMock, make_mock_city: Callable[..., MagicMock]
    ) -> None:
        mock_geoip_reader.city.return_value = make_mock_city("8.8.8.8")
        with patch("fastgeoip.app.get_ip_header", return_value="8.8.8.8"):
            response = client_dev.get("/")
        assert response.status_code == 200
        assert response.json()["ip"] == "8.8.8.8"
        assert response.json()["country_code"] == "US"

    def test_localhost(self, client_dev: TestClient) -> None:
        with patch("fastgeoip.app.get_ip_header", return_value="127.0.0.1"):
            response = client_dev.get("/")
        assert response.status_code == 200
        assert response.json() == {"detail": "You are on localhost"}

    def test_private_ip(self, client_dev: TestClient) -> None:
        with patch("fastgeoip.app.get_ip_header", return_value="192.168.1.1"):
            response = client_dev.get("/")
        assert response.status_code == 200
        assert response.json() == {"detail": "You are on a private network"}

    def test_invalid_format(self, client_dev: TestClient) -> None:
        with patch("fastgeoip.app.get_ip_header", return_value="not-an-ip"):
            response = client_dev.get("/")
        assert response.status_code == 200
        assert "incorrect format" in response.json()["detail"]


class TestGeolookupEndpoint:
    def test_valid_ip(
        self, client_dev: TestClient, mock_geoip_reader: MagicMock, make_mock_city: Callable[..., MagicMock]
    ) -> None:
        mock_geoip_reader.city.return_value = make_mock_city("1.1.1.1", "AU", "Australia", "New South Wales", "Sydney")
        response = client_dev.get("/geolookup", params={"ip": "1.1.1.1"})
        assert response.status_code == 200
        assert response.json()["ip"] == "1.1.1.1"
        assert response.json()["country_code"] == "AU"

    def test_invalid_ip(self, client_dev: TestClient) -> None:
        response = client_dev.get("/geolookup", params={"ip": "invalid"})
        assert response.status_code == 200
        assert "incorrect format" in response.json()["detail"]

    def test_localhost(self, client_dev: TestClient) -> None:
        response = client_dev.get("/geolookup", params={"ip": "127.0.0.1"})
        assert response.status_code == 200
        assert response.json() == {"detail": "You are on localhost"}


class TestNullGeoipFields:
    def test_lookup_returns_nulls(
        self, client_dev: TestClient, mock_geoip_reader: MagicMock, make_mock_city: Callable[..., MagicMock]
    ) -> None:
        mock_city = make_mock_city("8.8.8.8")
        mock_city.country = None
        mock_city.subdivisions.most_specific = None
        mock_city.city = None
        mock_geoip_reader.city.return_value = mock_city
        response = client_dev.get("/geolookup", params={"ip": "8.8.8.8"})
        assert response.status_code == 200
        assert response.json() == {
            "country_code": None,
            "country_name": None,
            "region_name": None,
            "city": None,
            "ip": "8.8.8.8",
        }
