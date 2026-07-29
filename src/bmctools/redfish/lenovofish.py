import json
from typing import Optional
from bmctools.redfish.fishapi import RedfishAPI


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
    Two firmware-dependent quirks drive the shape of this class:

    * **Boot order.** Recent XCC firmware exposes the standard
      ``Boot.BootOrder`` array plus a ``BootOptions`` collection, and boot
      order is set by PATCHing ``BootOrder`` with ``BootNNNN`` references.
      Older firmware exposes neither, and boot order lives in the Lenovo OEM
      resource ``/Systems/{id}/Oem/Lenovo/BootSettings`` as ``BootOrderNext``
      — a list of human-readable device names drawn from
      ``BootOrderSupported``. Every boot-order method here probes the standard
      properties first and falls back to the OEM resource.
    * **ETags.** XCC returns ETags on the system resource and rejects some
      PATCHes without a matching ``If-Match``. :meth:`_patch` sends the
      current ETag when the BMC provides one and retries with ``If-Match: *``
      if the BMC still answers 412/428.
    """

    def __init__(self, fishapi: 'RedfishAPI') -> None:
        """Initialize with a shared RedfishAPI session.

        Args:
            fishapi: An authenticated :class:`~bmctools.redfish.fishapi.RedfishAPI` instance.
        """
        self.api = fishapi
        self.boot_options = None
        self.system_id = self._get_system_id()
        # Cached OEM boot-order member URI. False means "probed, not present";
        # None means "not probed yet".
        self._oem_boot_uri = None


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

    def _oem_boot_order_uri(self) -> Optional[str]:
        """Return the URI of the Lenovo OEM boot-order resource, if present.

        Looks up ``/Systems/{id}/Oem/Lenovo/BootSettings`` and returns the
        first member (``BootOrder.BootOrder`` on the firmware that exposes
        it).  Result is cached, including the negative case.
        """
        if self._oem_boot_uri is not None:
            return self._oem_boot_uri or None

        self._oem_boot_uri = False
        response = self.api.get(f'{self._system_uri()}/Oem/Lenovo/BootSettings')
        if response.status_code == 200:
            members = response.json().get('Members', [])
            if members:
                uri = members[0].get('@odata.id')
                if uri:
                    self._oem_boot_uri = uri

        return self._oem_boot_uri or None


    def _oem_boot_order(self) -> dict:
        """Read the Lenovo OEM boot order.

        Returns:
            Dict with ``uri``, ``order`` (current ``BootOrderNext`` list) and
            ``supported`` (``BootOrderSupported`` list).

        Raises:
            ValueError: If the OEM boot-order resource is absent or unreadable.
        """
        uri = self._oem_boot_order_uri()
        if not uri:
            raise ValueError(
                'Boot order not available: the system exposes neither Boot.BootOrder '
                'nor the Lenovo OEM BootSettings resource'
            )

        response = self.api.get(uri)
        if response.status_code != 200:
            raise ValueError(f'Failed to retrieve OEM boot order from {uri}, status code: {response.status_code}')

        data = response.json()
        return {
            'uri': uri,
            'order': data.get('BootOrderNext', []),
            'supported': data.get('BootOrderSupported', []),
        }


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

        Uses the standard ``Boot.BootOrder`` array when the system exposes
        one, and the Lenovo OEM ``BootOrderNext`` list otherwise. The two
        namespaces are not interchangeable: the standard path expects
        ``BootNNNN`` references and requires the full set of existing options,
        while the OEM path expects device names from ``BootOrderSupported``.

        Args:
            boot_order: Ordered list of boot option references (standard) or
                device names (OEM).

        Returns:
            Dict with keys: changed, needs_reboot, previous_boot_order, boot_order.

        Raises:
            ValueError: If validation fails or the PATCH is rejected.
        """
        if not boot_order:
            raise ValueError('Boot order must not be empty')

        if self._get_system().get('Boot', {}).get('BootOrder', []):
            return self._set_standard_boot_order(boot_order)
        return self._set_oem_boot_order(boot_order)


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
                'previous_boot_order': current_boot_order,
                'boot_order': boot_order,
            }

        payload = {"Boot": {"BootOrder": boot_order}}
        response = self._patch(self._system_uri(), payload)
        if response.status_code not in [200, 204]:
            raise ValueError(
                f'Failed to set boot order, status code: {response.status_code}'
                f'{self._error_detail(response)}'
            )

        self.boot_options = None
        return {
            'changed': True,
            'needs_reboot': True,
            'previous_boot_order': current_boot_order,
            'boot_order': boot_order,
        }


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


    def set_boot_first_by_mac(self, mac_address: str, boot_type: str = None) -> dict:
        """Move the boot option matching a MAC address to the front of the boot order.

        Requires the standard ``BootOptions`` collection: the OEM boot order
        carries device names with no MAC information, so a NIC cannot be
        identified there.

        Args:
            mac_address: MAC address of the target NIC.
            boot_type: Optional boot option type filter (e.g., 'PXE').

        Returns:
            Dict with the new boot order and the promoted option.

        Raises:
            ValueError: If no matching boot option exists, or the system has no
                standard boot order to reorder by reference.
        """
        if not self.get_boot_options():
            raise ValueError(
                'This system exposes no BootOptions collection, so a boot option '
                'cannot be resolved from a MAC address. Set the boot order by device '
                'name with set_boot_order(), or use set_next_onetime_boot("Pxe") for '
                'a one-time network boot.'
            )

        option = self.get_boot_option_by_mac(mac_address, type=boot_type)
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


    # ── Boot source override ─────────────────────────────────────────

    def set_boot_override(self, target: str, enabled: str = 'Once',
                          uefi_target: Optional[str] = None) -> bool:
        """Set boot source override, satisfying the ETag precondition.

        XCC rejects an override whose ``BootSourceOverrideMode`` disagrees
        with the system's current boot mode, so if the plain PATCH is refused
        the override is retried with the mode stated explicitly.

        Args:
            target: Boot source target (e.g., 'Pxe', 'Hdd', 'Cd', 'UefiBootNext').
            enabled: Override mode ('Once', 'Continuous', or 'Disabled').
            uefi_target: UEFI boot option reference (required when target is 'UefiBootNext').

        Returns:
            True on success.

        Raises:
            ValueError: If target/uefi_target are inconsistent or the PATCH is rejected.
        """
        if target == 'UefiBootNext' and not uefi_target:
            raise ValueError("uefi_target is required when target is 'UefiBootNext'")

        if target == 'UefiBootNext':
            payloads = [
                {"Boot": {
                    "BootSourceOverrideTarget": "UefiBootNext",
                    "BootSourceOverrideEnabled": enabled,
                    "UefiTargetBootSourceOverride": uefi_target,
                }},
                {"Boot": {
                    "BootSourceOverrideTarget": "UefiBootNext",
                    "BootSourceOverrideEnabled": enabled,
                    "BootNext": uefi_target,
                }},
                {"Boot": {"BootNext": uefi_target}},
            ]
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
                return True
            last_response = response

        raise ValueError(
            f'Failed to set boot override, status code: {last_response.status_code}'
            f'{self._error_detail(last_response)}'
        )


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
        ``BootSourceOverrideEnabled: Once`` is enough, and NIC selection falls
        to the BIOS boot order.

        When *mac_address* is given and the system exposes a ``BootOptions``
        collection, the specific NIC is targeted via ``UefiBootNext`` instead,
        so the machine boots that port rather than whichever network device
        the BIOS ranks first. If the MAC cannot be resolved to a boot option,
        this falls back to the generic override rather than failing.

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
                option = self.get_boot_option_by_mac(mac_address)
                boot_ref = option.get('BootOptionReference')
            except ValueError:
                boot_ref = None

            if boot_ref:
                return self.set_boot_override('UefiBootNext', enabled='Once',
                                              uefi_target=boot_ref)

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
