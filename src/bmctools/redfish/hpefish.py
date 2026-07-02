import json
from typing import Optional
from bmctools.redfish.fishapi import RedfishAPI


def _canonical_mac(mac: str) -> str:
    """Normalize a MAC to canonical ``XX:XX:XX:XX:XX:XX`` (upper, colon-separated)."""
    hex_only = mac.replace(':', '').replace('-', '').upper()
    return ':'.join(hex_only[i:i + 2] for i in range(0, len(hex_only), 2))


def _mac_from_uefi_device_path(uefi_path: str) -> Optional[str]:
    """Extract a MAC encoded as ``/MAC(xxxxxxxxxxxx,...)`` from a UefiDevicePath.

    Returns the canonical MAC string, or ``None`` if not present.
    """
    if not uefi_path:
        return None
    marker = '/MAC('
    idx = uefi_path.find(marker)
    if idx == -1:
        return None
    mac_start = idx + len(marker)
    mac_end = uefi_path.find(',', mac_start)
    if mac_end == -1:
        mac_end = uefi_path.find(')', mac_start)
    if mac_end <= mac_start:
        return None
    token = uefi_path[mac_start:mac_end]
    if len(token.replace(':', '').replace('-', '')) != 12:
        return None
    return _canonical_mac(token)


def _mac_from_display_name(display_name: str) -> Optional[str]:
    """Extract a MAC encoded as ``(MAC:xxxxxxxxxxxx)`` from a BootOption DisplayName.

    Returns the canonical MAC string, or ``None`` if not present.
    """
    if not display_name:
        return None
    marker = '(MAC:'
    idx = display_name.find(marker)
    if idx == -1:
        return None
    mac_start = idx + len(marker)
    mac_end = display_name.find(')', mac_start)
    if mac_end <= mac_start:
        return None
    token = display_name[mac_start:mac_end]
    if len(token.replace(':', '').replace('-', '')) != 12:
        return None
    return _canonical_mac(token)


def _mac_from_boot_option(option: dict) -> Optional[str]:
    """Best-effort extract of a canonical MAC from a BootOption resource.

    Checks ``UefiDevicePath`` (``/MAC(...)``) then ``DisplayName`` (``(MAC:...)``).
    """
    return (_mac_from_uefi_device_path(option.get('UefiDevicePath', ''))
            or _mac_from_display_name(option.get('DisplayName', '')))


class HpeFish:
    """
    HPE Redfish implementation.

    Targets HPE servers running the AMI Redfish stack (e.g. HPE Cray XD670,
    which reports ``Manufacturer: HPE`` but a ``Vendor: AMI`` / ``Oem.Gbt``
    service root and a system id of ``Self``).  Structurally this behaves like
    the Gigabyte/AMI BMC: ``Boot.BootOrder`` on the system resource, a
    ``/BootOptions`` collection, and standard ``ComputerSystem.Reset``.

    The key difference: the ComputerSystem advertises ``@Redfish.Settings``
    (a SettingsObject, typically ``/redfish/v1/Systems/Self/SD``).  Boot-order
    changes are PATCHed to that settings object, not the live resource.
    """
    def __init__(self, fishapi: 'RedfishAPI') -> None:
        """Initialize with a shared RedfishAPI session.

        Args:
            fishapi: An authenticated :class:`~bmctools.redfish.fishapi.RedfishAPI` instance.
        """
        self.api = fishapi
        self.boot_options = None
        self.system_id = self._get_system_id()


    def _get_system_id(self) -> str:
        """Get the system ID of the primary compute system (e.g. ``'Self'``).

        Some HPE platforms (e.g. the Cray XD670, an 8-GPU HGX box) expose more
        than one ComputerSystem — the GPU baseboard(s) alongside the host — and
        the baseboard can sort first in the collection while carrying no
        ``Boot.BootOrder``.  When multiple systems are present, prefer the one
        that actually exposes a boot order; otherwise fall back to a
        conventionally-named primary system, then the first member.
        """
        response = self.api.get('/redfish/v1/Systems')
        if response.status_code != 200:
            return 'Self'

        members = response.json().get('Members', [])
        ids = [m.get('@odata.id', '').rstrip('/').split('/')[-1] for m in members]
        ids = [i for i in ids if i]
        if not ids:
            return 'Self'
        if len(ids) == 1:
            return ids[0]

        # Multiple systems: pick the one that has a populated boot order.
        for sid in ids:
            resp = self.api.get(f'/redfish/v1/Systems/{sid}')
            if resp.status_code == 200 and resp.json().get('Boot', {}).get('BootOrder'):
                return sid

        # No boot order anywhere (e.g. powered off): prefer a known primary name.
        for preferred in ('Self', '1', 'System.Embedded.1', 'system'):
            if preferred in ids:
                return preferred
        return ids[0]


    def _system_uri(self) -> str:
        """Return the Redfish URI for the primary system resource."""
        return f'/redfish/v1/Systems/{self.system_id}'


    def _settings_uri(self) -> str:
        """Return the URI of the ComputerSystem settings object (@Redfish.Settings).

        Falls back to ``{system_uri}/SD`` when the annotation is absent.
        """
        response = self.api.get(self._system_uri())
        if response.status_code == 200:
            data = response.json()
            settings_obj = data.get('@Redfish.Settings', {}).get('SettingsObject', {})
            uri = settings_obj.get('@odata.id')
            if uri:
                return uri
        return f'{self._system_uri()}/SD'


    def _get_etag(self, endpoint: str) -> Optional[str]:
        """Retrieve the ETag header from an endpoint for If-Match precondition.

        Returns the ETag string, or ``None`` if the endpoint has none (some
        AMI settings objects do not require/emit one).

        Raises:
            ValueError: If the endpoint cannot be read.
        """
        response = self.api.get(endpoint)
        if response.status_code != 200:
            raise ValueError(f'Failed to get ETag from {endpoint}, status code: {response.status_code}')
        return response.headers.get('ETag')


    def get_boot_order(self) -> list:
        """Get the current boot order from the HPE system.

        Returns:
            List of boot option references in order.

        Raises:
            ValueError: If the boot order cannot be retrieved.
        """
        response = self.api.get(self._system_uri())
        if response.status_code == 200:
            data = response.json()
            boot_order = data.get('Boot', {}).get('BootOrder', [])
            if not boot_order:
                raise ValueError("BootOrder not found in response")
            return boot_order
        else:
            raise ValueError(f'Failed to retrieve boot order, status code: {response.status_code}')


    def get_boot_options(self, nocache: bool = False) -> list:
        """Get all available boot options.

        Each option is enriched with a ``MACAddress`` field (canonical
        ``XX:XX:XX:XX:XX:XX``) when a MAC can be derived from its
        ``UefiDevicePath`` or ``DisplayName``.

        Args:
            nocache: If True, bypass the cache and query the BMC directly.

        Returns:
            List of boot option dictionaries.

        Raises:
            ValueError: If boot options cannot be retrieved.
        """
        if not nocache and self.boot_options is not None:
            return self.boot_options

        response = self.api.get(f'{self._system_uri()}/BootOptions')
        if response.status_code == 200:
            data = response.json()
            members = data.get('Members', [])
            boot_options = []
            for member in members:
                option_response = self.api.get(member['@odata.id'])
                if option_response.status_code == 200:
                    option_data = option_response.json()
                    mac = _mac_from_boot_option(option_data)
                    if mac:
                        option_data['MACAddress'] = mac
                    boot_options.append(option_data)

            self.boot_options = boot_options
            return boot_options
        else:
            raise ValueError(f'Failed to retrieve boot options, status code: {response.status_code}')


    def get_boot_option_by_mac(self, mac_address: str, type: Optional[str] = None, nocache: bool = False) -> dict:
        """Get a boot option by MAC address.

        Matches against the MAC derived from ``UefiDevicePath`` or
        ``DisplayName`` (see :func:`_mac_from_boot_option`).  When
        ``BootOptionType`` is populated it is honored as a filter; otherwise
        ``type`` is matched as a substring of ``DisplayName``.

        Args:
            mac_address: MAC address (format: ``XX:XX:XX:XX:XX:XX`` or ``XXXXXXXXXXXX``).
            type: Optional boot option type filter (e.g., ``'PXE'``).
            nocache: If True, force a fresh API call instead of using cached boot options.

        Returns:
            Dict containing the matching boot option data.

        Raises:
            ValueError: If no matching boot option is found.
        """
        target = _canonical_mac(mac_address)

        for option in self.get_boot_options(nocache=nocache):
            if option.get('MACAddress') != target:
                continue
            if type:
                boot_type = option.get('BootOptionType')
                if boot_type is not None:
                    if boot_type.lower() != type.lower():
                        continue
                elif type.lower() not in option.get('DisplayName', '').lower():
                    continue
            return option

        raise ValueError(
            f'No boot option found with MAC address: {mac_address}'
            + (f' and type: {type}' if type else '')
        )


    def get_boot_option_by_alias(self, alias: str, nocache: bool = False) -> dict:
        """Get a boot option by its alias/name.

        Args:
            alias: Boot option alias to search for (case-insensitive).
            nocache: If True, force a fresh API call instead of using cached boot options.

        Returns:
            Dict containing the matching boot option data.

        Raises:
            ValueError: If no boot option is found with the specified alias.
        """
        for option in self.get_boot_options(nocache=nocache):
            if option.get('Alias', '').lower() == alias.lower():
                return option

        raise ValueError(f'No boot option found with alias: {alias}')


    def set_boot_order(self, boot_order: list) -> dict:
        """Set the boot order for the system via the @Redfish.Settings object.

        Args:
            boot_order: Ordered list of boot option references
                (e.g., ``['Boot0004', 'Boot0005', ...]``). Must include ALL
                existing boot options — no additions or omissions.

        Returns:
            Dict with keys: changed, needs_reboot, previous_boot_order, boot_order.

        Raises:
            ValueError: If *boot_order* does not match the current set of options,
                or if the PATCH request fails.
        """
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

        # Skip PATCH if the order is already correct
        if boot_order == current_boot_order:
            return {
                'changed': False,
                'needs_reboot': False,
                'previous_boot_order': current_boot_order,
                'boot_order': boot_order,
            }

        payload = {
            "Boot": {
                "BootOrder": boot_order
            }
        }

        # AMI-based HPE BMCs apply boot-order changes through the settings
        # object (@Redfish.Settings), not the live ComputerSystem resource.
        settings_uri = self._settings_uri()
        headers = {}
        etag = self._get_etag(settings_uri)
        if etag:
            headers['If-Match'] = etag

        response = self.api.patch(settings_uri, data=payload, headers=headers)
        if response.status_code in [200, 202, 204]:
            return {
                'changed': True,
                'needs_reboot': True,
                'previous_boot_order': current_boot_order,
                'boot_order': boot_order,
            }
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to set boot order, status code: {response.status_code}{error_detail}')


    def set_boot_first_by_mac(self, mac_address: str, boot_type: str = None) -> dict:
        """Move the boot option matching a MAC address to the front of the boot order.

        Args:
            mac_address: MAC address of the target NIC
            boot_type: Optional boot option type filter (e.g., 'PXE')

        Returns:
            Dict with the new boot order and the promoted option

        Raises:
            ValueError: If no matching boot option or set fails
        """
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


    def get_supported_reset_types(self) -> dict:
        """Get the reset types supported by this system.

        Returns:
            Dict with keys ``'types'`` (list of allowable reset type strings),
            ``'actions'`` (raw Actions dict), and ``'reset_action'`` (the
            ComputerSystem.Reset action dict).

        Raises:
            ValueError: If the system resource cannot be read.
        """
        response = self.api.get(self._system_uri())
        if response.status_code == 200:
            data = response.json()
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
        else:
            raise ValueError(f'Failed to get system info, status code: {response.status_code}')


    def reset_system(self, reset_type: str = None) -> bool:
        """Reset the system.

        Args:
            reset_type: Optional Redfish reset type (e.g., ``'GracefulRestart'``,
                ``'ForceRestart'``).  When ``None``, the type is chosen
                automatically from the supported reset types.

        Returns:
            ``True`` on success.

        Raises:
            ValueError: If the reset request fails.
        """
        if reset_type is None:
            reset_info = self.get_supported_reset_types()
            supported_types = reset_info['types']

            if not supported_types:
                reset_type = 'ForceRestart'
            else:
                if 'GracefulRestart' in supported_types:
                    reset_type = 'GracefulRestart'
                elif 'ForceRestart' in supported_types:
                    reset_type = 'ForceRestart'
                else:
                    reset_type = supported_types[0]

        payload = {"ResetType": reset_type}

        response = self.api.post(f'{self._system_uri()}/Actions/ComputerSystem.Reset', data=payload)
        if response.status_code in [200, 202, 204]:
            return True
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to reset system, status code: {response.status_code}{error_detail}')


    def get_firmware_inventory(self) -> dict:
        """Get the firmware inventory for all installed components.

        Returns:
            Dict with ``'firmware_count'`` (int) and ``'firmware'`` (list of
            dicts containing Id, Name, Version, Updateable, and Status).

        Raises:
            ValueError: If the firmware inventory endpoint cannot be read.
        """
        response = self.api.get('/redfish/v1/UpdateService/FirmwareInventory')
        if response.status_code == 200:
            data = response.json()
            members = data.get('Members', [])

            firmware_list = []
            for member in members:
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
        else:
            raise ValueError(f'Failed to get firmware inventory, status code: {response.status_code}')


    def get_network_interfaces(self) -> list:
        """Get all Ethernet interfaces for the system.

        Returns:
            List of dicts, one per EthernetInterface resource.

        Raises:
            ValueError: If the EthernetInterfaces collection cannot be read.
        """
        response = self.api.get(f'{self._system_uri()}/EthernetInterfaces')
        if response.status_code != 200:
            raise ValueError(f'Failed to retrieve EthernetInterfaces, status code: {response.status_code}')

        data = response.json()
        members = data.get('Members', [])
        interfaces = []
        for member in members:
            iface_resp = self.api.get(member['@odata.id'])
            if iface_resp.status_code == 200:
                interfaces.append(iface_resp.json())

        return interfaces


    # ── BMC (Manager) Reset ──────────────────────────────────────────

    def _get_manager_id(self) -> str:
        """Get the Manager ID from the Managers collection.

        Returns:
            Manager ID string.
        """
        response = self.api.get('/redfish/v1/Managers')
        if response.status_code == 200:
            data = response.json()
            members = data.get('Members', [])
            if members:
                odata_id = members[0].get('@odata.id', '')
                return odata_id.split('/')[-1] or 'Self'
        return 'Self'

    def get_supported_bmc_reset_types(self) -> dict:
        """Get the list of supported reset types for the BMC (Manager).

        Returns:
            Dict with 'manager_id', 'types' (list of allowed types), 'actions'
            (raw Actions dict), and 'reset_action' (the Manager.Reset action dict).
        """
        manager_id = self._get_manager_id()
        response = self.api.get(f'/redfish/v1/Managers/{manager_id}')
        if response.status_code == 200:
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
        else:
            raise ValueError(f'Failed to get Manager info, status code: {response.status_code}')

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
        """Reset the BMC (Manager).

        Args:
            reset_type: Type of reset (e.g., 'GracefulRestart', 'ForceRestart').
                If None, will auto-select from supported types.

        Returns:
            True if reset command was accepted.
        """
        manager_id = self._get_manager_id()

        if reset_type is None:
            reset_info = self.get_supported_bmc_reset_types()
            supported_types = reset_info['types']

            if not supported_types:
                reset_type = 'GracefulRestart'
            else:
                if 'GracefulRestart' in supported_types:
                    reset_type = 'GracefulRestart'
                elif 'ForceRestart' in supported_types:
                    reset_type = 'ForceRestart'
                else:
                    reset_type = supported_types[0]

        payload = {"ResetType": reset_type}

        response = self.api.post(f'/redfish/v1/Managers/{manager_id}/Actions/Manager.Reset', data=payload)
        if response.status_code in [200, 202, 204]:
            return True
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to reset BMC, status code: {response.status_code}{error_detail}')
