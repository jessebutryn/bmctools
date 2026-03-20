import json
from typing import Optional

class GigaFish:
    """
    Gigabyte (GIGA Computing) Redfish implementation.

    Gigabyte BMCs typically use '1' as the system ID under /redfish/v1/Systems/.
    """
    def __init__(self, fishapi):
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
        boot_options = self.get_boot_options(nocache=nocache)

        for option in boot_options:
            option_alias = option.get('Alias', '')
            if option_alias.lower() == alias.lower():
                return option

        raise ValueError(f'No boot option found with alias: {alias}')


    def set_boot_order(self, boot_order: list) -> bool:
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

        payload = {
            "Boot": {
                "BootOrder": boot_order
            }
        }

        etag = self._get_etag(self._system_uri())
        headers = {'If-Match': etag}
        response = self.api.patch(self._system_uri(), data=payload, headers=headers)
        if response.status_code in [200, 204]:
            return True
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to set boot order, status code: {response.status_code}{error_detail}')


    def get_supported_reset_types(self) -> dict:
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

        self.set_boot_order(new_order)

        return {
            'promoted': boot_ref,
            'display_name': option.get('DisplayName', ''),
            'mac_address': mac_address,
            'boot_order': new_order,
            'message': f'{boot_ref} ({option.get("DisplayName", "")}) moved to front of boot order'
        }
