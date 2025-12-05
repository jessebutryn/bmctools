from typing import Optional
from bmctools.redfish.fishapi import RedfishAPI

class Redfish:
    """
    Redfish API client for interacting with the Redfish service.

    This class initializes the RedfishAPI and determines the manufacturer-specific
    implementation to use based on the system's manufacturer.
    """
    def __init__(self, ip: str, username: str, password: str, verify_ssl: bool = False):
        self.api = RedfishAPI(ip, username, password, verify_ssl=verify_ssl)
        self.system_id = self.get_system_id()
        self.manufacturer = self.get_manufacturer()
        self.manufacturer_class = self.instantiate_manufacturer_class(self.manufacturer)


    def get_system_id(self) -> Optional[str]:
        """Get the system ID from the Systems collection."""
        response = self.api.get('/redfish/v1/Systems')
        if response.status_code == 200:
            try:
                data = response.json()
                members = data.get('Members', [])
                if members and len(members) > 0:
                    # Extract the system ID from the first member's @odata.id
                    # e.g., "/redfish/v1/Systems/System.Embedded.1" -> "System.Embedded.1"
                    odata_id = members[0].get('@odata.id', '')
                    system_id = odata_id.split('/')[-1]
                    return system_id
            except Exception:
                pass
        return None


    def get_manufacturer(self) -> Optional[str]:
        """Get the manufacturer from the system resource."""
        if not self.system_id:
            return None
        
        response = self.api.get(f'/redfish/v1/Systems/{self.system_id}')
        if response.status_code == 200:
            try:
                data = response.json()
                manufacturer = data.get('Manufacturer')
                return manufacturer.lower() if manufacturer else None
            except Exception:
                pass
        return None


    def instantiate_manufacturer_class(self, manufacturer: str) -> Optional[str]:
        """Instantiate manufacturer-specific class based on the manufacturer name."""
        if manufacturer == 'supermicro':
            from bmctools.redfish.smcfish import SMCFish
            return SMCFish(self.api)
        if manufacturer in ['asus', 'asustekcomputerinc.', 'asustek computer inc.']:
            from bmctools.redfish.asusfish import AsusFish
            return AsusFish(self.api)
        else:
            return None
        
    
    def get_boot_options(self) -> list:
        if self.manufacturer_class:
            return self.manufacturer_class.get_boot_options()
        else:
            raise NotImplementedError(f'Boot options retrieval not implemented for manufacturer: {self.manufacturer}')