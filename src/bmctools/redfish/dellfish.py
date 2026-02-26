import json
from typing import Optional

class DellFish:
    """
    Dell Redfish implementation.
    
    Dell systems typically use 'System.Embedded.1' as the system ID.
    This implementation supports Dell-specific Redfish endpoints and OEM extensions.
    """
    def __init__(self, fishapi: str):
        self.api = fishapi
        self.boot_options = None
        self.system_id = self._get_system_id()

    
    def _get_system_id(self) -> str:
        """Get the Dell system ID, typically 'System.Embedded.1'."""
        response = self.api.get('/redfish/v1/Systems')
        if response.status_code == 200:
            data = response.json()
            members = data.get('Members', [])
            if members and len(members) > 0:
                # Extract system ID from @odata.id (e.g., '/redfish/v1/Systems/System.Embedded.1')
                odata_id = members[0].get('@odata.id', '')
                system_id = odata_id.split('/')[-1]
                return system_id if system_id else 'System.Embedded.1'
        # Default to common Dell system ID
        return 'System.Embedded.1'

    
    def get_boot_order(self) -> list:
        """Get the current boot order from the Dell system.
        
        Returns:
            List of boot option references in order (e.g., ['Boot0001', 'Boot0002', ...])
            
        Raises:
            ValueError: If boot order cannot be retrieved
        """
        response = self.api.get(f'/redfish/v1/Systems/{self.system_id}')
        if response.status_code == 200:
            data = response.json()
            boot_order = data.get('Boot', {}).get('BootOrder', [])
            if not boot_order:
                raise ValueError("BootOrder not found in response")
            return boot_order
        else:
            raise ValueError(f'Failed to retrieve boot order, status code: {response.status_code}')
        
    
    def get_boot_options(self, nocache: bool = False) -> list:
        """Get all available boot options from the Dell system.
        
        Args:
            nocache: If True, force a fresh API call instead of using cached boot options
            
        Returns:
            List of boot option dictionaries containing details for each boot device
            
        Raises:
            ValueError: If boot options cannot be retrieved
        """
        # Return cached boot options if already fetched and cache is not disabled
        if not nocache and self.boot_options is not None:
            return self.boot_options
        
        response = self.api.get(f'/redfish/v1/Systems/{self.system_id}/BootOptions')
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


    def get_boot_option_by_mac(self, mac_address: str, type: Optional[str] = None, nocache: bool = False) -> dict:
        """Get a boot option by MAC address.
        
        Args:
            mac_address: MAC address to search for (format: XX:XX:XX:XX:XX:XX or XXXXXXXXXXXX)
            type: Optional boot option type to filter by (e.g., 'PXE')
            nocache: If True, force a fresh API call instead of using cached boot options
        
        Returns:
            Dict containing the boot option data
        
        Raises:
            ValueError: If no boot option is found with the specified MAC address or type
        """
        # Normalize MAC address to uppercase without separators
        def normalize(mac: str) -> str:
            return mac.replace(':', '').replace('-', '').upper()

        target = normalize(mac_address)

        boot_options = self.get_boot_options(nocache=nocache)

        for option in boot_options:
            # Dell exposes the NIC association in RelatedItem; follow those links
            related = option.get('RelatedItem', []) or []
            for rel in related:
                rel_id = rel.get('@odata.id') if isinstance(rel, dict) else None
                if not rel_id:
                    continue

                # Retrieve the NetworkDeviceFunction (or related) resource
                try:
                    rel_resp = self.api.get(rel_id)
                except Exception:
                    rel_resp = None

                if not rel_resp or rel_resp.status_code != 200:
                    # some RelatedItem entries may point to containers; try expanding if present
                    continue

                try:
                    rel_data = rel_resp.json()
                except Exception:
                    continue

                # Look for MAC address in common locations
                mac_candidates = []
                eth = rel_data.get('Ethernet') or {}
                if isinstance(eth, dict):
                    if eth.get('MACAddress'):
                        mac_candidates.append(eth.get('MACAddress'))
                    if eth.get('PermanentMACAddress'):
                        mac_candidates.append(eth.get('PermanentMACAddress'))

                # Some Dell OEM data may include MAC under Oem -> Dell -> DellNIC -> ProductName or similar
                try:
                    oem_mac = (
                        rel_data.get('Oem', {})
                        .get('Dell', {})
                        .get('DellNIC', {})
                        .get('ProductName')
                    )
                    # ProductName sometimes includes the MAC at the end after a dash
                    if oem_mac and isinstance(oem_mac, str) and ':' in oem_mac:
                        # extract last token with colons
                        token = oem_mac.split()[-1]
                        mac_candidates.append(token)
                except Exception:
                    pass

                for cand in mac_candidates:
                    if cand and normalize(cand) == target:
                        # Check type if specified
                        if type and option.get('BootOptionType') is not None and option.get('BootOptionType', '').lower() != type.lower():
                            continue
                        return option

        raise ValueError(f'No boot option found with MAC address: {mac_address}' + (f' and type: {type}' if type else ''))


    def get_boot_option_by_alias(self, alias: str, nocache: bool = False) -> dict:
        """Get a boot option by its display name or alias.
        
        Args:
            alias: The display name or alias to search for (case-insensitive)
            nocache: If True, force a fresh API call instead of using cached boot options
        
        Returns:
            Dict containing the boot option data
        
        Raises:
            ValueError: If no boot option is found with the specified alias
        """
        boot_options = self.get_boot_options(nocache=nocache)
        alias_lower = alias.lower()
        
        for option in boot_options:
            display_name = option.get('DisplayName', '').lower()
            name = option.get('Name', '').lower()
            description = option.get('Description', '').lower()
            
            if alias_lower in display_name or alias_lower in name or alias_lower in description:
                return option
        
        raise ValueError(f'No boot option found with alias: {alias}')


    def set_boot_order(self, boot_order: list) -> bool:
        """Set the boot order for the Dell system.
        
        Dell systems use PATCH operations on the System resource to update boot order.
        
        Args:
            boot_order: List of boot option references (e.g., ["Boot0003", "Boot0004", ...])
                        Must include ALL boot options, not just a subset.
        
        Returns:
            True if successful
            
        Raises:
            ValueError: If the boot order doesn't include all required boot options or update fails
        """
        # Get the current boot order to validate the new one
        current_boot_order = self.get_boot_order()
        
        # Validate that the new boot order has the same number of entries
        if len(boot_order) != len(current_boot_order):
            raise ValueError(
                f'Boot order must contain all {len(current_boot_order)} boot options. '
                f'You provided {len(boot_order)}. '
                f'Current boot options: {current_boot_order}'
            )
        
        # Validate that all entries in the new boot order exist in current boot order
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
        
        # Dell uses the Settings endpoint for boot configuration changes
        endpoint = '/redfish/v1/Systems/System.Embedded.1/Settings'
        
        payload = {
            "Boot": {
                "BootOrder": boot_order
            }
        }
        
        response = self.api.patch(endpoint, data=payload)
        if response.status_code in [200, 202, 204]:
            # Clear cached boot options as they may have changed
            self.boot_options = None
            return True
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

        # Move to front, keep the rest in existing order
        new_order = [boot_ref] + [b for b in current_order if b != boot_ref]

        self.set_boot_order(new_order)

        return {
            'promoted': boot_ref,
            'display_name': option.get('DisplayName', ''),
            'mac_address': mac_address,
            'boot_order': new_order,
            'message': f'{boot_ref} ({option.get("DisplayName", "")}) moved to front of boot order'
        }

    def setup_pxe_boot(self, mac_address: str, protocol: str = 'IPv4',
                       reboot: bool = True) -> dict:
        """Enable PXE boot on a NIC and set it first in boot order.

        If the NIC already has a PXE boot option, just moves it to the
        front of the boot order (no reboot needed). If PXE is not yet
        enabled, stages the BIOS setting and optionally reboots to apply.

        Args:
            mac_address: MAC address of the target NIC
            protocol: PXE protocol - 'IPv4', 'IPv6', or 'IPv4andIPv6'
            reboot: If True and PXE needs enabling, reboot to apply

        Returns:
            Dict with action taken and details
        """
        # Verify the NIC exists
        self._find_interface_by_mac(mac_address)

        # Check if a PXE boot option already exists for this MAC
        try:
            option = self.get_boot_option_by_mac(mac_address, type='PXE')
        except ValueError:
            option = None

        if option:
            # PXE already enabled — just reorder
            result = self.set_boot_first_by_mac(mac_address, boot_type='PXE')
            result['pxe_already_enabled'] = True
            result['boot_order_set'] = True
            result['rebooted'] = False
            return result

        # PXE not enabled — stage BIOS setting
        pxe_result = self.enable_nic_pxe(mac_address, protocol=protocol)

        result = {
            'pxe_already_enabled': False,
            'boot_order_set': False,
            'pxe_slot': pxe_result.get('pxe_slot'),
            'nic_id': pxe_result.get('nic_id'),
            'mac_address': mac_address,
            'rebooted': False,
        }

        if reboot:
            # Set one-time boot to PXE so it PXE boots after reboot
            self.set_next_onetime_boot('Pxe')
            self.reset_system('GracefulRestart')
            result['rebooted'] = True
            result['message'] = (
                f'PXE enabled on {pxe_result.get("nic_id")} '
                f'(PxeDev{pxe_result.get("pxe_slot")}). '
                f'System is rebooting with one-time PXE boot. '
                f'After reboot, run boot-first-by-mac to make permanent.'
            )
        else:
            result['message'] = (
                f'PXE enabled on {pxe_result.get("nic_id")} '
                f'(PxeDev{pxe_result.get("pxe_slot")}). '
                f'Reboot required to apply. Then run boot-first-by-mac '
                f'to make permanent.'
            )

        return result

    def set_next_onetime_boot(self, boot_source: str) -> bool:
        """Set the next one-time boot source for the Dell system.
        
        Args:
            boot_source: Boot source target (e.g., 'Pxe', 'Cd', 'Hdd', 'BiosSetup', 'None', etc.)
        
        Returns:
            True if successful
            
        Raises:
            ValueError: If the update fails
        """
        payload = {
            "Boot": {
                "BootSourceOverrideEnabled": "Once",
                "BootSourceOverrideTarget": boot_source
            }
        }
        
        response = self.api.patch(f'/redfish/v1/Systems/{self.system_id}', data=payload)
        if response.status_code in [200, 204]:
            return True
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to set one-time boot, status code: {response.status_code}{error_detail}')


    def get_supported_reset_types(self) -> dict:
        """Get the list of supported reset types for this Dell system.
        
        Returns:
            Dict with 'types' (list of allowed types) and 'actions' (full actions data)
        """
        response = self.api.get(f'/redfish/v1/Systems/{self.system_id}')
        if response.status_code == 200:
            data = response.json()
            actions = data.get('Actions', {})
            
            # Try multiple possible keys for the reset action
            reset_action = (actions.get('#ComputerSystem.Reset') or 
                          actions.get('ComputerSystem.Reset') or
                          {})
            
            # Try multiple possible keys for allowable values
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
        """Reset/reboot the Dell system.
        
        Common Dell reset types: On, ForceOff, GracefulShutdown, GracefulRestart, 
        ForceRestart, Nmi, PushPowerButton
        
        Args:
            reset_type: Type of reset. If None, will use 'GracefulRestart' as default.
                       Common values: 'GracefulRestart', 'ForceRestart', 'On', 'ForceOff'
        
        Returns:
            True if successful
            
        Raises:
            ValueError: If reset fails or reset_type is not supported
        """
        if reset_type is None:
            reset_type = 'GracefulRestart'
        
        # Validate reset type
        supported = self.get_supported_reset_types()
        if supported['types'] and reset_type not in supported['types']:
            raise ValueError(
                f"Reset type '{reset_type}' not supported. "
                f"Supported types: {supported['types']}"
            )
        
        payload = {
            "ResetType": reset_type
        }
        
        response = self.api.post(
            f'/redfish/v1/Systems/{self.system_id}/Actions/ComputerSystem.Reset',
            data=payload
        )
        
        if response.status_code in [200, 204]:
            return True
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to reset system, status code: {response.status_code}{error_detail}')


    def create_user_group(self, role_name: str, privileges: int) -> dict:
        """Create a Dell iDRAC user group (role) by updating DellAttributes.

        This finds the manager id (e.g. iDRAC.Embedded.1), reads existing
        Roles.N.Name keys and picks the next available index (starting at 4)
        then PATCHes `/redfish/v1/Managers/{mgr}/Oem/Dell/DellAttributes/{mgr}`

        Args:
            role_name: Display name for the new role.
            privileges: Integer privileges bitmask.

        Returns:
            Dict with `role_index` and the response data (if any).

        Raises:
            ValueError: on failure to apply the change.
        """
        # Find manager id
        mgr_resp = self.api.get('/redfish/v1/Managers')
        if mgr_resp.status_code != 200:
            raise ValueError(f'Failed to list Managers, status code: {mgr_resp.status_code}')

        mgr_data = mgr_resp.json()
        members = mgr_data.get('Members', [])
        if not members:
            raise ValueError('No Managers found')

        # Use the first manager by default
        mgr_odata = members[0].get('@odata.id', '')
        mgr_id = mgr_odata.split('/')[-1] if mgr_odata else 'iDRAC.Embedded.1'

        attrs_path = f'/redfish/v1/Managers/{mgr_id}/Oem/Dell/DellAttributes/{mgr_id}'

        # Try to read existing attributes to find used role indices
        used_indices = set()
        get_attrs = self.api.get(attrs_path)
        if get_attrs.status_code == 200:
            try:
                attrs = get_attrs.json().get('Attributes', {})
                for key in attrs.keys():
                    # match Roles.<N>.Name
                    if key.startswith('Roles.') and key.endswith('.Name'):
                        parts = key.split('.')
                        if len(parts) >= 3:
                            try:
                                idx = int(parts[1])
                                used_indices.add(idx)
                            except Exception:
                                pass
            except Exception:
                used_indices = set()

        # choose smallest available index >=4
        start = 4
        idx = start
        while idx in used_indices:
            idx += 1

        payload = {
            'Attributes': {
                f'Roles.{idx}.Name': role_name,
                f'Roles.{idx}.Privileges': privileges,
            }
        }

        resp = self.api.patch(attrs_path, data=payload)
        if resp.status_code in [200, 204]:
            # try to return any JSON body if present
            try:
                data = resp.json()
            except Exception:
                data = {}
            return {'role_index': idx, 'response': data}
        else:
            detail = ''
            try:
                detail = json.dumps(resp.json(), indent=2)
            except Exception:
                detail = resp.text
            raise ValueError(f'Failed to create user group, status: {resp.status_code}, detail: {detail}')


    def toggle_local_idrac_access(self, disable: bool) -> dict:
        """Toggle local iDRAC access via DellAttributes.

        NOTE: Dell's semantics are inverted — setting these attributes to
        "Enabled" actually disables local iDRAC access. Therefore this
        function accepts `disable: bool` where True will set the attributes
        to "Enabled" (disabling local access) and False will set them to
        "Disabled" (enabling local access).

        This patches the DellAttributes endpoint for the first Manager (iDRAC)
        and sets the following attributes:
          - LocalSecurity.1.PrebootConfig: "Enabled" / "Disabled"
          - LocalSecurity.1.LocalConfig: "Enabled" / "Disabled"

        Args:
            disable: True to disable local access, False to enable it.

        Returns:
            Dict with the response JSON (if any) and the applied values.

        Raises:
            ValueError: on failure to apply the change.
        """
        # Find manager id
        mgr_resp = self.api.get('/redfish/v1/Managers')
        if mgr_resp.status_code != 200:
            raise ValueError(f'Failed to list Managers, status code: {mgr_resp.status_code}')

        mgr_data = mgr_resp.json()
        members = mgr_data.get('Members', [])
        if not members:
            raise ValueError('No Managers found')

        mgr_odata = members[0].get('@odata.id', '')
        mgr_id = mgr_odata.split('/')[-1] if mgr_odata else 'iDRAC.Embedded.1'

        attrs_path = f'/redfish/v1/Managers/{mgr_id}/Oem/Dell/DellAttributes/{mgr_id}'

        # Inverted semantics: 'Enabled' will disable local access
        value = 'Enabled' if disable else 'Disabled'

        payload = {
            'Attributes': {
                'LocalSecurity.1.PrebootConfig': value,
                'LocalSecurity.1.LocalConfig': value,
            }
        }

        resp = self.api.patch(attrs_path, data=payload)
        if resp.status_code in [200, 204]:
            try:
                data = resp.json()
            except Exception:
                data = {}
            return {'applied': {'LocalSecurity.1.PrebootConfig': value, 'LocalSecurity.1.LocalConfig': value}, 'response': data}
        else:
            detail = ''
            try:
                detail = json.dumps(resp.json(), indent=2)
            except Exception:
                detail = resp.text
            raise ValueError(f'Failed to toggle local iDRAC access, status: {resp.status_code}, detail: {detail}')


    def get_network_interfaces(self) -> list:
        """Get NIC information including MAC addresses from the Dell system.

        Queries the EthernetInterfaces collection under the system resource
        and returns details for each interface.

        Returns:
            List of dicts, each containing interface details (Id, Name,
            MACAddress, SpeedMbps, Status, etc.)

        Raises:
            ValueError: If the interfaces cannot be retrieved
        """
        response = self.api.get(f'/redfish/v1/Systems/{self.system_id}/EthernetInterfaces')
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


    def _find_interface_by_mac(self, mac_address: str) -> dict:
        """Find an EthernetInterface by MAC address.

        Args:
            mac_address: MAC address (e.g., '04:32:01:D8:C0:B0')

        Returns:
            The matching interface dict

        Raises:
            ValueError: If no interface matches
        """
        interfaces = self.get_network_interfaces()
        target_mac = mac_address.replace(':', '').replace('-', '').upper()

        for iface in interfaces:
            iface_mac = (iface.get('MACAddress') or '').replace(':', '').replace('-', '').upper()
            if iface_mac == target_mac:
                return iface

        raise ValueError(f'No NIC found with MAC address: {mac_address}')

    def _get_nic_oem_attrs_path(self, iface: dict) -> str:
        """Build the DellNetworkAttributes path for an EthernetInterface.

        Args:
            iface: EthernetInterface dict (must contain 'Id' and 'Links')

        Returns:
            The OEM DellNetworkAttributes endpoint path
        """
        nic_id = iface['Id']

        chassis_id = 'System.Embedded.1'
        chassis_link = iface.get('Links', {}).get('Chassis', {}).get('@odata.id', '')
        if chassis_link:
            chassis_id = chassis_link.split('/')[-1]

        adapter_id = nic_id.split('-')[0]

        return (
            f'/redfish/v1/Chassis/{chassis_id}/NetworkAdapters/{adapter_id}'
            f'/NetworkDeviceFunctions/{nic_id}'
            f'/Oem/Dell/DellNetworkAttributes/{nic_id}'
        )

    def get_nic_attributes(self, mac_address: str) -> dict:
        """Get Dell OEM network attributes for a NIC by MAC address.

        Args:
            mac_address: MAC address (e.g., '04:32:01:D8:C0:B0')

        Returns:
            Dict with nic_id and the OEM attributes

        Raises:
            ValueError: If the NIC or attributes cannot be retrieved
        """
        iface = self._find_interface_by_mac(mac_address)
        attrs_path = self._get_nic_oem_attrs_path(iface)

        response = self.api.get(attrs_path)
        if response.status_code != 200:
            raise ValueError(
                f'Failed to get attributes for {iface["Id"]}, '
                f'status: {response.status_code}'
            )

        data = response.json()
        return {
            'nic_id': iface['Id'],
            'mac_address': mac_address,
            'attributes': data.get('Attributes', {})
        }

    def _get_bios_attributes(self) -> dict:
        """Get current BIOS attributes.

        Returns:
            Dict of BIOS attribute name -> value

        Raises:
            ValueError: If BIOS attributes cannot be retrieved
        """
        response = self.api.get(f'/redfish/v1/Systems/{self.system_id}/Bios')
        if response.status_code != 200:
            raise ValueError(f'Failed to get BIOS attributes, status: {response.status_code}')
        return response.json().get('Attributes', {})

    def enable_nic_pxe(self, mac_address: str, protocol: str = 'IPv4') -> dict:
        """Enable PXE boot on a NIC identified by MAC address.

        Finds the NIC, then configures a PxeDev slot in the BIOS Settings
        to enable PXE boot on that interface. Uses PxeDev1-4 slots.

        Args:
            mac_address: MAC address (e.g., '04:32:01:D8:C0:B0')
            protocol: PXE protocol - 'IPv4', 'IPv6', or 'IPv4andIPv6'

        Returns:
            Dict with nic_id, pxe_slot, and result message

        Raises:
            ValueError: If the NIC cannot be found, no free PXE slot, or PATCH fails
        """
        iface = self._find_interface_by_mac(mac_address)
        nic_id = iface['Id']

        # Read current BIOS attributes to find PxeDev slots
        bios_attrs = self._get_bios_attributes()

        # Check PxeDev1 through PxeDev4 for an existing or free slot
        target_slot = None
        for i in range(1, 5):
            en_key = f'PxeDev{i}EnDis'
            iface_key = f'PxeDev{i}Interface'

            # Skip if the BIOS doesn't have these attributes at all
            if en_key not in bios_attrs:
                continue

            current_iface = bios_attrs.get(iface_key, '')
            enabled = bios_attrs.get(en_key, 'Disabled')

            # Already assigned to this NIC
            if current_iface == nic_id:
                target_slot = i
                break

            # First free (disabled) slot
            if target_slot is None and enabled == 'Disabled':
                target_slot = i

        if target_slot is None:
            raise ValueError(
                'No available PxeDev slot (1-4). All slots are in use.'
            )

        payload = {
            "Attributes": {
                f"PxeDev{target_slot}EnDis": "Enabled",
                f"PxeDev{target_slot}Interface": nic_id,
                f"PxeDev{target_slot}Protocol": protocol,
            }
        }

        settings_path = f'/redfish/v1/Systems/{self.system_id}/Bios/Settings'
        response = self.api.patch(settings_path, data=payload)
        if response.status_code in [200, 202, 204]:
            return {
                'nic_id': nic_id,
                'mac_address': mac_address,
                'pxe_slot': target_slot,
                'message': (
                    f'PXE boot enabled on {nic_id} (PxeDev{target_slot}). '
                    f'A system reboot is required to apply.'
                )
            }
        else:
            detail = ''
            try:
                detail = json.dumps(response.json(), indent=2)
            except Exception:
                detail = response.text
            raise ValueError(
                f'Failed to enable PXE on {nic_id}, status: {response.status_code}, detail: {detail}'
            )
