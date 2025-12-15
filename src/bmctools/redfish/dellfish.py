import json

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


    def get_boot_option_by_mac(self, mac_address: str, nocache: bool = False) -> dict:
        """Get a boot option by MAC address.
        
        Args:
            mac_address: MAC address to search for (format: XX:XX:XX:XX:XX:XX or XXXXXXXXXXXX)
            nocache: If True, force a fresh API call instead of using cached boot options
        
        Returns:
            Dict containing the boot option data
        
        Raises:
            ValueError: If no boot option is found with the specified MAC address
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
                        return option

        raise ValueError(f'No boot option found with MAC address: {mac_address}')


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
        
        # Dell systems use PATCH on the System resource
        payload = {
            "Boot": {
                "BootOrder": boot_order
            }
        }
        
        response = self.api.patch(f'/redfish/v1/Systems/{self.system_id}', data=payload)
        if response.status_code in [200, 204]:
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