from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest

from fastgeoip.config import Settings
from fastgeoip.geoip_service import get_reader, lookup_ip_address
from fastgeoip.models import IpLookupResponse


class TestLookupIpAddress:
    def test_full_record(
        self,
        mock_geoip_reader: MagicMock,
        make_mock_city: Callable[..., MagicMock],
        make_settings: Callable[..., Settings],
    ) -> None:
        mock_geoip_reader.city.return_value = make_mock_city("1.1.1.1", "AU", "Australia", "New South Wales", "Sydney")
        result = lookup_ip_address("1.1.1.1", make_settings(environment="DEV"))
        assert result == IpLookupResponse(
            country_code="AU",
            country_name="Australia",
            region_name="New South Wales",
            city="Sydney",
            ip="1.1.1.1",
        )

    def test_null_country_city_and_subdivision(
        self,
        mock_geoip_reader: MagicMock,
        make_mock_city: Callable[..., MagicMock],
        make_settings: Callable[..., Settings],
    ) -> None:
        # Real GeoLite2 data has entries without country/subdivision/city (e.g. 8.8.8.8).
        mock_city = make_mock_city("8.8.8.8")
        mock_city.country = None
        mock_city.subdivisions.most_specific = None
        mock_city.city = None
        mock_geoip_reader.city.return_value = mock_city
        result = lookup_ip_address("8.8.8.8", make_settings(environment="DEV"))
        assert result == IpLookupResponse(
            country_code=None, country_name=None, region_name=None, city=None, ip="8.8.8.8"
        )

    def test_reader_is_opened_once_per_db_path(
        self,
        make_mock_city: Callable[..., MagicMock],
        make_settings: Callable[..., Settings],
    ) -> None:
        get_reader.cache_clear()
        try:
            with patch("fastgeoip.geoip_service.geoip2.database.Reader") as mock_reader_class:
                mock_reader_class.return_value.city.return_value = make_mock_city("1.1.1.1")
                settings = make_settings(environment="DEV")
                lookup_ip_address("1.1.1.1", settings)
                lookup_ip_address("8.8.8.8", settings)
                assert mock_reader_class.call_count == 1
                assert mock_reader_class.call_args.args == (str(settings.db_path),)
        finally:
            get_reader.cache_clear()

    def test_lookup_exception_propagates(
        self,
        mock_geoip_reader: MagicMock,
        make_settings: Callable[..., Settings],
    ) -> None:
        mock_geoip_reader.city.side_effect = Exception("boom")
        with pytest.raises(Exception, match="boom"):
            lookup_ip_address("8.8.8.8", make_settings(environment="DEV"))
