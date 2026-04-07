import json
from typing import Optional
from bmctools.redfish.fishapi import RedfishAPI

class AsusFish:
    """
    ASUS Redfish implementation.
    """
    def __init__(self, fishapi: 'RedfishAPI') -> None:
        """Initialize with a shared RedfishAPI session.

        Args:
            fishapi: An authenticated :class:`~bmctools.redfish.fishapi.RedfishAPI` instance.
        """
        self.api = fishapi
        self.boot_options = None


    def get_boot_order(self) -> list:
        """Get the current boot order from the ASUS system.

        Returns:
            List of boot option references in order.

        Raises:
            ValueError: If the boot order cannot be retrieved.
        """
        response = self.api.get(f'/redfish/v1/Systems/Self')
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
        # Return cached boot options if already fetched and cache is not disabled
        if not nocache and self.boot_options is not None:
            return self.boot_options
        
        response = self.api.get('/redfish/v1/Systems/Self/BootOptions')
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
        normalized_mac = mac_address.replace(':', '').replace('-', '').upper()
        
        boot_options = self.get_boot_options(nocache=nocache)
        
        for option in boot_options:
            uefi_path = option.get('UefiDevicePath', '')
            # Extract MAC from UEFI device path (format: .../MAC(XXXXXXXXXXXX,0xX)/...)
            if '/MAC(' in uefi_path:
                # Find MAC address in the path
                mac_start = uefi_path.find('/MAC(') + 5
                mac_end = uefi_path.find(',', mac_start)
                if mac_end > mac_start:
                    path_mac = uefi_path[mac_start:mac_end].upper()
                    if path_mac == normalized_mac:
                        # Check type if specified
                        if type and option.get('BootOptionType') is not None and option.get('BootOptionType', '').lower() != type.lower():
                            continue
                        return option
        
        raise ValueError(f'No boot option found with MAC address: {mac_address}' + (f' and type: {type}' if type else ''))
        


    def set_boot_order(self, boot_order: list) -> dict:
        """Set the boot order for the system.

        Args:
            boot_order: List of boot option references (e.g., ["Boot0003", "Boot0004", ...])
                        Must include ALL boot options, not just a subset.

        Returns:
            Dict with keys: changed, needs_reboot, previous_boot_order, boot_order.

        Raises:
            ValueError: If the boot order doesn't include all required boot options
        """
        # ASUS uses FutureState (SD) URI for boot configuration changes
        # First, get the current boot order to validate the new one
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

        # Skip PATCH if the order is already correct
        if boot_order == current_boot_order:
            return {
                'changed': False,
                'needs_reboot': False,
                'previous_boot_order': current_boot_order,
                'boot_order': boot_order,
            }

        # Get the current ETag from the SD endpoint
        sd_endpoint = '/redfish/v1/Systems/Self/SD'
        etag = self._get_sd_etag(sd_endpoint)

        payload = {
            "Boot": {
                "BootOrder": boot_order
            }
        }

        headers = {'If-Match': etag}
        response = self.api.patch(sd_endpoint, data=payload, headers=headers)
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


    def _get_sd_etag(self, sd_endpoint: str = '/redfish/v1/Systems/Self/SD') -> str:
        """Retrieve the ETag header from the SD (FutureState) endpoint.

        Args:
            sd_endpoint: The SD endpoint to query (defaults to Systems/Self/SD).

        Returns:
            The ETag header string.

        Raises:
            ValueError: If the SD endpoint cannot be read or the ETag header is missing.
        """
        get_response = self.api.get(sd_endpoint)
        if get_response.status_code != 200:
            raise ValueError(f'Failed to get current system state, status code: {get_response.status_code}')

        etag = get_response.headers.get('ETag')
        if not etag:
            raise ValueError('ETag header not found in response')

        return etag
    

    def get_pending_boot_order(self) -> list:
        """Get the pending boot order from the FutureState (SD) endpoint."""
        response = self.api.get('/redfish/v1/Systems/Self/SD')
        if response.status_code == 200:
            data = response.json()
            boot_order = data.get('Boot', {}).get('BootOrder', [])
            return boot_order
        else:
            raise ValueError(f'Failed to retrieve pending boot order, status code: {response.status_code}')
    


    def get_supported_reset_types(self) -> dict:
        """Get the list of supported reset types for this system.
        
        Returns a dict with 'types' (list of allowed types) and 'actions' (full actions data for debugging)
        """
        response = self.api.get('/redfish/v1/Systems/Self')
        if response.status_code == 200:
            data = response.json()
            actions = data.get('Actions', {})
            
            # Try multiple possible keys for the reset action
            reset_action = (actions.get('#ComputerSystem.Reset') or 
                          actions.get('ComputerSystem.Reset') or
                          actions.get('#ComputerSystem.Reset@Redfish.ActionInfo') or
                          {})
            
            # Try multiple possible keys for allowable values
            allowed_values = (reset_action.get('ResetType@Redfish.AllowableValues') or
                            reset_action.get('AllowableValues') or
                            reset_action.get('@Redfish.AllowableValues') or
                            [])
            
            return {
                'types': allowed_values,
                'actions': actions,
                'reset_action': reset_action
            }
        else:
            raise ValueError(f'Failed to get system info, status code: {response.status_code}')
    


    def reset_system(self, reset_type: str = None) -> bool:
        """Reset/reboot the system to apply pending boot order changes.
        
        Args:
            reset_type: Type of reset. If None, will use the first supported type.
                Common values that may be supported:
                - "On": Turn on the system
                - "ForceOff": Immediate shutdown
                - "GracefulShutdown": Graceful shutdown
                - "GracefulRestart": Graceful reboot
                - "ForceRestart": Immediate reboot
                - "PushPowerButton": Simulate power button press
        
        Returns:
            True if reset command was accepted
        """
        # If no reset type specified, get supported types and use first one
        if reset_type is None:
            reset_info = self.get_supported_reset_types()
            supported_types = reset_info['types']
            
            if not supported_types:
                # If we can't find supported types, try common ones
                # Most systems support at least these
                reset_type = 'ForceRestart'
            else:
                # Prefer graceful restart if available, otherwise use first available
                if 'GracefulRestart' in supported_types:
                    reset_type = 'GracefulRestart'
                elif 'ForceRestart' in supported_types:
                    reset_type = 'ForceRestart'
                else:
                    reset_type = supported_types[0]
        
        payload = {
            "ResetType": reset_type
        }
        
        response = self.api.post('/redfish/v1/Systems/Self/Actions/ComputerSystem.Reset', data=payload)
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
        

    def get_boot_option_by_alias(self, alias: str, nocache: bool = False) -> dict:
        """Get a boot option by its alias name.
        
        Args:
            alias: Alias name of the boot option to search for
            nocache: If True, force a fresh API call instead of using cached boot options
        
        Returns:
            Dict containing the boot option data
        
        Raises:
            ValueError: If no boot option is found with the specified alias
        """
        boot_options = self.get_boot_options(nocache=nocache)
        
        for option in boot_options:
            option_alias = option.get('Alias', '')
            if option_alias.lower() == alias.lower():
                return option
        
        raise ValueError(f'No boot option found with alias: {alias}')

    def set_boot_first_by_mac(self, mac_address: str, boot_type: str = None) -> dict:
        """Move the boot option matching a MAC address to the front of the boot order.

        If the system has Boot.BootOrder on /Systems/Self/SD, uses the standard
        method. If Boot.BootOrder doesn't exist, falls back to SETUP006 via /Bios/SD.

        Args:
            mac_address: MAC address of the target NIC.
            boot_type: Optional boot option type filter (e.g., 'PXE').

        Returns:
            Dict with the new boot order and the promoted option.
        """
        # Check if /Systems/Self/SD has a Boot.BootOrder
        try:
            current_order = self.get_boot_order()
        except (ValueError, Exception):
            current_order = None

        if current_order:
            # Standard BootOrder method (newer models)
            option = self.get_boot_option_by_mac(mac_address, type=boot_type)
            boot_ref = option.get('BootOptionReference')
            if not boot_ref:
                raise ValueError(
                    f'Boot option for MAC {mac_address} has no BootOptionReference'
                )

            if boot_ref not in current_order:
                raise ValueError(
                    f'{boot_ref} not found in current boot order: {current_order}'
                )

            new_order = [boot_ref] + [b for b in current_order if b != boot_ref]
            result = self.set_boot_order(new_order)

            return {
                'method': 'boot_order',
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

        # No Boot.BootOrder — use SETUP006
        result = self.set_boot_first_by_mac_bios(mac_address, boot_type=boot_type)
        result['method'] = 'setup006'
        return result

    def get_firmware_inventory(self) -> dict:
        """Get firmware inventory from the UpdateService.

        Returns:
            Dict containing firmware inventory information including BIOS and BMC versions

        Raises:
            ValueError: If the firmware inventory cannot be retrieved
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


    def get_update_service_info(self) -> dict:
        """Get UpdateService information including current update status.

        Returns:
            Dict containing UpdateService status and configuration

        Raises:
            ValueError: If UpdateService cannot be accessed
        """
        response = self.api.get('/redfish/v1/UpdateService')
        if response.status_code == 200:
            data = response.json()
            oem_data = data.get('Oem', {})
            ami_update = oem_data.get('AMIUpdateService', {})
            bmc_data = oem_data.get('BMC', {})

            return {
                'service_enabled': data.get('ServiceEnabled'),
                'status': data.get('Status', {}),
                'multipart_push_uri': data.get('MultipartHttpPushUri'),
                'update_status': ami_update.get('UpdateStatus'),
                'update_target': ami_update.get('UpdateTarget'),
                'flash_percentage': ami_update.get('FlashPercentage'),
                'dual_images': bmc_data.get('DualImageConfigurations', {})
            }
        else:
            raise ValueError(f'Failed to get UpdateService info, status code: {response.status_code}')


    def update_bmc_firmware(self, firmware_path: str, preserve_config: bool = True) -> dict:
        """Update BMC firmware using multipart HTTP push.

        Args:
            firmware_path: Path to the BMC firmware file
            preserve_config: Whether to preserve BMC configuration (default: True)

        Returns:
            Dict containing update status information

        Raises:
            ValueError: If the firmware update fails to initiate
        """
        import os
        endpoint = '/redfish/v1/UpdateService/upload'

        update_params = {
            "Targets": [],
            "@Redfish.OperationApplyTime": "Immediate"
        }

        oem_params = {}
        if preserve_config:
            oem_params['PreserveConfiguration'] = True

        response = self.api.post_multipart(endpoint, firmware_path, update_params, oem_params)

        if response.status_code in [200, 202, 204]:
            # Get the current status after initiating upload
            try:
                status_info = self.get_update_service_info()
                return {
                    'status': 'accepted',
                    'message': 'BMC firmware update initiated',
                    'update_status': status_info.get('update_status'),
                    'flash_percentage': status_info.get('flash_percentage')
                }
            except Exception:
                return {
                    'status': 'accepted',
                    'message': 'BMC firmware update initiated'
                }
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to update BMC firmware, status code: {response.status_code}{error_detail}')


    def update_bios_firmware(self, firmware_path: str) -> dict:
        """Update BIOS firmware using Asus OEM extension.

        Args:
            firmware_path: Path to the BIOS firmware file

        Returns:
            Dict containing update status information

        Raises:
            ValueError: If the firmware update fails to initiate
        """
        # Asus uses an OEM-specific endpoint for BIOS updates
        endpoint = '/redfish/v1/UpdateService/Actions/Oem/UpdateService.BIOSFwUpdate'

        response = self.api.post_file(endpoint, firmware_path)

        if response.status_code in [200, 202, 204]:
            # Get the current status after initiating upload
            try:
                status_info = self.get_update_service_info()
                return {
                    'status': 'accepted',
                    'message': 'BIOS firmware update initiated',
                    'update_status': status_info.get('update_status'),
                    'flash_percentage': status_info.get('flash_percentage')
                }
            except Exception:
                return {
                    'status': 'accepted',
                    'message': 'BIOS firmware update initiated'
                }
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to update BIOS firmware, status code: {response.status_code}{error_detail}')


    def get_network_interfaces(self) -> list:
        """Get NIC information including MAC addresses from the system.

        Queries the EthernetInterfaces collection under /redfish/v1/Systems/Self
        and returns details for each interface.

        Returns:
            List of dicts, each containing interface details (Id, Name,
            MACAddress, SpeedMbps, Status, etc.)

        Raises:
            ValueError: If the interfaces cannot be retrieved
        """
        response = self.api.get('/redfish/v1/Systems/Self/EthernetInterfaces')
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


    def set_trusted_module_state(self, state: str = "Disabled") -> bool:
        """
        Set the TrustedModules State (e.g., "Enabled" or "Disabled") at /redfish/v1/Systems/Self.
        Uses PATCH with If-Match header (ETag).
        Args:
            state: The desired state for TrustedModules ("Enabled" or "Disabled").
        Returns:
            True if successful.
        Raises:
            ValueError if the operation fails.
        """
        endpoint = '/redfish/v1/Systems/Self'
        # Get ETag for If-Match header
        get_response = self.api.get(endpoint)
        if get_response.status_code != 200:
            raise ValueError(f'Failed to get system info, status code: {get_response.status_code}')
        etag = get_response.headers.get('ETag')
        if not etag:
            raise ValueError('ETag header not found in response')

        payload = {
            "TrustedModules": [
                {"Status": {"State": state}}
            ]
        }
        headers = {'If-Match': etag}
        response = self.api.patch(endpoint, data=payload, headers=headers)
        if response.status_code in [200, 204]:
            return True
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to set TrustedModules state, status code: {response.status_code}{error_detail}')


    # ── SETUP006 Boot Order (older ASUS models via /Bios/SD) ──────────
    #
    # On older ASUS boards, boot order is not in /Systems/Self/SD BootOrder
    # but in a BIOS attribute called SETUP006. The value is a semicolon-
    # delimited string:
    #
    #   "display name,0xHEXID,true;another entry,0xHEXID,false;"
    #
    # The order of entries IS the boot priority. The hex ID maps to
    # /BootOptions/XXXX. The boolean is whether the entry is enabled.
    # MAC addresses appear in the display name for network boot options.

    @staticmethod
    def parse_setup006(value: str) -> list:
        """Parse a SETUP006 string into a list of boot entry dicts.

        Args:
            value: The raw SETUP006 attribute string.

        Returns:
            List of dicts with keys: display_name, hex_id, enabled, raw
        """
        entries = []
        for part in value.split(';'):
            part = part.strip()
            if not part:
                continue
            # Format: "display name,0xHEXID,true"
            pieces = part.rsplit(',', 2)
            if len(pieces) == 3:
                display_name = pieces[0]
                hex_id = pieces[1]
                enabled = pieces[2].strip().lower() == 'true'
                entries.append({
                    'display_name': display_name,
                    'hex_id': hex_id,
                    'enabled': enabled,
                    'raw': part,
                })
            else:
                # Unparseable entry — preserve as-is
                entries.append({
                    'display_name': part,
                    'hex_id': None,
                    'enabled': None,
                    'raw': part,
                })
        return entries

    @staticmethod
    def build_setup006(entries: list) -> str:
        """Rebuild a SETUP006 string from a list of boot entry dicts.

        Args:
            entries: List of dicts as returned by parse_setup006().

        Returns:
            The SETUP006 attribute string.
        """
        parts = []
        for entry in entries:
            if entry.get('hex_id') is not None:
                enabled_str = 'true' if entry['enabled'] else 'false'
                parts.append(f"{entry['display_name']},{entry['hex_id']},{enabled_str}")
            else:
                parts.append(entry['raw'])
        return ';'.join(parts) + ';'

    def get_bios_boot_order(self) -> dict:
        """Get the boot order from the SETUP006 BIOS attribute.

        Returns:
            Dict with 'entries' (parsed list) and 'raw' (original string).

        Raises:
            ValueError: If SETUP006 is not found.
        """
        response = self.api.get('/redfish/v1/Systems/Self/Bios')
        if response.status_code != 200:
            raise ValueError(f'Failed to get BIOS settings, status code: {response.status_code}')

        data = response.json()
        attributes = data.get('Attributes', {})
        setup006 = attributes.get('SETUP006')
        if setup006 is None:
            raise ValueError('SETUP006 attribute not found in BIOS settings')

        entries = self.parse_setup006(setup006)
        return {
            'entries': entries,
            'raw': setup006,
        }

    def set_bios_boot_order(self, entries: list) -> bool:
        """Set the boot order via SETUP006 on /Bios/SD.

        Args:
            entries: Ordered list of boot entry dicts (from parse_setup006).

        Returns:
            True if successful.
        """
        setup006_value = self.build_setup006(entries)

        sd_endpoint = '/redfish/v1/Systems/Self/Bios/SD'
        etag = self._get_sd_etag(sd_endpoint)

        payload = {
            "Attributes": {
                "SETUP006": setup006_value
            }
        }

        headers = {'If-Match': etag}
        response = self.api.patch(sd_endpoint, data=payload, headers=headers)
        if response.status_code in [200, 204]:
            return True
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to set SETUP006, status code: {response.status_code}{error_detail}')

    def set_boot_first_by_hex_id(self, hex_id: str) -> dict:
        """Move a boot entry to the front of the SETUP006 boot order by hex ID.

        Args:
            hex_id: The hex boot option ID (e.g., '0x0007' or '0007').

        Returns:
            Dict with the result including new order.
        """
        # Normalize to 0xXXXX format
        if not hex_id.startswith('0x'):
            hex_id = f'0x{hex_id.upper()}'
        hex_id = hex_id.lower()

        boot_data = self.get_bios_boot_order()
        entries = boot_data['entries']

        # Find the target entry
        target = None
        rest = []
        for entry in entries:
            entry_hex = (entry.get('hex_id') or '').lower()
            if entry_hex == hex_id:
                target = entry
            else:
                rest.append(entry)

        if target is None:
            available = [e['hex_id'] for e in entries if e.get('hex_id')]
            raise ValueError(f'Boot entry {hex_id} not found. Available: {available}')

        # Ensure the target is enabled
        target['enabled'] = True

        new_order = [target] + rest
        self.set_bios_boot_order(new_order)

        return {
            'promoted': target['hex_id'],
            'display_name': target['display_name'],
            'boot_order': [{'hex_id': e['hex_id'], 'display_name': e['display_name'], 'enabled': e['enabled']} for e in new_order],
            'message': f"{target['hex_id']} ({target['display_name']}) moved to front of boot order"
        }

    def _build_boot_option_mac_map(self) -> dict:
        """Build a mapping of BootOption hex IDs to MAC addresses.

        Fetches each BootOption and extracts the MAC from UefiDevicePath.

        Returns:
            Dict mapping hex ID (e.g., '0x0007') to normalized MAC (e.g., 'A088C2973BE1').
        """
        mac_map = {}
        boot_options = self.get_boot_options(nocache=True)
        for option in boot_options:
            uefi_path = option.get('UefiDevicePath', '')
            if '/MAC(' in uefi_path:
                mac_start = uefi_path.find('/MAC(') + 5
                mac_end = uefi_path.find(',', mac_start)
                if mac_end > mac_start:
                    mac = uefi_path[mac_start:mac_end].upper()
                    # BootOption Id is like "0001" — normalize to "0x0001"
                    opt_id = option.get('Id', '')
                    hex_id = f'0x{opt_id.upper()}'
                    mac_map[hex_id.lower()] = mac
        return mac_map

    # ── BMC (Manager) Reset ──────────────────────────────────────────

    def _get_manager_id(self) -> str:
        """Get the Manager ID (BMC) from the Managers collection.

        Returns:
            Manager ID string (e.g., 'Self').
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
        """Fetch allowable values from a Redfish ActionInfo endpoint.

        Args:
            action_info_uri: URI to the ActionInfo resource.

        Returns:
            List of allowable value strings for the ResetType parameter.
        """
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


    def set_boot_first_by_mac_bios(self, mac_address: str, boot_type: str = None) -> dict:
        """Move a boot entry to the front of SETUP006 by MAC address.

        Matches MAC addresses by cross-referencing BootOptions (UefiDevicePath)
        with SETUP006 entries (hex ID). Falls back to matching MAC in the
        display name if not found via BootOptions.

        Args:
            mac_address: MAC address to search for (e.g., 'A0:88:C2:97:3B:E1').
            boot_type: Optional type filter to match in display name (e.g., 'PXE', 'HTTP').

        Returns:
            Dict with the result including new order.
        """
        normalized_mac = mac_address.replace(':', '').replace('-', '').upper()
        display_mac = mac_address.replace('-', ':').upper()

        boot_data = self.get_bios_boot_order()
        entries = boot_data['entries']

        # Build a map of hex_id -> MAC from BootOptions UefiDevicePath
        mac_map = self._build_boot_option_mac_map()

        # First pass: match via BootOptions MAC map
        matches = []
        for entry in entries:
            entry_hex = (entry.get('hex_id') or '').lower()
            entry_mac = mac_map.get(entry_hex, '')
            if entry_mac == normalized_mac:
                if boot_type:
                    if boot_type.upper() in entry.get('display_name', '').upper():
                        matches.append(entry)
                else:
                    matches.append(entry)

        # Second pass: fall back to matching MAC in display name
        if not matches:
            for entry in entries:
                display = entry.get('display_name', '')
                if display_mac in display.upper() or normalized_mac in display.upper().replace(':', '').replace('-', ''):
                    if boot_type:
                        if boot_type.upper() in display.upper():
                            matches.append(entry)
                    else:
                        matches.append(entry)

        if not matches:
            raise ValueError(
                f'No boot entry found with MAC {mac_address}'
                + (f' and type {boot_type}' if boot_type else '')
            )

        target = matches[0]
        return self.set_boot_first_by_hex_id(target['hex_id'])
