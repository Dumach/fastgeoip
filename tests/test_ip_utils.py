from fastgeoip.ip_utils import validIPAddress, validate_ip


class TestValidateIp:
    def test_loopback(self) -> None:
        assert validate_ip("127.0.0.1") == "You are on localhost"
        assert validate_ip("::1") == "You are on localhost"

    def test_private_ipv4(self) -> None:
        assert validate_ip("192.168.1.1") == "You are on a private network"
        assert validate_ip("10.0.0.1") == "You are on a private network"
        assert validate_ip("172.16.0.1") == "You are on a private network"

    def test_public_ip(self) -> None:
        assert validate_ip("8.8.8.8") == ""
        assert validate_ip("1.1.1.1") == ""


class TestIpValidation:
    def test_valid_ipv4(self) -> None:
        assert validIPAddress("8.8.8.8") is True
        assert validIPAddress("192.168.1.1") is True

    def test_valid_ipv6(self) -> None:
        assert validIPAddress("2001:0db8:85a3:0000:0000:8a2e:0370:7334") is True
        assert validIPAddress("::1") is True

    def test_invalid_ip(self) -> None:
        assert validIPAddress("not-an-ip") is False
        assert validIPAddress("999.999.999.999") is False
        assert validIPAddress("") is False
