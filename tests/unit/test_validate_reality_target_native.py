"""Exact supported browser-shaped engine; required isolated native lane."""
import os
import pytest
from test_validate_reality_target import tls_site, run_site

pytestmark = pytest.mark.native_runtime

def test_supported_real_client_handshake(tls_site):
    directory = os.environ["REALITY_TEST_CLIENT_DIR"]
    result, report = run_site(tls_site, REALITY_CLIENT_DIR=directory)
    assert result.returncode == 0, (report, result.stderr)
    assert report['client_compatibility'] == 'passed'
    assert report['client_engine'] == 'curl-impersonate-0.6.1/chrome116'
    assert len(tls_site[2]) == 3
    assert tls_site[2][-1] == ("TLSv1.3", "h2")


def test_owned_service_reached_through_explicit_ingress(tls_site):
    port, _, seen, _ = tls_site
    result, report = run_site(tls_site, TARGET_MODE='owned-public', TARGET='127.0.0.1:8443',
                              PUBLIC_ENDPOINT=f"{os.environ['REALITY_TEST_PUBLIC_IP']}:{port}",
                              OWNED_SNI='exact.example')
    assert result.returncode == 0, report
    assert report['mode'] == 'owned-public'
    assert report['hygiene'] == 'passed'
    assert len(seen) == 2


def test_pinned_client_ignores_ambient_curl_config(tls_site, tmp_path):
    (tmp_path / '.curlrc').write_text('this-option-does-not-exist\n')
    result, report = run_site(tls_site, CURL_HOME=str(tmp_path),
                              REALITY_CLIENT_DIR=os.environ['REALITY_TEST_CLIENT_DIR'])
    assert result.returncode == 0, report
    assert report['client_compatibility'] == 'passed'


@pytest.mark.parametrize('tls_site', ['client-no-h2'], indirect=True)
def test_client_h2_downgrade_does_not_relabel_hygiene(tls_site):
    result, report = run_site(tls_site, REALITY_CLIENT_DIR=os.environ['REALITY_TEST_CLIENT_DIR'])
    assert result.returncode != 0
    assert report['hygiene'] == 'passed'
    assert report['client_compatibility'] == 'failed'
    assert report['reason_codes'] == ['client_failed']
