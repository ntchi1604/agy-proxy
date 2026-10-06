import asyncio
import socket
import unittest

from agy_proxy.dns_fallback import (
    _is_ip_or_local,
    install_dns_fallback,
    patched_getaddrinfo,
)


class TestDnsFallback(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        install_dns_fallback()

    def test_is_ip_or_local(self):
        self.assertTrue(_is_ip_or_local("127.0.0.1"))
        self.assertTrue(_is_ip_or_local(b"127.0.0.1"))
        self.assertTrue(_is_ip_or_local("localhost"))
        self.assertTrue(_is_ip_or_local(b"localhost"))
        self.assertTrue(_is_ip_or_local("::1"))
        self.assertTrue(_is_ip_or_local("192.168.1.1"))
        self.assertTrue(_is_ip_or_local(b"192.168.1.1"))
        self.assertFalse(_is_ip_or_local("oauth2.googleapis.com"))
        self.assertFalse(_is_ip_or_local(b"oauth2.googleapis.com"))

    def test_patched_getaddrinfo_localhost(self):
        res = patched_getaddrinfo("127.0.0.1", 8000, family=socket.AF_INET)
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0][4][0], "127.0.0.1")

        # Test with bytes host
        res_bytes = patched_getaddrinfo(b"127.0.0.1", 8000, family=socket.AF_INET)
        self.assertTrue(len(res_bytes) > 0)
        self.assertEqual(res_bytes[0][4][0], "127.0.0.1")

    async def test_asyncio_loop_getaddrinfo_with_family_keyword_arg(self):
        """
        Verifies that BaseEventLoop.getaddrinfo does not raise:
        TypeError: BaseEventLoop.run_in_executor() got an unexpected keyword argument 'family'
        when called with keyword arguments like family=socket.AF_INET, and supports bytes host.
        """
        loop = asyncio.get_running_loop()
        # Should not raise TypeError: run_in_executor unexpected keyword argument 'family'
        res = await loop.getaddrinfo(
            "127.0.0.1",
            8000,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0][4][0], "127.0.0.1")

        # Support bytes host from anyio/httpcore
        res_b = await loop.getaddrinfo(
            b"127.0.0.1",
            8000,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        self.assertTrue(len(res_b) > 0)
        self.assertEqual(res_b[0][4][0], "127.0.0.1")

    def test_patched_getaddrinfo_stale_fallback_on_system_failure(self):
        """Tests that when system getaddrinfo fails with gaierror -3, last known good stale IP is returned."""
        import unittest.mock
        from agy_proxy import dns_fallback

        test_host = "daily-cloudcode-pa.googleapis.com"
        orig_fn = dns_fallback._ORIG_GETADDRINFO

        def fake_getaddrinfo(h, port, family=0, type=0, proto=0, flags=0):
            if h == test_host:
                raise socket.gaierror(-3, "Temporary failure in name resolution")
            # If resolved IP is passed, succeed:
            return orig_fn(h, port, family, type, proto, flags)

        with unittest.mock.patch("agy_proxy.dns_fallback._ORIG_GETADDRINFO", side_effect=fake_getaddrinfo):
            # Clear fresh cache for this host to force error path
            with dns_fallback._CACHE_LOCK:
                dns_fallback._DNS_CACHE.pop(test_host, None)
            res = patched_getaddrinfo(test_host, 443, family=socket.AF_INET)
            self.assertTrue(len(res) > 0)
            self.assertIn(res[0][4][0], dns_fallback._LAST_KNOWN_IPS[test_host])


if __name__ == "__main__":
    unittest.main()
