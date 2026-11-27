"""Shared, hermetic fixtures for the test suite."""

from collections.abc import Callable, Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fastgeoip.app import create_app
from fastgeoip.config import Settings
from fastgeoip.geoip_service import get_reader


@pytest.fixture()
def make_settings() -> Callable[..., Settings]:
    """Build Settings without reading the repo's .env file."""
    return lambda **kwargs: Settings(_env_file=None, **kwargs)


@pytest.fixture()
def client_prod(make_settings: Callable[..., Settings]) -> TestClient:
    return TestClient(create_app(make_settings(environment="PROD", access_key="test-key-123")))


@pytest.fixture()
def client_dev(make_settings: Callable[..., Settings]) -> TestClient:
    return TestClient(create_app(make_settings(environment="DEV")))


@pytest.fixture()
def make_mock_city() -> Callable[..., MagicMock]:
    """Create a mock geoip2 City response with all fields populated by default."""

    def factory(
        ip: str,
        country_code: str = "US",
        country_name: str = "United States",
        region_name: str = "California",
        city: str = "San Francisco",
    ) -> MagicMock:
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

    return factory


@pytest.fixture()
def mock_geoip_reader() -> Iterator[MagicMock]:
    """Patch the Reader at its source and return the reader instance it creates.

    `get_reader` is lru_cached, so the cache must be cleared around the patch;
    otherwise a reader built by an earlier test would be reused.
    """
    get_reader.cache_clear()
    try:
        with patch("fastgeoip.geoip_service.geoip2.database.Reader") as reader_class:
            reader = MagicMock()
            reader_class.return_value = reader
            yield reader
    finally:
        get_reader.cache_clear()
