import json
from typing import Optional
from bmctools.redfish.fishapi import RedfishAPI

class CiscoFish:
    """
    Cisco (CIMC/UCS) Redfish implementation.

    Cisco CIMC does not expose standard Redfish BootOrder/BootOptions collections.
    Boot device selection is managed via BootSourceOverrideTarget (one-time or
    continuous) and detailed boot order is controlled through BIOS token settings.

    Boot override and BIOS settings are handled by the generic Redfish class
    (standard Redfish endpoints). This class provides Cisco-specific operations.
    """
    def __init__(self, fishapi: 'RedfishAPI') -> None:
        """Initialize with a shared RedfishAPI session.

        Args:
            fishapi: An authenticated :class:`~bmctools.redfish.fishapi.RedfishAPI` instance.
        """
        self.api = fishapi
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


    # ── System Reset ──────────────────────────────────────────────────

    def get_supported_reset_types(self) -> dict:
        """Get the reset types supported by this Cisco system.

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
        """Reset the Cisco system.

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


    # ── Firmware ──────────────────────────────────────────────────────

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


    # ── NIC Discovery ─────────────────────────────────────────────────

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
