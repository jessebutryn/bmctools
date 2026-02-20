import json
from typing import Optional

class AsusFish:
    """
    ASUS Redfish implementation.
    """
    def __init__(self, fishapi: str):
        self.api = fishapi
        self.boot_options = None


    def get_boot_order(self) -> list:
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
        


    def set_boot_order(self, boot_order: list) -> bool:
        """Set the boot order for the system.
        
        Args:
            boot_order: List of boot option references (e.g., ["Boot0003", "Boot0004", ...])
                        Must include ALL boot options, not just a subset.
        
        Returns:
            True if successful
            
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
            return True
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
