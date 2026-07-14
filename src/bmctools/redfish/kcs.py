"""Shared helpers for KCS control over Redfish.

KCS (Keyboard Controller Style) is the in-band IPMI system interface that lets
the host OS talk to the BMC without network credentials.  "Disabling KCS" here
means restricting that OS-to-BMC passthrough so the BMC can only be managed
out-of-band, and is done entirely via Redfish PATCH.

Vendors differ in what they patch (Dell toggles an iDRAC attribute; Supermicro
lowers the KCS interface privilege), but they share the same endpoint-loop
strategy: a candidate list of ``(endpoint, payload)`` pairs is tried in order —
older generation first, then the newer OEM path — and a ``404`` simply means
"wrong generation, try the next endpoint".
"""

import json
from typing import List, Optional, Tuple

# HTTP statuses that count as a successful PATCH. Vendors normally return 200
# (with a body); 204 (No Content) is accepted defensively.
_SUCCESS_STATUSES = (200, 204)


def patch_kcs_endpoints(api, endpoints_payloads: List[Tuple[str, dict]], vendor: str) -> str:
    """Apply the first working ``(endpoint, payload)`` PATCH from *endpoints_payloads*.

    Args:
        api: A :class:`~bmctools.redfish.fishapi.RedfishAPI` instance.
        endpoints_payloads: Ordered list of ``(endpoint, payload)`` pairs to try.
            Earlier entries target older BMC generations; a ``404`` advances to
            the next entry.
        vendor: Lowercased vendor key (e.g. ``'dell'``, ``'supermicro'``) used to
            tailor error messages (e.g. Supermicro license/BIOS hints).

    Returns:
        The endpoint that accepted the change.

    Raises:
        ValueError: If authentication is rejected (401), a license is required
            (Supermicro 403), an unexpected status is returned, or every
            candidate endpoint returned 404.
    """
    for endpoint, payload in endpoints_payloads:
        response = api.patch(endpoint, data=payload)
        status = response.status_code

        if status in _SUCCESS_STATUSES:
            return endpoint

        if status == 401:
            raise ValueError(
                'KCS control failed: authentication rejected (HTTP 401). '
                'Check the BMC credentials.'
            )

        if status == 403 and vendor == 'supermicro':
            raise ValueError(
                'KCS control failed: HTTP 403 — a license (SKU) is required '
                'for Supermicro KCS / out-of-band access on this BMC.'
            )

        if status == 404:
            # This generation does not expose that endpoint; try the next one.
            continue

        raise ValueError(
            f'KCS control failed: unexpected HTTP {status} at {endpoint}'
            f'{_error_detail(response)}'
        )

    if vendor == 'supermicro':
        raise ValueError(
            'KCS control failed: the BMC/BIOS does not support KCS control or '
            'requires a firmware update (all candidate endpoints returned 404).'
        )
    raise ValueError(
        'KCS control failed: unable to set KCS control on this device '
        '(all candidate endpoints returned 404).'
    )


def read_kcs_endpoint(api, endpoints: List[str]) -> Tuple[str, dict]:
    """GET the first readable endpoint from *endpoints*.

    Args:
        api: A :class:`~bmctools.redfish.fishapi.RedfishAPI` instance.
        endpoints: Ordered list of endpoints to try (older generation first).

    Returns:
        Tuple of ``(endpoint, json_data)`` for the first endpoint returning 200.

    Raises:
        ValueError: If none of the endpoints could be read.
    """
    for endpoint in endpoints:
        response = api.get(endpoint)
        if response.status_code == 200:
            try:
                return endpoint, response.json()
            except Exception:
                continue
    raise ValueError(
        'Unable to read KCS state: none of the candidate endpoints were '
        f'reachable ({", ".join(endpoints)}).'
    )


def _error_detail(response) -> str:
    """Best-effort extra detail for an unexpected Redfish response."""
    try:
        return f"\nError details: {json.dumps(response.json(), indent=2)}"
    except Exception:
        text = getattr(response, 'text', '')
        return f"\nResponse text: {text}" if text else ''
