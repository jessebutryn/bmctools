import json
from typing import Optional
from bmctools.redfish.fishapi import RedfishAPI

class GigaFish:
    """
    Gigabyte (GIGA Computing) Redfish implementation.

    Gigabyte BMCs typically use '1' as the system ID under /redfish/v1/Systems/.
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


    def get_boot_order(self) -> list:
        """Get the current boot order from the Gigabyte system.

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
                    boot_options.append(option_response.json())

            self.boot_options = boot_options
            return boot_options
        else:
            raise ValueError(f'Failed to retrieve boot options, status code: {response.status_code}')


    def get_boot_option_by_mac(self, mac_address: str, type: Optional[str] = None, nocache: bool = False) -> dict:
        """Get a boot option by MAC address.

        Args:
            mac_address: MAC address to search for (format: ``XX:XX:XX:XX:XX:XX`` or ``XXXXXXXXXXXX``).
            type: Optional boot option type to filter by (e.g., ``'PXE'``).
            nocache: If True, force a fresh API call instead of using cached boot options.

        Returns:
            Dict containing the matching boot option data.

        Raises:
            ValueError: If no boot option is found with the specified MAC address or type.
        """
        normalized_mac = mac_address.replace(':', '').replace('-', '').upper()

        boot_options = self.get_boot_options(nocache=nocache)

        for option in boot_options:
            uefi_path = option.get('UefiDevicePath', '')
            if '/MAC(' in uefi_path:
                mac_start = uefi_path.find('/MAC(') + 5
                mac_end = uefi_path.find(',', mac_start)
                if mac_end > mac_start:
                    path_mac = uefi_path[mac_start:mac_end].upper()
                    if path_mac == normalized_mac:
                        if type and option.get('BootOptionType') is not None and option.get('BootOptionType', '').lower() != type.lower():
                            continue
                        return option

        raise ValueError(f'No boot option found with MAC address: {mac_address}' + (f' and type: {type}' if type else ''))


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
        boot_options = self.get_boot_options(nocache=nocache)

        for option in boot_options:
            option_alias = option.get('Alias', '')
            if option_alias.lower() == alias.lower():
                return option

        raise ValueError(f'No boot option found with alias: {alias}')


    def set_boot_order(self, boot_order: list) -> dict:
        """Set the boot order for the system.

        Args:
            boot_order: Ordered list of boot option references
                (e.g., ``['Boot0003', 'Boot0004', ...]``). Must include ALL
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

        etag = self._get_etag(self._system_uri())
        headers = {'If-Match': etag}
        response = self.api.patch(self._system_uri(), data=payload, headers=headers)
        if response.status_code in [200, 204]:
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
                return odata_id.split('/')[-1] or '1'
        return '1'

    def get_supported_bmc_reset_types(self) -> dict:
        """Get the list of supported reset types for the BMC (Manager).

        Returns:
            Dict with 'types' (list of allowed types), 'actions' (raw Actions dict),
            and 'reset_action' (the Manager.Reset action dict).
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

            # If no inline values, follow @Redfish.ActionInfo link
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
