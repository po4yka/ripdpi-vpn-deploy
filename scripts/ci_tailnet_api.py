"""Bounded OAuth enrollment for a disposable CI controller and its one guest."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.tailscale.com/api/v2/"


class EnrollmentError(ValueError):
    """Categorical failure: HTTP bodies and credentials never enter diagnostics."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EnrollmentError("tailnet-redirect-refused")


class Enrollment:
    def __init__(self, client_id, client_secret, tailnet, tag, *, opener=None):
        if (not all(isinstance(value, str) and value for value in
                    (client_id, client_secret, tailnet, tag))
                or not re.fullmatch(r"tag:[a-zA-Z][a-zA-Z0-9-]{0,62}", tag)):
            raise EnrollmentError("tailnet-configuration-invalid")
        self.client_id, self.client_secret = client_id, client_secret
        self.tailnet, self.tag = urllib.parse.quote(tailnet, safe=""), tag
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.owned_keys = []

    def _request(self, path, *, method="POST", document=None, token=None, missing_ok=False):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if path == "oauth/token":
            data = urllib.parse.urlencode(document).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(document).encode() if document is not None else None
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise EnrollmentError("tailnet-response-invalid")
                result = json.loads(raw) if raw else {}
                if not isinstance(result, dict):
                    raise EnrollmentError("tailnet-response-invalid")
                return result
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return {}
            raise EnrollmentError("tailnet-request-failed") from None
        except (OSError, ValueError):
            raise EnrollmentError("tailnet-request-failed") from None

    def _token(self):
        result = self._request("oauth/token", document={
            "grant_type": "client_credentials", "client_id": self.client_id,
            "client_secret": self.client_secret,
        })
        token = result.get("access_token")
        if not isinstance(token, str) or not token:
            raise EnrollmentError("tailnet-token-invalid")
        return token

    def key(self):
        result = self._request(f"tailnet/{self.tailnet}/keys", token=self._token(), document={
            "expirySeconds": 600, "description": "disposable deployment",
            "capabilities": {"devices": {"create": {
                "reusable": False, "ephemeral": True, "preauthorized": True,
                "tags": [self.tag],
            }}},
        })
        identifier, key = result.get("id"), result.get("key")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier):
            raise EnrollmentError("tailnet-key-response-invalid")
        self.owned_keys.append(identifier)
        if not isinstance(key, str) or not key.startswith("tskey-auth-"):
            raise EnrollmentError("tailnet-key-response-invalid")
        return key

    def revoke(self):
        failed = False
        for identifier in list(self.owned_keys):
            try:
                self._request(f"tailnet/{self.tailnet}/keys/{identifier}", method="DELETE",
                              token=self._token(), missing_ok=True)
                self.owned_keys.remove(identifier)
            except EnrollmentError:
                failed = True
        if failed:
            raise EnrollmentError("tailnet-key-cleanup-incomplete")
