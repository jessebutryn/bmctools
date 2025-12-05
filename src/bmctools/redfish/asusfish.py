import json

class AsusFish:
    """
    ASUS Redfish implementation.
    """
    def __init__(self, fishapi: str):
        self.api = fishapi

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
        
    def get_boot_options(self) -> list:
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
            return boot_options
        else:
            raise ValueError(f'Failed to retrieve boot options, status code: {response.status_code}')
        
    def set_boot_order(self, boot_order: list) -> bool:
        # ASUS uses FutureState (SD) URI for boot configuration changes
        # First, get the current ETag from the SD endpoint
        sd_endpoint = '/redfish/v1/Systems/Self/SD'
        get_response = self.api.get(sd_endpoint)
        if get_response.status_code != 200:
            raise ValueError(f'Failed to get current system state, status code: {get_response.status_code}')
        
        etag = get_response.headers.get('ETag')
        if not etag:
            raise ValueError('ETag header not found in response')
        
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