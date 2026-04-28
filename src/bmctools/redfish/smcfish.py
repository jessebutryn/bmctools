
from typing import Optional

from bmctools.redfish.fishapi import RedfishAPI

class SMCFish:
    """
    Supermicro Redfish implementation.
    """
    def __init__(self, fishapi: 'RedfishAPI') -> None:
        """Initialize with a shared RedfishAPI session.

        Args:
            fishapi: An authenticated :class:`~bmctools.redfish.fishapi.RedfishAPI` instance.
        """
        self.api = fishapi
        self.boot_options = None

    
    def get_boot_order(self) -> list:
        """Get the current boot order from the Supermicro system.

        Returns:
            List of boot option references in order.

        Raises:
            ValueError: If the boot order cannot be retrieved.
        """
        response = self.api.get('/redfish/v1/Systems/1')
        if response.status_code == 200:
            data = response.json()
            boot_order = data.get('Boot', {}).get('BootOrder', [])
            if not boot_order:
                raise ValueError("BootOrder not found in response")
            return boot_order
        else:
            raise ValueError(f'Failed to retrieve boot order, status code: {response.status_code}')
        
    
    # ── BMC (Manager) Reset ──────────────────────────────────────────

    def _get_manager_id(self) -> str:
        """Get the Manager ID from the Managers collection.

        Returns:
            Manager ID string (e.g., '1').
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


    def get_boot_options(self, nocache: bool = False) -> list:
        """Get all available boot options.

        Args:
            nocache: If True, bypass the cache and query the BMC directly.

        Returns:
            List of boot option dictionaries.

        Raises:
            ValueError: If boot options cannot be retrieved.
        """
        # Return cached boot options if already fetched and cache is not disabled
        if not nocache and self.boot_options is not None:
            return self.boot_options

        response = self.api.get('/redfish/v1/Systems/1/BootOptions')
        if response.status_code == 200:
            data = response.json()
            members = data.get('Members', [])
            boot_options = []
            for member in members:
                option_response = self.api.get(member['@odata.id'])
                if option_response.status_code == 200:
                    option_data = option_response.json()
                    boot_options.append(option_data)

            # Cache the boot options
            self.boot_options = boot_options
            return boot_options
        else:
            raise ValueError(f'Failed to retrieve boot options, status code: {response.status_code}')


    def get_network_interfaces(self) -> list:
        """Get NIC information including MAC addresses from the Supermicro system.

        Queries the EthernetInterfaces collection under /redfish/v1/Systems/1
        and returns details for each interface.

        Returns:
            List of dicts, each containing interface details (Id, Name,
            MACAddress, SpeedMbps, Status, etc.)

        Raises:
            ValueError: If the interfaces cannot be retrieved
        """
        response = self.api.get('/redfish/v1/Systems/1/EthernetInterfaces')
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


    def get_boot_option_by_mac(self, mac_address: str, type: Optional[str] = None, nocache: bool = False) -> dict:
        """Get a boot option by MAC address.

        Supermicro encodes the MAC in the BootOption ``DisplayName`` as
        ``(MAC:xxxxxxxxxxxx)`` rather than in a ``UefiDevicePath`` field,
        and does not populate ``BootOptionType``, so we parse the MAC from
        the display name and use ``type`` as a substring match against it.

        Args:
            mac_address: MAC address (format: ``XX:XX:XX:XX:XX:XX`` or ``XXXXXXXXXXXX``).
            type: Optional substring to match against ``DisplayName`` (e.g., ``'PXE'``).
            nocache: If True, force a fresh API call instead of using cached boot options.

        Returns:
            Dict containing the matching boot option data.

        Raises:
            ValueError: If no boot option is found with the specified MAC address (and type).
        """
        normalized_mac = mac_address.replace(':', '').replace('-', '').upper()

        boot_options = self.get_boot_options(nocache=nocache)

        for option in boot_options:
            display_name = option.get('DisplayName', '')
            marker = '(MAC:'
            idx = display_name.find(marker)
            if idx == -1:
                continue
            mac_start = idx + len(marker)
            mac_end = display_name.find(')', mac_start)
            if mac_end <= mac_start:
                continue
            option_mac = display_name[mac_start:mac_end].upper()
            if option_mac != normalized_mac:
                continue
            if type and type.lower() not in display_name.lower():
                continue
            return option

        raise ValueError(
            f'No boot option found with MAC address: {mac_address}'
            + (f' and type: {type}' if type else '')
        )