from typing import Optional
from bmctools.redfish.fishapi import RedfishAPI

class Redfish:
    """
    Redfish API client for interacting with the Redfish service.

    This class initializes the RedfishAPI and determines the manufacturer-specific
    implementation to use based on the system's manufacturer.
    """
    def __init__(self, ip: str, username: str, password: str, verify_ssl: bool = False, manufacturer: Optional[str] = None):
        self.api = RedfishAPI(ip, username, password, verify_ssl=verify_ssl)
        self.system_id = self.get_system_id()
        self.manufacturer = manufacturer.lower() if manufacturer else self.get_manufacturer()
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
        if manufacturer in ['dell inc.']:
            from bmctools.redfish.dellfish import DellFish
            return DellFish(self.api)
        else:
            return None
        
    
    def get_boot_order(self) -> list:
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')
        
        try:
            return self.manufacturer_class.get_boot_order()
        except AttributeError:
            raise NotImplementedError(f'Boot order retrieval not implemented for manufacturer: {self.manufacturer}')
        
    
    def get_boot_options(self, nocache: bool = False) -> list:
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')
        
        try:
            return self.manufacturer_class.get_boot_options(nocache=nocache)
        except AttributeError:
            raise NotImplementedError(f'Boot options retrieval not implemented for manufacturer: {self.manufacturer}')
        

    def get_boot_option_by_mac(self, mac_address: str, type: Optional[str] = None, nocache: bool = False) -> dict:
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')
        
        try:
            return self.manufacturer_class.get_boot_option_by_mac(mac_address, type=type, nocache=nocache)
        except AttributeError:
            raise NotImplementedError(f'Boot option by MAC retrieval not implemented for manufacturer: {self.manufacturer}')
        

    def get_boot_option_by_alias(self, alias: str, nocache: bool = False) -> dict:
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')
        
        try:
            return self.manufacturer_class.get_boot_option_by_alias(alias, nocache=nocache)
        except AttributeError:
            raise NotImplementedError(f'Boot option by alias retrieval not implemented for manufacturer: {self.manufacturer}')
        
    
    def set_boot_order(self, boot_order: list) -> None:
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            self.manufacturer_class.set_boot_order(boot_order)
        except AttributeError:
            raise NotImplementedError(f'Setting boot order not implemented for manufacturer: {self.manufacturer}')


    def reset_system(self, reset_type: str = None) -> bool:
        """Reset/reboot the system.

        Args:
            reset_type: Type of reset (e.g., GracefulRestart, ForceRestart, ForceOff, On).
                        If None, the manufacturer class will auto-select.

        Returns:
            True if reset command was accepted

        Raises:
            NotImplementedError: If not implemented for the manufacturer
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.reset_system(reset_type)
        except AttributeError:
            raise NotImplementedError(f'System reset not implemented for manufacturer: {self.manufacturer}')


    def get_supported_reset_types(self) -> dict:
        """Get supported reset types for this system.

        Returns:
            Dict containing supported reset types

        Raises:
            NotImplementedError: If not implemented for the manufacturer
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.get_supported_reset_types()
        except AttributeError:
            raise NotImplementedError(f'Reset types not implemented for manufacturer: {self.manufacturer}')


    def get_firmware_inventory(self) -> dict:
        """Get firmware inventory (BIOS, BMC versions, etc.).

        Returns:
            Dict containing firmware inventory information

        Raises:
            NotImplementedError: If not implemented for the manufacturer
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.get_firmware_inventory()
        except AttributeError:
            raise NotImplementedError(f'Firmware inventory not implemented for manufacturer: {self.manufacturer}')


    def get_update_service_info(self) -> dict:
        """Get UpdateService information and current update status.

        Returns:
            Dict containing UpdateService status and configuration

        Raises:
            NotImplementedError: If not implemented for the manufacturer
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.get_update_service_info()
        except AttributeError:
            raise NotImplementedError(f'Update service info not implemented for manufacturer: {self.manufacturer}')


    def update_bmc_firmware(self, firmware_path: str, preserve_config: bool = True) -> dict:
        """Update BMC firmware.

        Args:
            firmware_path: Path to the BMC firmware file
            preserve_config: Whether to preserve BMC configuration (default: True)

        Returns:
            Dict containing update status information

        Raises:
            NotImplementedError: If not implemented for the manufacturer
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.update_bmc_firmware(firmware_path, preserve_config=preserve_config)
        except AttributeError:
            raise NotImplementedError(f'BMC firmware update not implemented for manufacturer: {self.manufacturer}')


    def update_bios_firmware(self, firmware_path: str) -> dict:
        """Update BIOS firmware.

        Args:
            firmware_path: Path to the BIOS firmware file

        Returns:
            Dict containing update status information

        Raises:
            NotImplementedError: If not implemented for the manufacturer
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.update_bios_firmware(firmware_path)
        except AttributeError:
            raise NotImplementedError(f'BIOS firmware update not implemented for manufacturer: {self.manufacturer}')
