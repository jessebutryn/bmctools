
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