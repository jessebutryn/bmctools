from bmctools.redfish.fishapi import RedfishAPI

class Redfish:
    """
    Redfish API client for interacting with the Redfish service.

    This class initializes the RedfishAPI and determines the manufacturer-specific
    implementation to use based on the system's manufacturer.
    """
    def __init__(self, ip: str, username: str, password: str, verify_ssl: bool = False):
        self.api = RedfishAPI(ip, username, password, verify_ssl=verify_ssl)
        self.manufacturer = self.get_manufacturer()
        self.manufacturer_class = self.instantiate_manufacturer_class(self.manufacturer)


    def get_manufacturer(self) -> str:
        response = self.api.get('/redfish/v1/Systems/1')
        if response.status_code == 200:
            data = response.json()
            manufacturer = data.get('Manufacturer')
            return manufacturer.lower() if manufacturer else None
        else:
            return None


    def instantiate_manufacturer_class(self, manufacturer: str) -> str|None:
        """Instantiate manufacturer-specific class based on the manufacturer name."""
        if manufacturer == 'supermicro':
            from bmctools.redfish.smcfish import SMCFish
            return SMCFish(self.api)
        else:
            return None
        
    
    def get_boot_options(self) -> list:
        if self.manufacturer_class:
            return self.manufacturer_class.get_boot_options()
        else:
            raise NotImplementedError(f'Boot options retrieval not implemented for manufacturer: {self.manufacturer}')