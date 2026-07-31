import json
import re
from typing import Optional
from bmctools.redfish.fishapi import RedfishAPI

BOOT_REF_RE = re.compile(r'Boot[0-9A-Fa-f]{4}$')


class _BootOrderReadOnly(ValueError):
    """Raised internally when the BMC rejects ``Boot.BootOrder`` as read-only."""


def _normalize_device_name(name: str) -> str:
    """Reduce a boot device label to a form comparable across namespaces.

    The standard ``BootOptions`` display names and the Lenovo OEM device names
    describe the same devices with different punctuation — ``'CD_DVDRom'`` vs
    ``'CD/DVD Rom'``, ``'HardDisk'`` vs ``'Hard Disk'``, ``'ubuntu_Boot0008'``
    vs ``'ubuntu - Boot0008'`` — so strip everything but alphanumerics.
    """
    return re.sub(r'[^0-9a-z]', '', (name or '').lower())


def _canonical_mac(mac: str) -> str:
    """Normalize a MAC string to canonical ``XX:XX:XX:XX:XX:XX`` (upper, colon-separated)."""
    hex_only = mac.replace(':', '').replace('-', '').upper()
    return ':'.join(hex_only[i:i + 2] for i in range(0, len(hex_only), 2))


def _mac_from_uefi_device_path(uefi_path: str) -> Optional[str]:
    """Extract a MAC address from a UEFI device path of the form ``.../MAC(XXXXXXXXXXXX,...)``.

    Returns the canonical MAC string, or ``None`` if not present.
    """
    if not uefi_path or '/MAC(' not in uefi_path:
        return None
    mac_start = uefi_path.find('/MAC(') + 5
    mac_end = uefi_path.find(',', mac_start)
    if mac_end <= mac_start:
        return None
    token = uefi_path[mac_start:mac_end]
    if len(token.replace(':', '').replace('-', '')) != 12:
        return None
    return _canonical_mac(token)


class LenovoFish:
    """
    Lenovo (XClarity Controller / ThinkSystem) Redfish implementation.

    Lenovo BMCs use '1' as the system and manager ID under /redfish/v1/.
    Four XCC behaviours drive the shape of this class:

    * **Boot order.** Recent XCC firmware exposes the standard
      ``Boot.BootOrder`` array plus a ``BootOptions`` collection, and boot
      order is set by PATCHing ``BootOrder`` with ``BootNNNN`` references.
      Older firmware exposes neither, and boot order lives in the Lenovo OEM
      resource ``/Systems/{id}/Oem/Lenovo/BootSettings`` as ``BootOrderNext``
      — a list of human-readable device names drawn from
      ``BootOrderSupported``. Every boot-order method here probes the standard
      properties first and falls back to the OEM resource, which recent
      firmware marks deprecated in favour of ``Boot.BootOrder``.
    * **Boot options are category-level.** On ThinkSystem the ``BootOptions``
      collection holds generic entries (``Network``, ``HardDisk``,
      ``CD_DVDRom``) plus installed OS loaders, with ``VenHw_``-style UEFI
      device paths that encode no MAC address. Individual ports are ranked in
      the OEM ``BootOrder.NetworkBootOrder`` resource instead, whose entries
      name slot, protocol and adapter and — depending on the adapter — the
      MAC. Selecting a NIC by MAC therefore means promoting it there, not in
      the main boot order; see :meth:`set_boot_first_by_mac`.
    * **No per-option boot override.** XCC advertises ``UefiTarget`` — not the
      ``UefiBootNext`` other vendors use — but restricts
      ``UefiTargetBootSourceOverride`` to an undisclosed list of accepted
      values, rejecting both UEFI device paths and ``BootNNNN`` references with
      ``PropertyValueNotInList``; ``BootNext`` is read-only. A specific device
      therefore cannot be named in a one-time override, and network boot to a
      chosen port is done by promoting the port (see
      :meth:`set_network_boot_first_by_mac`) plus a generic ``Pxe`` override.
    * **ETags.** XCC returns weak ETags on the system resource and rejects
      some PATCHes without a matching ``If-Match``. :meth:`_patch` sends the
      current ETag when the BMC provides one and retries with ``If-Match: *``
      if the BMC still answers 412/428.

    Two further traps worth knowing when using this class:

    * A ``2xx`` on a PATCH to ``/Systems/{id}`` does not prove the override
      took: XCC applies each property independently, so a payload whose only
      writable property is incidental succeeds while the override itself is
      dropped. :meth:`set_boot_override` reads the override back and only
      reports success when the BMC agrees.
    * After a PATCH to an OEM ``BootSettings`` member, *that member* answers
      HTTP 500 ("internal service error") for several minutes while the BMC
      digests the change, even though the rest of the service stays healthy.
      Read the order before writing, and expect read-after-write to fail.

    Verified against a ThinkSystem SR685a V3 (XCC 16E-6.10, UEFI R5E122B).
    """

    def __init__(self, fishapi: 'RedfishAPI') -> None:
        """Initialize with a shared RedfishAPI session.

        Args:
            fishapi: An authenticated :class:`~bmctools.redfish.fishapi.RedfishAPI` instance.
        """
        self.api = fishapi
        self.boot_options = None
        self.system_id = self._get_system_id()
        # Cached OEM boot-order member URIs, keyed by category. A cached None
        # means "probed, not present"; an absent key means "not probed yet".
        self._oem_boot_uris = {}


    def _get_system_id(self) -> str:
        """Get the system ID from the Systems collection."""
        response = self.api.get('/redfish/v1/Systems')
        if response.status_code == 200:
            data = response.json()
            members = data.get('Members', [])
            if members and len(members) > 0:
                odata_id = members[0].get('@odata.id', '')
                system_id = odata_id.split('/')[-1]
                return system_id if system_id else '1'
        return '1'


    def _system_uri(self) -> str:
        """Return the Redfish URI for the primary system resource."""
        return f'/redfish/v1/Systems/{self.system_id}'


    def _get_system(self) -> dict:
        """Fetch the system resource.

        Raises:
            ValueError: If the system resource cannot be read.
        """
        response = self.api.get(self._system_uri())
        if response.status_code != 200:
            raise ValueError(f'Failed to get system info, status code: {response.status_code}')
        return response.json()


    def _get_etag(self, endpoint: str) -> Optional[str]:
        """Return the ETag header for an endpoint, or ``None`` if it has none.

        Unlike the AMI-based implementations, a missing ETag is not fatal on
        XCC — many resources accept an unconditional PATCH — so this returns
        ``None`` instead of raising and lets :meth:`_patch` decide.
        """
        response = self.api.get(endpoint)
        if response.status_code != 200:
            return None
        return response.headers.get('ETag')


    def _patch(self, endpoint: str, payload: dict) -> 'requests.Response':
        """PATCH an endpoint, satisfying the ETag precondition when required.

        Sends ``If-Match`` with the resource's current ETag when the BMC
        provides one. If the BMC still rejects the request with 412
        (Precondition Failed) or 428 (Precondition Required) — e.g. the ETag
        changed in between, or none was advertised — it retries once with the
        ``If-Match: *`` wildcard.

        Args:
            endpoint: Redfish endpoint to PATCH.
            payload: JSON body for the PATCH.

        Returns:
            The HTTP response.
        """
        etag = self._get_etag(endpoint)
        headers = {'If-Match': etag} if etag else None
        response = self.api.patch(endpoint, data=payload, headers=headers)
        if response.status_code in [412, 428]:
            response = self.api.patch(endpoint, data=payload, headers={'If-Match': '*'})
        return response


    @staticmethod
    def _error_detail(response: 'requests.Response') -> str:
        """Format a response body for inclusion in an error message."""
        try:
            return f"\nError details: {json.dumps(response.json(), indent=2)}"
        except Exception:
            return f"\nResponse text: {response.text}"


    # ── Boot order ───────────────────────────────────────────────────

    def _oem_boot_order_uri(self, kind: str = 'BootOrder') -> Optional[str]:
        """Return the URI of a Lenovo OEM boot-order resource, if present.

        ``/Systems/{id}/Oem/Lenovo/BootSettings`` holds one member per boot
        category — ``BootOrder.BootOrder`` (the top-level order) plus
        ``BootOrder.NetworkBootOrder``, ``BootOrder.HardDiskBootOrder``,
        ``BootOrder.CDDVDROMBootOrder`` and ``BootOrder.USBBootOrder``, which
        rank the devices *within* a category. Members are selected by name,
        not position, since the collection order is not guaranteed.

        Args:
            kind: Member suffix, e.g. ``'BootOrder'`` or ``'NetworkBootOrder'``.

        Returns:
            The member URI, or ``None`` if the resource is absent. Results are
            cached, including the negative case.
        """
        if kind in self._oem_boot_uris:
            return self._oem_boot_uris[kind]

        self._oem_boot_uris[kind] = None
        response = self.api.get(f'{self._system_uri()}/Oem/Lenovo/BootSettings')
        if response.status_code == 200:
            wanted = f'BootOrder.{kind}'
            for member in response.json().get('Members', []):
                uri = member.get('@odata.id', '')
                if uri.rsplit('/', 1)[-1] == wanted:
                    self._oem_boot_uris[kind] = uri
                    break

        return self._oem_boot_uris[kind]


    def _oem_boot_order(self, kind: str = 'BootOrder') -> dict:
        """Read a Lenovo OEM boot order.

        Args:
            kind: Member suffix, e.g. ``'BootOrder'`` or ``'NetworkBootOrder'``.

        ``BootOrderNext`` is the order staged for the next boot and is the only
        writable list; ``BootOrderCurrent`` is what is in effect now. They
        differ exactly while a change is staged, which makes
        ``BootOrderCurrent`` the value to restore to when reverting.

        Returns:
            Dict with ``uri``, ``order`` (the pending ``BootOrderNext`` list),
            ``current`` (``BootOrderCurrent``) and ``supported``
            (``BootOrderSupported``).

        Raises:
            ValueError: If the resource is absent or unreadable.
        """
        uri = self._oem_boot_order_uri(kind)
        if not uri:
            raise ValueError(
                f'Lenovo OEM BootSettings member BootOrder.{kind} is not available '
                f'on this system'
            )

        response = self.api.get(uri)
        if response.status_code == 500:
            raise ValueError(
                f'{uri} returned HTTP 500. XCC serves the OEM boot settings from UEFI '
                f'and the whole BootSettings sub-tree answers 500 while that sync is '
                f'stuck — for several minutes after any write to it, and for as long as '
                f'the host holds the settings open'
                f'{self._system_status_hint()}. '
                f'The rest of the Redfish service stays healthy meanwhile.'
            )
        if response.status_code != 200:
            raise ValueError(f'Failed to retrieve OEM boot order from {uri}, status code: {response.status_code}')

        data = response.json()
        return {
            'uri': uri,
            'order': data.get('BootOrderNext', []),
            'current': data.get('BootOrderCurrent', []),
            'supported': data.get('BootOrderSupported', []),
        }


    def _system_status_hint(self) -> str:
        """Return a hint naming the host state when it explains a stuck sync."""
        try:
            status = self._get_system().get('Oem', {}).get('Lenovo', {}).get('SystemStatus')
        except ValueError:
            return ''

        if status == 'SystemRunningInSetup':
            return (' — this host reports SystemStatus "SystemRunningInSetup", i.e. it is '
                    'parked in the UEFI setup menu, which holds the boot settings and '
                    'blocks the sync; boot the host out of setup first')
        return f' (host SystemStatus: {status})' if status else ''


    def get_boot_order(self) -> list:
        """Get the current boot order.

        Prefers the standard ``Boot.BootOrder`` array (``BootNNNN``
        references); falls back to the Lenovo OEM ``BootOrderNext`` list of
        device names on firmware that does not expose it.

        Returns:
            List of boot option references, or OEM device names.

        Raises:
            ValueError: If the boot order cannot be retrieved.
        """
        boot_order = self._get_system().get('Boot', {}).get('BootOrder', [])
        if boot_order:
            return boot_order

        oem = self._oem_boot_order()
        if not oem['order']:
            raise ValueError('BootOrder not found in response')
        return oem['order']


    def get_boot_options(self, nocache: bool = False) -> list:
        """Get all available boot options.

        Options are enriched with a ``MACAddress`` field (canonical
        ``XX:XX:XX:XX:XX:XX``) when the ``UefiDevicePath`` encodes one.

        On firmware without a ``BootOptions`` collection this returns an empty
        list — the OEM boot order carries device names only, with no per-option
        resource to read.

        Args:
            nocache: If True, bypass the cache and query the BMC directly.

        Returns:
            List of boot option dictionaries.

        Raises:
            ValueError: If the collection exists but cannot be read.
        """
        if not nocache and self.boot_options is not None:
            return self.boot_options

        response = self.api.get(f'{self._system_uri()}/BootOptions')
        if response.status_code == 404:
            self.boot_options = []
            return self.boot_options
        if response.status_code != 200:
            raise ValueError(f'Failed to retrieve boot options, status code: {response.status_code}')

        boot_options = []
        for member in response.json().get('Members', []):
            option_response = self.api.get(member['@odata.id'])
            if option_response.status_code == 200:
                option_data = option_response.json()
                mac = _mac_from_uefi_device_path(option_data.get('UefiDevicePath', ''))
                if mac:
                    option_data['MACAddress'] = mac
                boot_options.append(option_data)

        self.boot_options = boot_options
        return boot_options


    def get_boot_option_by_mac(self, mac_address: str, type: Optional[str] = None, nocache: bool = False) -> dict:
        """Get a boot option by MAC address.

        Matches the MAC encoded in ``UefiDevicePath``, then falls back to a
        MAC embedded in the option's display name (some XCC builds label
        network entries that way).

        Args:
            mac_address: MAC address to search for.
            type: Optional boot option type to filter by (e.g., 'PXE').
            nocache: If True, force a fresh API call.

        Returns:
            Dict containing the matching boot option data.

        Raises:
            ValueError: If no matching boot option is found.
        """
        target = _canonical_mac(mac_address)
        target_bare = target.replace(':', '')

        for option in self.get_boot_options(nocache=nocache):
            if option.get('MACAddress') != target:
                labels = ' '.join(str(option.get(key, '')) for key in ('DisplayName', 'Name', 'Description'))
                normalized = labels.upper().replace(':', '').replace('-', '')
                if target_bare not in normalized:
                    continue
            if type and option.get('BootOptionType') is not None \
                    and option.get('BootOptionType', '').lower() != type.lower():
                continue
            return option

        raise ValueError(f'No boot option found with MAC address: {mac_address}' + (f' and type: {type}' if type else ''))


    def get_boot_option_by_alias(self, alias: str, nocache: bool = False) -> dict:
        """Get a boot option by its alias / display name (case-insensitive substring match)."""
        alias_lower = alias.lower()

        for option in self.get_boot_options(nocache=nocache):
            display_name = option.get('DisplayName', '').lower()
            name = option.get('Name', '').lower()
            description = option.get('Description', '').lower()
            option_alias = option.get('Alias', '').lower()

            if alias_lower == option_alias or alias_lower in display_name \
                    or alias_lower in name or alias_lower in description:
                return option

        raise ValueError(f'No boot option found with alias: {alias}')


    def set_boot_order(self, boot_order: list) -> dict:
        """Set the boot order.

        Accepts either namespace. ``BootNNNN`` references are validated against
        the standard ``Boot.BootOrder`` array and PATCHed there; anything else
        is treated as Lenovo OEM device names. On firmware that exposes
        ``Boot.BootOrder`` as **read-only** — the case on current ThinkSystem
        XCC, where the OEM resource is the only writable boot order — the
        references are translated to OEM device names and written there
        instead, so callers need not care which mechanism the BMC allows.

        Args:
            boot_order: Ordered list of boot option references (e.g.
                ``['Boot0003', 'Boot0009', ...]``) or Lenovo OEM device names
                (e.g. ``['Network', 'Ubuntu', ...]``).

        Returns:
            Dict with keys: changed, needs_reboot, previous_boot_order,
            boot_order. When references were translated, ``mechanism`` is
            ``'oem'`` and ``oem_boot_order`` holds the device names written.

        Raises:
            ValueError: If validation fails or the PATCH is rejected.
        """
        if not boot_order:
            raise ValueError('Boot order must not be empty')

        standard_order = self._get_system().get('Boot', {}).get('BootOrder', [])
        looks_like_refs = all(BOOT_REF_RE.match(entry) for entry in boot_order)

        if standard_order and looks_like_refs:
            try:
                return self._set_standard_boot_order(boot_order)
            except _BootOrderReadOnly:
                pass

            oem_names = self._oem_names_for_refs(boot_order)
            result = self._set_oem_boot_order(oem_names)
            return {
                **result,
                'mechanism': 'oem',
                'previous_boot_order': standard_order,
                'boot_order': boot_order,
                'oem_boot_order': oem_names,
                'oem_previous_boot_order': result['previous_boot_order'],
            }

        return {**self._set_oem_boot_order(boot_order), 'mechanism': 'oem'}


    def _oem_names_for_refs(self, refs: list) -> list:
        """Translate ``BootNNNN`` references to Lenovo OEM device names.

        Args:
            refs: Boot option references, in the desired order.

        Returns:
            The corresponding OEM device names, in the same order.

        Raises:
            ValueError: If any reference has no counterpart in the OEM device
                list, or two references map to the same device.
        """
        labels = {}
        for option in self.get_boot_options():
            ref = option.get('BootOptionReference')
            if ref:
                labels[ref] = option.get('DisplayName') or option.get('Name') or ''

        oem = self._oem_boot_order()
        candidates = oem['supported'] or oem['order']
        by_normalized = {_normalize_device_name(name): name for name in candidates}

        names, unmatched = [], []
        for ref in refs:
            name = by_normalized.get(_normalize_device_name(labels.get(ref, '')))
            if name is None:
                unmatched.append(f'{ref} ({labels.get(ref, "unknown")!r})')
            else:
                names.append(name)

        if unmatched:
            raise ValueError(
                f'Boot.BootOrder is read-only on this BMC, and these boot options have '
                f'no counterpart in the Lenovo OEM device list: {unmatched}. '
                f'OEM devices: {candidates}'
            )

        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValueError(
                f'Several boot options map to the same OEM device name(s): '
                f'{sorted(duplicates)}. Set the order with OEM device names directly.'
            )

        return names


    def _set_standard_boot_order(self, boot_order: list) -> dict:
        """Set boot order via the standard ``Boot.BootOrder`` array."""
        current_boot_order = self.get_boot_order()

        if len(boot_order) != len(current_boot_order):
            raise ValueError(
                f'Boot order must contain all {len(current_boot_order)} boot options. '
                f'You provided {len(boot_order)}. '
                f'Current boot options: {current_boot_order}'
            )

        current_set = set(current_boot_order)
        new_set = set(boot_order)
        if new_set != current_set:
            missing = current_set - new_set
            extra = new_set - current_set
            error_msg = 'Boot order validation failed.'
            if missing:
                error_msg += f' Missing options: {sorted(missing)}.'
            if extra:
                error_msg += f' Unknown options: {sorted(extra)}.'
            raise ValueError(error_msg)

        if boot_order == current_boot_order:
            return {
                'changed': False,
                'needs_reboot': False,
                'mechanism': 'standard',
                'previous_boot_order': current_boot_order,
                'boot_order': boot_order,
            }

        payload = {"Boot": {"BootOrder": boot_order}}
        response = self._patch(self._system_uri(), payload)
        if response.status_code not in [200, 204]:
            if self._is_read_only_rejection(response, 'BootOrder'):
                raise _BootOrderReadOnly('Boot.BootOrder is read-only on this BMC')
            raise ValueError(
                f'Failed to set boot order, status code: {response.status_code}'
                f'{self._error_detail(response)}'
            )

        self.boot_options = None
        return {
            'changed': True,
            'needs_reboot': True,
            'mechanism': 'standard',
            'previous_boot_order': current_boot_order,
            'boot_order': boot_order,
        }


    @staticmethod
    def _is_read_only_rejection(response: 'requests.Response', property_name: str) -> bool:
        """Check whether a response rejected *property_name* as read-only."""
        try:
            body = json.dumps(response.json())
        except Exception:
            body = response.text or ''
        return 'PropertyNotWritable' in body or (
            'read-only' in body and property_name in body)


    def _set_oem_boot_order(self, boot_order: list) -> dict:
        """Set boot order via the Lenovo OEM ``BootOrderNext`` property."""
        oem = self._oem_boot_order()
        current_boot_order = oem['order']
        supported = oem['supported']

        if len(set(boot_order)) != len(boot_order):
            raise ValueError(f'Boot order contains duplicate entries: {boot_order}')

        if supported:
            unknown = [name for name in boot_order if name not in supported]
            if unknown:
                raise ValueError(
                    f'Unknown boot device names: {unknown}. '
                    f'Supported devices: {supported}'
                )

        if boot_order == current_boot_order:
            return {
                'changed': False,
                'needs_reboot': False,
                'previous_boot_order': current_boot_order,
                'boot_order': boot_order,
            }

        response = self._patch(oem['uri'], {"BootOrderNext": boot_order})
        if response.status_code not in [200, 202, 204]:
            raise ValueError(
                f'Failed to set OEM boot order, status code: {response.status_code}'
                f'{self._error_detail(response)}'
            )

        return {
            'changed': True,
            'needs_reboot': True,
            'previous_boot_order': current_boot_order,
            'boot_order': boot_order,
        }


    # ── Per-NIC network boot order (Lenovo OEM) ──────────────────────

    def get_network_boot_order(self) -> dict:
        """Get the Lenovo per-NIC network boot order.

        On ThinkSystem servers the standard ``BootOptions`` collection is
        category-level — a single generic ``Network`` entry rather than one
        entry per port — so the ranking *between* NICs lives in the OEM
        ``BootOrder.NetworkBootOrder`` resource. Its entries are UEFI boot
        strings that name slot, protocol and adapter, e.g.::

            UEFI:   SLOT 10 (C7/0/0) PXE IPv4  Mellanox ConnectX-6 Dx ... - E8:EB:D3:FD:CD:60

        Returns:
            Dict with ``uri``, ``order`` (pending), ``current`` and ``supported``.

        Raises:
            ValueError: If the system exposes no network boot order.
        """
        return self._oem_boot_order('NetworkBootOrder')


    def find_network_boot_entry(self, mac_address: str, boot_type: str = 'PXE') -> str:
        """Find the network boot entry for a NIC by MAC address.

        Only adapters whose UEFI boot string embeds the MAC can be matched;
        some adapters (e.g. onboard Broadcom OCP ports) are named by slot and
        port only, and must be selected by string instead.

        Args:
            mac_address: MAC address of the target NIC.
            boot_type: Preferred protocol when a NIC has several entries
                (Lenovo lists PXE and HTTP separately). Default 'PXE'.

        Returns:
            The matching network boot entry string.

        Raises:
            ValueError: If no entry names that MAC.
        """
        oem = self.get_network_boot_order()
        entries = oem['order'] or oem['supported']
        target_bare = _canonical_mac(mac_address).replace(':', '')

        matches = [e for e in entries
                   if target_bare in e.upper().replace(':', '').replace('-', '')]
        if not matches:
            raise ValueError(
                f'No network boot entry names MAC {mac_address}. Entries carrying a '
                f'MAC can be matched; the rest must be selected by string. '
                f'Available entries: {entries}'
            )

        if boot_type:
            preferred = [e for e in matches if boot_type.upper() in e.upper()]
            if preferred:
                return preferred[0]

        return matches[0]


    def set_network_boot_first_by_mac(self, mac_address: str, boot_type: str = 'PXE') -> dict:
        """Move a NIC to the front of the Lenovo network boot order.

        This ranks the NIC ahead of the other network devices; whether the
        machine boots from the network at all is still decided by the main boot
        order (or a one-time ``Pxe`` override). The change is persistent and
        applies on the next boot.

        Note that the resource answers HTTP 500 for several minutes after the
        PATCH, so reading the order back to confirm will fail for a while. To
        revert, PATCH ``BootOrderNext`` with the ``BootOrderCurrent`` list.

        Args:
            mac_address: MAC address of the target NIC.
            boot_type: Preferred protocol (default 'PXE').

        Returns:
            Dict with keys: changed, needs_reboot, promoted, mac_address,
            previous_boot_order, boot_order.

        Raises:
            ValueError: If no entry names that MAC, or the PATCH is rejected.
        """
        entry = self.find_network_boot_entry(mac_address, boot_type=boot_type)
        oem = self.get_network_boot_order()
        current_order = oem['order'] or oem['supported']

        new_order = [entry] + [e for e in current_order if e != entry]

        if new_order == current_order:
            return {
                'changed': False,
                'needs_reboot': False,
                'promoted': entry,
                'mac_address': mac_address,
                'previous_boot_order': current_order,
                'boot_order': new_order,
                'message': f'{entry} is already first in the network boot order',
            }

        response = self._patch(oem['uri'], {"BootOrderNext": new_order})
        if response.status_code not in [200, 202, 204]:
            raise ValueError(
                f'Failed to set network boot order, status code: {response.status_code}'
                f'{self._error_detail(response)}'
            )

        return {
            'changed': True,
            'needs_reboot': True,
            'promoted': entry,
            'mac_address': mac_address,
            'previous_boot_order': current_order,
            'boot_order': new_order,
            'message': f'{entry} moved to front of the network boot order',
        }


    def _network_boot_option_ref(self) -> Optional[str]:
        """Return the ``BootNNNN`` reference of the generic network boot option."""
        options = self.get_boot_options()
        for match in (lambda label: label == 'network',
                      lambda label: 'network' in label or 'pxe' in label):
            for option in options:
                label = (option.get('DisplayName') or option.get('Name') or '').lower()
                if match(label):
                    return option.get('BootOptionReference')
        return None


    def set_boot_first_by_mac(self, mac_address: str, boot_type: str = None) -> dict:
        """Make the NIC with the given MAC address boot first.

        Two mechanisms, in order of preference:

        1. If the ``BootOptions`` collection exposes per-NIC entries carrying a
           MAC, the matching ``BootNNNN`` reference is moved to the front of
           the boot order — the same behaviour as the other vendor classes.
        2. Otherwise (the usual case on ThinkSystem, where boot options are
           category-level), the NIC is moved to the front of the OEM network
           boot order *and* the generic network boot option is moved to the
           front of the main boot order. Both are needed: the first decides
           which port, the second decides that a network device is tried first.

        Args:
            mac_address: MAC address of the target NIC.
            boot_type: Optional boot option type / protocol filter (e.g., 'PXE').

        Returns:
            Dict with the new boot order and the promoted entry. In case 2 the
            network-order result is included under ``network_boot_order``.

        Raises:
            ValueError: If the MAC cannot be matched by either mechanism.
        """
        try:
            option = self.get_boot_option_by_mac(mac_address, type=boot_type)
        except ValueError:
            option = None

        if option is None:
            return self._set_boot_first_by_mac_via_network_order(mac_address, boot_type)
        boot_ref = option.get('BootOptionReference')
        if not boot_ref:
            raise ValueError(
                f'Boot option for MAC {mac_address} has no BootOptionReference'
            )

        current_order = self.get_boot_order()

        if boot_ref not in current_order:
            raise ValueError(
                f'{boot_ref} not found in current boot order: {current_order}'
            )

        new_order = [boot_ref] + [b for b in current_order if b != boot_ref]
        result = self.set_boot_order(new_order)

        return {
            'changed': result['changed'],
            'needs_reboot': result['needs_reboot'],
            'promoted': boot_ref,
            'display_name': option.get('DisplayName', ''),
            'mac_address': mac_address,
            'previous_boot_order': result['previous_boot_order'],
            'boot_order': new_order,
            'message': f'{boot_ref} ({option.get("DisplayName", "")}) moved to front of boot order'
                       if result['changed'] else
                       f'{boot_ref} ({option.get("DisplayName", "")}) is already first in boot order'
        }


    def _set_boot_first_by_mac_via_network_order(self, mac_address: str,
                                                boot_type: str = None) -> dict:
        """Promote a NIC in the OEM network boot order, then network-boot first.

        Used when boot options are category-level and carry no MAC, so the NIC
        cannot be named in the main boot order.
        """
        network_result = self.set_network_boot_first_by_mac(
            mac_address, boot_type=boot_type or 'PXE')

        boot_ref = self._network_boot_option_ref()
        if not boot_ref:
            raise ValueError(
                f'{network_result["promoted"]} was moved to the front of the network '
                f'boot order, but no generic network boot option was found to put '
                f'first in the main boot order. Set it manually with set_boot_order(), '
                f'or use set_next_onetime_boot("Pxe") for a one-time network boot.'
            )

        current_order = self.get_boot_order()
        if boot_ref not in current_order:
            raise ValueError(
                f'{boot_ref} not found in current boot order: {current_order}'
            )

        new_order = [boot_ref] + [b for b in current_order if b != boot_ref]
        result = self.set_boot_order(new_order)

        return {
            'changed': result['changed'] or network_result['changed'],
            'needs_reboot': result['needs_reboot'] or network_result['needs_reboot'],
            'promoted': boot_ref,
            'display_name': network_result['promoted'],
            'mac_address': mac_address,
            'previous_boot_order': result['previous_boot_order'],
            'boot_order': new_order,
            'network_boot_order': network_result,
            'message': (
                f'{network_result["promoted"]} moved to front of the network boot order; '
                f'{boot_ref} '
                + ('moved to front of boot order' if result['changed']
                   else 'already first in boot order')
            ),
        }


    # ── Boot source override ─────────────────────────────────────────

    def set_boot_override(self, target: str, enabled: str = 'Once',
                          uefi_target: Optional[str] = None) -> bool:
        """Set boot source override, satisfying the ETag precondition.

        XCC rejects an override whose ``BootSourceOverrideMode`` disagrees
        with the system's current boot mode, so if the plain PATCH is refused
        the override is retried with the mode stated explicitly.

        Args:
            target: Boot source target (e.g., 'Pxe', 'Hdd', 'Cd', 'UefiTarget').
                XCC advertises ``UefiTarget`` — not the ``UefiBootNext`` other
                vendors use — for booting a named UEFI device; both spellings
                are accepted here and resolved against the BMC's allowable
                values.
            enabled: Override mode ('Once', 'Continuous', or 'Disabled').
            uefi_target: UEFI device path, or a ``BootNNNN`` reference whose
                ``UefiDevicePath`` is looked up. Required when target is
                'UefiTarget'/'UefiBootNext'.

        Returns:
            True on success.

        Raises:
            ValueError: If target/uefi_target are inconsistent or the PATCH is rejected.
        """
        if target in ('UefiTarget', 'UefiBootNext'):
            if not uefi_target:
                raise ValueError(f"uefi_target is required when target is '{target}'")
            payloads = self._uefi_target_payloads(uefi_target, enabled)
        else:
            payloads = [{"Boot": {
                "BootSourceOverrideTarget": target,
                "BootSourceOverrideEnabled": enabled,
            }}]

        # Retry every variant with the boot mode stated explicitly.
        boot_mode = self._current_boot_override_mode()
        if boot_mode:
            payloads = payloads + [
                {"Boot": dict(payload["Boot"], BootSourceOverrideMode=boot_mode)}
                for payload in payloads
            ]

        last_response = None
        for payload in payloads:
            response = self._patch(self._system_uri(), payload)
            if response.status_code in [200, 204]:
                # A 2xx is not proof the override took. XCC applies a PATCH
                # property-by-property, so a payload whose only writable
                # property is something incidental (e.g. BootSourceOverrideMode
                # alongside a read-only BootNext) succeeds while the override
                # itself is dropped. Confirm by reading the override back.
                if self._override_applied(payload['Boot'], enabled):
                    return True
                continue
            last_response = response

        if target in ('UefiTarget', 'UefiBootNext'):
            raise ValueError(
                f'This BMC did not accept a boot override targeting {uefi_target!r}. '
                f'XCC restricts UefiTargetBootSourceOverride to an undisclosed list of '
                f'accepted values and rejects both UEFI device paths and BootNNNN '
                f'references, and BootNext is read-only. To network boot a specific '
                f'port, promote it with set_network_boot_first_by_mac() and set a '
                f'generic one-time Pxe override instead.'
                + (f' Last response: {last_response.status_code}'
                   f'{self._error_detail(last_response)}' if last_response else '')
            )

        if last_response is None:
            raise ValueError(
                f'Boot override was accepted but did not take effect: the BMC still '
                f'reports a different BootSourceOverrideTarget than the requested '
                f'{target!r}.'
            )

        raise ValueError(
            f'Failed to set boot override, status code: {last_response.status_code}'
            f'{self._error_detail(last_response)}'
        )


    def _override_applied(self, requested: dict, enabled: str) -> bool:
        """Check that a boot override PATCH actually took effect.

        Args:
            requested: The ``Boot`` sub-object that was PATCHed.
            enabled: The override mode that was requested.

        Returns:
            True if the BMC now reports the requested target and mode.
        """
        try:
            boot = self._get_system().get('Boot', {})
        except ValueError:
            # Can't confirm either way — assume the 2xx meant what it said.
            return True

        target = requested.get('BootSourceOverrideTarget')
        if target is None:
            # BootNext-only payload: confirm the reference landed.
            return boot.get('BootNext') == requested.get('BootNext')

        if boot.get('BootSourceOverrideTarget') != target:
            return False
        if enabled != 'Disabled' and boot.get('BootSourceOverrideEnabled') != enabled:
            return False

        uefi_target = requested.get('UefiTargetBootSourceOverride')
        if uefi_target and boot.get('UefiTargetBootSourceOverride') != uefi_target:
            return False

        return True


    def _uefi_target_payloads(self, uefi_target: str, enabled: str) -> list:
        """Return PATCH payload variants for booting a named UEFI device.

        XCC's ``BootSourceOverrideTarget@Redfish.AllowableValues`` offers
        ``UefiTarget`` (paired with ``UefiTargetBootSourceOverride``, a UEFI
        device path) rather than the ``UefiBootNext``/``BootNext`` pair used by
        other vendors. The advertised value is preferred, with the other
        spellings kept as fallbacks for firmware that differs.

        A ``BootNNNN`` reference is resolved to its ``UefiDevicePath``, since
        ``UefiTargetBootSourceOverride`` takes a device path, not a reference.
        """
        allowable = []
        try:
            allowable = self._get_system().get('Boot', {}).get(
                'BootSourceOverrideTarget@Redfish.AllowableValues', [])
        except ValueError:
            pass

        device_path = uefi_target
        if uefi_target.startswith('Boot'):
            try:
                option = next(o for o in self.get_boot_options()
                              if o.get('BootOptionReference') == uefi_target)
                device_path = option.get('UefiDevicePath') or uefi_target
            except (StopIteration, ValueError):
                pass

        uefi_target_payload = {"Boot": {
            "BootSourceOverrideTarget": "UefiTarget",
            "BootSourceOverrideEnabled": enabled,
            "UefiTargetBootSourceOverride": device_path,
        }}
        boot_next_payloads = [
            {"Boot": {
                "BootSourceOverrideTarget": "UefiBootNext",
                "BootSourceOverrideEnabled": enabled,
                "BootNext": uefi_target,
            }},
            {"Boot": {"BootNext": uefi_target}},
        ]

        if 'UefiBootNext' in allowable and 'UefiTarget' not in allowable:
            return boot_next_payloads + [uefi_target_payload]
        return [uefi_target_payload] + boot_next_payloads


    def _current_boot_override_mode(self) -> Optional[str]:
        """Return the boot override mode to state explicitly on retry.

        Uses the system's current ``BootSourceOverrideMode`` when set,
        otherwise derives it from ``Boot.BootMode`` / ``BootSourceOverrideMode``
        allowable values. Returns ``None`` when nothing can be determined.
        """
        try:
            boot = self._get_system().get('Boot', {})
        except ValueError:
            return None

        mode = boot.get('BootSourceOverrideMode')
        if mode:
            return mode

        allowable = boot.get('BootSourceOverrideMode@Redfish.AllowableValues', [])
        if 'UEFI' in allowable:
            return 'UEFI'
        return None


    def set_next_onetime_boot(self, boot_source: str = 'Pxe',
                              mac_address: Optional[str] = None) -> bool:
        """Set the next one-time boot source on a Lenovo (XCC) system.

        This is the Lenovo entry point into the cross-manufacturer
        network-boot flow. XCC accepts the standard one-time boot source
        override, so network boot needs no OEM call: ``Pxe`` with
        ``BootSourceOverrideEnabled: Once`` is enough, and the choice of port
        falls to the network boot order.

        When *mac_address* is given, the NIC is first moved to the front of the
        OEM network boot order (see :meth:`set_network_boot_first_by_mac`), so
        the one-time PXE boot lands on that port rather than whichever network
        device happens to be ranked first. Note that unlike the override
        itself, promoting the NIC is a persistent change. If the MAC matches no
        network boot entry, the generic override is still set rather than
        failing.

        Args:
            boot_source: Boot source target (default 'Pxe').
            mac_address: Optional MAC address of the NIC to boot from.

        Returns:
            True on success.

        Raises:
            ValueError: If the PATCH is rejected.
        """
        if mac_address:
            try:
                self.set_network_boot_first_by_mac(mac_address)
            except ValueError:
                pass

        return self.set_boot_override(boot_source, enabled='Once')


    # ── BIOS settings ────────────────────────────────────────────────

    def _bios_settings_uri(self) -> str:
        """Return the URI that accepts pending BIOS attribute changes.

        Follows ``@Redfish.Settings`` → ``SettingsObject`` from ``/Bios``,
        which resolves to ``/Bios/Pending`` on XCC, and falls back to the
        conventional ``/Bios/Settings`` when the annotation is absent.
        """
        response = self.api.get(f'{self._system_uri()}/Bios')
        if response.status_code == 200:
            settings = response.json().get('@Redfish.Settings', {})
            uri = settings.get('SettingsObject', {}).get('@odata.id')
            if uri:
                return uri
        return f'{self._system_uri()}/Bios/Settings'


    def get_bios_settings(self) -> dict:
        """Get current BIOS attributes.

        Returns:
            Dict with ``attributes``, ``id`` and ``description``.

        Raises:
            ValueError: If the BIOS resource cannot be read.
        """
        response = self.api.get(f'{self._system_uri()}/Bios')
        if response.status_code != 200:
            raise ValueError(f'Failed to get BIOS settings, status code: {response.status_code}')

        data = response.json()
        return {
            'attributes': data.get('Attributes', {}),
            'id': data.get('Id'),
            'description': data.get('Description'),
        }


    def set_bios_settings(self, attributes: dict) -> bool:
        """Stage BIOS attributes on the pending-settings resource.

        Args:
            attributes: Dict of BIOS attribute key/value pairs to set.

        Returns:
            True if the settings were accepted (applied on next reboot).

        Raises:
            ValueError: If the PATCH is rejected.
        """
        settings_uri = self._bios_settings_uri()
        response = self._patch(settings_uri, {"Attributes": attributes})
        if response.status_code in [200, 202, 204]:
            return True

        raise ValueError(
            f'Failed to set BIOS settings, status code: {response.status_code}'
            f'{self._error_detail(response)}'
        )


    # ── System Reset ─────────────────────────────────────────────────

    def get_supported_reset_types(self) -> dict:
        """Get supported reset types from the ComputerSystem.Reset action."""
        data = self._get_system()
        actions = data.get('Actions', {})

        reset_action = (actions.get('#ComputerSystem.Reset') or
                        actions.get('ComputerSystem.Reset') or
                        {})

        allowed_values = (reset_action.get('ResetType@Redfish.AllowableValues') or
                          reset_action.get('AllowableValues') or
                          [])

        if not allowed_values:
            action_info_uri = reset_action.get('@Redfish.ActionInfo')
            if action_info_uri:
                allowed_values = self._get_action_info_allowable_values(action_info_uri)

        return {
            'types': allowed_values,
            'actions': actions,
            'reset_action': reset_action
        }


    def reset_system(self, reset_type: str = None) -> bool:
        """Reset the system.

        Args:
            reset_type: Optional Redfish reset type. When None, one is chosen
                from the supported types.

        Returns:
            True on success.

        Raises:
            ValueError: If the reset request fails.
        """
        if reset_type is None:
            reset_type = self._pick_reset_type(self.get_supported_reset_types()['types'],
                                               default='ForceRestart')

        response = self.api.post(f'{self._system_uri()}/Actions/ComputerSystem.Reset',
                                 data={"ResetType": reset_type})
        if response.status_code in [200, 202, 204]:
            return True

        raise ValueError(
            f'Failed to reset system, status code: {response.status_code}'
            f'{self._error_detail(response)}'
        )


    @staticmethod
    def _pick_reset_type(supported_types: list, default: str) -> str:
        """Choose a reset type, preferring a graceful restart."""
        if not supported_types:
            return default
        if 'GracefulRestart' in supported_types:
            return 'GracefulRestart'
        if 'ForceRestart' in supported_types:
            return 'ForceRestart'
        return supported_types[0]


    # ── Firmware Inventory ───────────────────────────────────────────

    def get_firmware_inventory(self) -> dict:
        """Get firmware inventory for installed components."""
        response = self.api.get('/redfish/v1/UpdateService/FirmwareInventory')
        if response.status_code != 200:
            raise ValueError(f'Failed to get firmware inventory, status code: {response.status_code}')

        firmware_list = []
        for member in response.json().get('Members', []):
            member_url = member.get('@odata.id')
            if not member_url:
                continue
            try:
                fw_resp = self.api.get(member_url)
                if fw_resp.status_code == 200:
                    fw_data = fw_resp.json()
                    firmware_list.append({
                        'Id': fw_data.get('Id'),
                        'Name': fw_data.get('Name'),
                        'Version': fw_data.get('Version'),
                        'Updateable': fw_data.get('Updateable'),
                        'Status': fw_data.get('Status', {})
                    })
            except Exception:
                continue

        return {
            'firmware_count': len(firmware_list),
            'firmware': firmware_list
        }


    # ── Network Interfaces ───────────────────────────────────────────

    def get_network_interfaces(self) -> list:
        """Get Ethernet interfaces for the system."""
        response = self.api.get(f'{self._system_uri()}/EthernetInterfaces')
        if response.status_code != 200:
            raise ValueError(f'Failed to retrieve EthernetInterfaces, status code: {response.status_code}')

        interfaces = []
        for member in response.json().get('Members', []):
            iface_resp = self.api.get(member['@odata.id'])
            if iface_resp.status_code == 200:
                interfaces.append(iface_resp.json())

        return interfaces


    # ── BMC (Manager) Reset ──────────────────────────────────────────

    def _get_manager_id(self) -> str:
        """Get the Manager ID from the Managers collection."""
        response = self.api.get('/redfish/v1/Managers')
        if response.status_code == 200:
            members = response.json().get('Members', [])
            if members:
                odata_id = members[0].get('@odata.id', '')
                return odata_id.split('/')[-1] or '1'
        return '1'


    def get_supported_bmc_reset_types(self) -> dict:
        """Get supported reset types for the BMC (Manager)."""
        manager_id = self._get_manager_id()
        response = self.api.get(f'/redfish/v1/Managers/{manager_id}')
        if response.status_code != 200:
            raise ValueError(f'Failed to get Manager info, status code: {response.status_code}')

        data = response.json()
        actions = data.get('Actions', {})

        reset_action = (actions.get('#Manager.Reset') or
                        actions.get('Manager.Reset') or
                        {})

        allowed_values = (reset_action.get('ResetType@Redfish.AllowableValues') or
                          reset_action.get('AllowableValues') or
                          [])

        if not allowed_values:
            action_info_uri = reset_action.get('@Redfish.ActionInfo')
            if action_info_uri:
                allowed_values = self._get_action_info_allowable_values(action_info_uri)

        return {
            'manager_id': manager_id,
            'types': allowed_values,
            'actions': actions,
            'reset_action': reset_action
        }


    def _get_action_info_allowable_values(self, action_info_uri: str) -> list:
        """Fetch allowable values from a Redfish ActionInfo endpoint."""
        response = self.api.get(action_info_uri)
        if response.status_code == 200:
            data = response.json()
            for param in data.get('Parameters', []):
                if param.get('Name') == 'ResetType':
                    return param.get('AllowableValues', [])
        return []


    def reset_bmc(self, reset_type: str = None) -> bool:
        """Reset the BMC (Manager)."""
        manager_id = self._get_manager_id()

        if reset_type is None:
            reset_type = self._pick_reset_type(self.get_supported_bmc_reset_types()['types'],
                                               default='GracefulRestart')

        response = self.api.post(f'/redfish/v1/Managers/{manager_id}/Actions/Manager.Reset',
                                 data={"ResetType": reset_type})
        if response.status_code in [200, 202, 204]:
            return True

        raise ValueError(
            f'Failed to reset BMC, status code: {response.status_code}'
            f'{self._error_detail(response)}'
        )
