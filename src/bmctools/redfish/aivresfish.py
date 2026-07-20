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


class AivresFish:
    """
    Aivres (formerly Inspur) Redfish implementation.

    Aivres BMCs require an ``If-Match`` ETag header on PATCH requests to
    /Systems/{id}; without it the BMC returns HTTP 428 Precondition Required.
    This class fetches the ETag before each PATCH.
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


    def _get_etag(self, endpoint: str) -> str:
        """Retrieve the ETag header from an endpoint for If-Match precondition.

        Args:
            endpoint: The Redfish endpoint to query.

        Returns:
            The ETag header string.

        Raises:
            ValueError: If the endpoint cannot be read or the ETag header is missing.
        """
        response = self.api.get(endpoint)
        if response.status_code != 200:
            raise ValueError(f'Failed to get ETag from {endpoint}, status code: {response.status_code}')

        etag = response.headers.get('ETag')
        if not etag:
            raise ValueError(f'ETag header not found in response from {endpoint}')

        return etag


    def _patch_with_etag(self, endpoint: str, payload: dict) -> 'requests.Response':
        """PATCH an endpoint with an ETag-derived If-Match header.

        Args:
            endpoint: Redfish endpoint to PATCH.
            payload: JSON body for the PATCH.

        Returns:
            The HTTP response.
        """
        etag = self._get_etag(endpoint)
        headers = {'If-Match': etag}
        return self.api.patch(endpoint, data=payload, headers=headers)


    def get_boot_order(self) -> list:
        """Get the current boot order from the Aivres system.

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

        Options are enriched with a ``MACAddress`` field (canonical
        ``XX:XX:XX:XX:XX:XX``) when the ``UefiDevicePath`` encodes one.

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
                    mac = _mac_from_uefi_device_path(option_data.get('UefiDevicePath', ''))
                    if mac:
                        option_data['MACAddress'] = mac
                    boot_options.append(option_data)

            self.boot_options = boot_options
            return boot_options
        else:
            raise ValueError(f'Failed to retrieve boot options, status code: {response.status_code}')


    def get_boot_option_by_mac(self, mac_address: str, type: Optional[str] = None, nocache: bool = False) -> dict:
        """Get a boot option by MAC address.

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

        for option in self.get_boot_options(nocache=nocache):
            if option.get('MACAddress') != target:
                continue
            if type and option.get('BootOptionType') is not None \
                    and option.get('BootOptionType', '').lower() != type.lower():
                continue
            return option

        raise ValueError(f'No boot option found with MAC address: {mac_address}' + (f' and type: {type}' if type else ''))


    def get_boot_option_by_alias(self, alias: str, nocache: bool = False) -> dict:
        """Get a boot option by its alias / display name (case-insensitive substring match)."""
        boot_options = self.get_boot_options(nocache=nocache)
        alias_lower = alias.lower()

        for option in boot_options:
            display_name = option.get('DisplayName', '').lower()
            name = option.get('Name', '').lower()
            description = option.get('Description', '').lower()
            option_alias = option.get('Alias', '').lower()

            if alias_lower == option_alias or alias_lower in display_name \
                    or alias_lower in name or alias_lower in description:
                return option

        raise ValueError(f'No boot option found with alias: {alias}')


    def set_boot_order(self, boot_order: list) -> dict:
        """Set the boot order, sending the required If-Match ETag header.

        Args:
            boot_order: Ordered list of boot option references.

        Returns:
            Dict with keys: changed, needs_reboot, previous_boot_order, boot_order.

        Raises:
            ValueError: If validation fails or the PATCH is rejected.
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

        if boot_order == current_boot_order:
            return {
                'changed': False,
                'needs_reboot': False,
                'previous_boot_order': current_boot_order,
                'boot_order': boot_order,
            }

        payload = {"Boot": {"BootOrder": boot_order}}
        response = self._patch_with_etag(self._system_uri(), payload)
        if response.status_code in [200, 204]:
            self.boot_options = None
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
            except Exception:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to set boot order, status code: {response.status_code}{error_detail}')


    def set_boot_first_by_mac(self, mac_address: str, boot_type: str = None) -> dict:
        """Move the boot option matching a MAC address to the front of the boot order."""
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


    def set_boot_override(self, target: str, enabled: str = 'Once',
                          uefi_target: Optional[str] = None) -> bool:
        """Set boot source override, sending the required If-Match ETag header.

        Aivres BMCs return HTTP 428 ("Precondition Required") on PATCH to
        /Systems/{id} without an If-Match header. This method fetches the
        current ETag and includes it on the PATCH.

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

        last_response = None
        for payload in payloads:
            response = self._patch_with_etag(self._system_uri(), payload)
            if response.status_code in [200, 204]:
                return True
            last_response = response

        error_detail = ""
        try:
            error_data = last_response.json()
            error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
        except Exception:
            error_detail = f"\nResponse text: {last_response.text}"
        raise ValueError(f'Failed to set boot override, status code: {last_response.status_code}{error_detail}')


    def set_next_onetime_boot(self, boot_source: str = 'Pxe') -> bool:
        """Set the next one-time boot source on an Aivres (AMI-based) system.

        This is the Aivres entry point into the network-boot flow. AMI-based
        Aivres BMCs expose no writable ``Boot.BootOrder`` and their
        ``BootSourceOverrideTarget@Redfish.AllowableValues`` only offers the
        generic targets ``None``, ``Pxe``, ``Hdd``, ``Cd``, ``Diags``,
        ``BiosSetup`` and ``Usb`` — there is no ``UefiBootNext`` /
        ``UefiTarget`` to point at a specific NIC. For network boot we
        therefore set the generic ``Pxe`` override and leave NIC selection to
        the BIOS boot order.

        The underlying PATCH to /Systems/{id} requires an If-Match ETag header
        (the BMC returns HTTP 428 without one); ``set_boot_override`` fetches
        the ETag and includes it, and expects a 204 (or 200) on success.

        Args:
            boot_source: Boot source target (default 'Pxe').

        Returns:
            True on success.

        Raises:
            ValueError: If the PATCH is rejected.
        """
        return self.set_boot_override(boot_source, enabled='Once')


    def set_bios_settings(self, attributes: dict) -> bool:
        """Set BIOS attributes via /Bios/Settings with the required If-Match ETag header."""
        settings_uri = f'{self._system_uri()}/Bios/Settings'

        payload = {"Attributes": attributes}
        response = self._patch_with_etag(settings_uri, payload)
        if response.status_code in [200, 202, 204]:
            return True
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except Exception:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to set BIOS settings, status code: {response.status_code}{error_detail}')


    # ── System Reset ─────────────────────────────────────────────────

    def get_supported_reset_types(self) -> dict:
        """Get supported reset types from the ComputerSystem.Reset action."""
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
        """Reset the system."""
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
            except Exception:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to reset system, status code: {response.status_code}{error_detail}')


    # ── Firmware Inventory ───────────────────────────────────────────

    def get_firmware_inventory(self) -> dict:
        """Get firmware inventory for installed components."""
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


    # ── Network Interfaces ───────────────────────────────────────────

    def get_network_interfaces(self) -> list:
        """Get Ethernet interfaces for the system."""
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
        """Get the Manager ID from the Managers collection."""
        response = self.api.get('/redfish/v1/Managers')
        if response.status_code == 200:
            data = response.json()
            members = data.get('Members', [])
            if members:
                odata_id = members[0].get('@odata.id', '')
                return odata_id.split('/')[-1] or '1'
        return '1'

    def get_supported_bmc_reset_types(self) -> dict:
        """Get supported reset types for the BMC (Manager)."""
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
        """Reset the BMC (Manager)."""
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
            except Exception:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to reset BMC, status code: {response.status_code}{error_detail}')
