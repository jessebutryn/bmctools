from typing import Optional
from bmctools.redfish.fishapi import RedfishAPI

class Redfish:
    """
    Redfish API client for interacting with the Redfish service.

    This class initializes the RedfishAPI and determines the manufacturer-specific
    implementation to use based on the system's manufacturer.
    """
    def __init__(self, ip: str, username: str, password: str, verify_ssl: bool = False, manufacturer: Optional[str] = None) -> None:
        """Initialize the Redfish client and detect the manufacturer.

        Args:
            ip: BMC IP address or hostname.
            username: Redfish username.
            password: Redfish password.
            verify_ssl: Whether to verify SSL certificates (default: False).
            manufacturer: Force a specific manufacturer string instead of
                auto-detecting from the system resource.
        """
        self.api = RedfishAPI(ip, username, password, verify_ssl=verify_ssl)
        self.system_id = self.get_system_id()
        self.manufacturer = manufacturer.lower() if manufacturer else self.get_manufacturer()
        self.manufacturer_class = self.instantiate_manufacturer_class(self.manufacturer)

        # Some platforms expose multiple ComputerSystems (e.g. an HGX GPU
        # baseboard alongside the host). Manufacturer classes that resolve the
        # primary compute system themselves expose it as ``system_id``; adopt
        # it so standard-Redfish methods here (boot override, BIOS, inventory)
        # target the same system as the manufacturer-specific ones.
        mc_system_id = getattr(self.manufacturer_class, 'system_id', None)
        if mc_system_id:
            self.system_id = mc_system_id


    def get_system_id(self) -> Optional[str]:
        """Get the system ID from the Redfish Systems collection.

        Queries ``/redfish/v1/Systems`` and extracts the ID segment from the
        first member's ``@odata.id``.

        Returns:
            System ID string (e.g. ``'System.Embedded.1'``, ``'1'``), or
            ``None`` if the collection cannot be read.
        """
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
        """Detect the server manufacturer from the Redfish system resource.

        Reads ``/redfish/v1/Systems/{system_id}`` and returns the lowercased
        ``Manufacturer`` field.

        Returns:
            Lowercased manufacturer string (e.g. ``'dell'``, ``'supermicro'``),
            or ``None`` if unknown or unreachable.
        """
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


    def instantiate_manufacturer_class(self, manufacturer: str) -> Optional[object]:
        """Instantiate the manufacturer-specific Redfish class.

        Args:
            manufacturer: Lowercased manufacturer string (e.g., 'supermicro', 'dell').

        Returns:
            Manufacturer-specific instance (SMCFish, DellFish, etc.), or None if unknown.
        """
        if manufacturer == 'supermicro':
            from bmctools.redfish.smcfish import SMCFish
            return SMCFish(self.api)
        if manufacturer in ['asus', 'asustekcomputerinc.', 'asustek computer inc.']:
            from bmctools.redfish.asusfish import AsusFish
            return AsusFish(self.api)
        if manufacturer in ['dell', 'dell inc.']:
            from bmctools.redfish.dellfish import DellFish
            return DellFish(self.api)
        if manufacturer in ['gigabyte', 'giga computing']:
            from bmctools.redfish.gigafish import GigaFish
            return GigaFish(self.api)
        if manufacturer in ['hpe', 'hp', 'hewlett packard enterprise', 'hewlett-packard enterprise', 'hewlett packard']:
            from bmctools.redfish.hpefish import HpeFish
            return HpeFish(self.api)
        if manufacturer in ['cisco', 'cisco systems inc', 'cisco systems inc.']:
            from bmctools.redfish.ciscofish import CiscoFish
            return CiscoFish(self.api)
        if manufacturer in ['aivres', 'inspur', 'inspur electronic information industry co., ltd.']:
            from bmctools.redfish.aivresfish import AivresFish
            return AivresFish(self.api)
        else:
            return None
        
    
    def get_boot_order(self) -> list:
        """Get the current boot order for the system.

        Returns:
            List of boot option references in order.

        Raises:
            NotImplementedError: If not supported for the detected manufacturer.
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')
        
        try:
            return self.manufacturer_class.get_boot_order()
        except AttributeError:
            raise NotImplementedError(f'Boot order retrieval not implemented for manufacturer: {self.manufacturer}')
        
    
    def get_boot_options(self, nocache: bool = False) -> list:
        """Get all available boot options.

        Args:
            nocache: If True, bypass cached results and query the BMC directly.

        Returns:
            List of boot option dictionaries.

        Raises:
            NotImplementedError: If not supported for the detected manufacturer.
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')
        
        try:
            return self.manufacturer_class.get_boot_options(nocache=nocache)
        except AttributeError:
            raise NotImplementedError(f'Boot options retrieval not implemented for manufacturer: {self.manufacturer}')
        

    def get_boot_option_by_mac(self, mac_address: str, type: Optional[str] = None, nocache: bool = False) -> dict:
        """Find a boot option matching the given MAC address.

        Args:
            mac_address: MAC address to search for.
            type: Optional boot option type filter (e.g., 'PXE').
            nocache: If True, force a fresh query.

        Returns:
            Boot option dict.

        Raises:
            NotImplementedError: If not supported for the detected manufacturer.
            ValueError: If no matching boot option is found.
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')
        
        try:
            return self.manufacturer_class.get_boot_option_by_mac(mac_address, type=type, nocache=nocache)
        except AttributeError:
            raise NotImplementedError(f'Boot option by MAC retrieval not implemented for manufacturer: {self.manufacturer}')
        

    def get_boot_option_by_alias(self, alias: str, nocache: bool = False) -> dict:
        """Find a boot option by display name or alias.

        Args:
            alias: Display name or description substring to match (case-insensitive).
            nocache: If True, force a fresh query.

        Returns:
            Boot option dict.

        Raises:
            NotImplementedError: If not supported for the detected manufacturer.
            ValueError: If no matching boot option is found.
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')
        
        try:
            return self.manufacturer_class.get_boot_option_by_alias(alias, nocache=nocache)
        except AttributeError:
            raise NotImplementedError(f'Boot option by alias retrieval not implemented for manufacturer: {self.manufacturer}')
        
    
    def set_boot_first_by_mac(self, mac_address: str, boot_type: str = None) -> dict:
        """Move the boot option matching a MAC address to the front of the boot order.

        Args:
            mac_address: MAC address of the target NIC.
            boot_type: Optional boot option type filter (e.g., 'PXE').

        Returns:
            Dict with the new boot order and the promoted option.

        Raises:
            NotImplementedError: If not supported for the detected manufacturer.
            ValueError: If no matching boot option is found.
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.set_boot_first_by_mac(mac_address, boot_type=boot_type)
        except AttributeError:
            raise NotImplementedError(f'set_boot_first_by_mac not implemented for manufacturer: {self.manufacturer}')


    def set_boot_order(self, boot_order: list) -> dict:
        """Set the boot order on the system.

        Args:
            boot_order: Ordered list of all boot option references
                        (e.g., ['Boot0003', 'Boot0001', 'Boot0002']).
                        Must include every existing boot option.

        Returns:
            Dict with keys: changed, needs_reboot, previous_boot_order, boot_order.

        Raises:
            NotImplementedError: If not supported for the detected manufacturer.
            ValueError: If the provided list is invalid.
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.set_boot_order(boot_order)
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


    def reset_bmc(self, reset_type: str = None) -> bool:
        """Reset the BMC (Manager).

        Args:
            reset_type: Type of reset (e.g., GracefulRestart, ForceRestart).
                        If None, the manufacturer class will auto-select.

        Returns:
            True if reset command was accepted

        Raises:
            NotImplementedError: If not implemented for the manufacturer
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.reset_bmc(reset_type)
        except AttributeError:
            raise NotImplementedError(f'BMC reset not implemented for manufacturer: {self.manufacturer}')


    def get_supported_bmc_reset_types(self) -> dict:
        """Get supported reset types for the BMC (Manager).

        Returns:
            Dict containing supported BMC reset types

        Raises:
            NotImplementedError: If not implemented for the manufacturer
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.get_supported_bmc_reset_types()
        except AttributeError:
            raise NotImplementedError(f'BMC reset types not implemented for manufacturer: {self.manufacturer}')


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


    def get_network_interfaces(self) -> list:
        """Get NIC / EthernetInterface information.

        Returns:
            List of interface dicts

        Raises:
            NotImplementedError: If not implemented for the manufacturer
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.get_network_interfaces()
        except AttributeError:
            raise NotImplementedError(f'get_network_interfaces not implemented for manufacturer: {self.manufacturer}')


    # ── KCS control (OS-to-BMC in-band IPMI passthrough) ──────────────

    def set_kcs_state(self, enabled: bool) -> dict:
        """Enable or disable the KCS (OS-to-BMC in-band IPMI passthrough) interface.

        Disabling KCS restricts in-band OS-to-BMC control so the BMC can only be
        managed out-of-band. The concrete mechanism is manufacturer-specific
        (Dell toggles an iDRAC attribute; Supermicro lowers the KCS interface
        privilege). ASUS and other manufacturers are not supported.

        Args:
            enabled: ``True`` to enable KCS, ``False`` to disable it.

        Returns:
            Dict describing the applied change.

        Raises:
            NotImplementedError: If not supported for the detected manufacturer.
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.set_kcs_state(enabled)
        except AttributeError:
            raise NotImplementedError(f'KCS control not implemented for manufacturer: {self.manufacturer}')


    def get_kcs_state(self) -> dict:
        """Get the current KCS (OS-to-BMC passthrough) state.

        Returns:
            Dict with ``kcs_enabled`` (bool) and manufacturer-specific detail.

        Raises:
            NotImplementedError: If not supported for the detected manufacturer.
        """
        if not self.manufacturer_class:
            raise NotImplementedError(f'No manufacturer-specific implementation available for: {self.manufacturer}')

        try:
            return self.manufacturer_class.get_kcs_state()
        except AttributeError:
            raise NotImplementedError(f'KCS control not implemented for manufacturer: {self.manufacturer}')


    # ── Boot Source Override (standard Redfish, all manufacturers) ────

    def get_boot_override(self) -> dict:
        """Get the current boot source override configuration.

        This is standard Redfish and works on all manufacturers.

        Returns:
            Dict with current override target, enabled state, and allowable values.
        """
        # Delegate to manufacturer class if it has a custom implementation
        if self.manufacturer_class and hasattr(self.manufacturer_class, 'get_boot_override'):
            return self.manufacturer_class.get_boot_override()

        response = self.api.get(f'/redfish/v1/Systems/{self.system_id}')
        if response.status_code == 200:
            data = response.json()
            boot = data.get('Boot', {})
            result = {
                'override_target': boot.get('BootSourceOverrideTarget', 'None'),
                'override_enabled': boot.get('BootSourceOverrideEnabled', 'Disabled'),
                'allowable_targets': boot.get('BootSourceOverrideTarget@Redfish.AllowableValues', []),
                'allowable_modes': boot.get('BootSourceOverrideEnabled@Redfish.AllowableValues', []),
            }
            if boot.get('UefiTargetBootSourceOverride'):
                result['uefi_target'] = boot['UefiTargetBootSourceOverride']
            if boot.get('BootNext'):
                result['boot_next'] = boot['BootNext']
            return result
        else:
            raise ValueError(f'Failed to get system info, status code: {response.status_code}')


    def set_boot_override(self, target: str, enabled: str = 'Once',
                          uefi_target: str = None) -> bool:
        """Set boot source override to boot from a specific device type.

        This is standard Redfish and works on all manufacturers.

        Args:
            target: Boot source target (e.g., 'Pxe', 'Hdd', 'Cd', 'BiosSetup',
                    'UefiBootNext', 'None')
            enabled: Override mode: 'Once', 'Continuous', or 'Disabled'
            uefi_target: UEFI boot option reference (e.g., 'Boot0002'). Required
                         when target is 'UefiBootNext'.

        Returns:
            True if successful.
        """
        if target == 'UefiBootNext' and not uefi_target:
            raise ValueError("uefi_target is required when target is 'UefiBootNext'")

        if self.manufacturer_class and hasattr(self.manufacturer_class, 'set_boot_override'):
            return self.manufacturer_class.set_boot_override(target, enabled, uefi_target=uefi_target)

        if target == 'UefiBootNext':
            payloads = self._uefi_boot_next_payloads(uefi_target, enabled)
        else:
            payloads = [{
                "Boot": {
                    "BootSourceOverrideTarget": target,
                    "BootSourceOverrideEnabled": enabled,
                }
            }]

        last_response = None
        for payload in payloads:
            response = self.api.patch(f'/redfish/v1/Systems/{self.system_id}', data=payload)
            if response.status_code in [200, 204]:
                return True
            last_response = response

        error_detail = ""
        try:
            import json
            error_data = last_response.json()
            error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
        except:
            error_detail = f"\nResponse text: {last_response.text}"
        raise ValueError(f'Failed to set boot override, status code: {last_response.status_code}{error_detail}')


    def _uefi_boot_next_payloads(self, uefi_target: str, enabled: str) -> list:
        """Return a list of payload variants to try for UefiBootNext, in priority order.

        BMCs vary in which properties they accept:
        1. UefiBootNext + UefiTargetBootSourceOverride (Redfish spec standard)
        2. UefiBootNext + BootNext (some BMCs use BootNext instead)
        3. BootNext alone (BMCs that don't support UefiBootNext as a target at all)
        """
        return [
            {
                "Boot": {
                    "BootSourceOverrideTarget": "UefiBootNext",
                    "BootSourceOverrideEnabled": enabled,
                    "UefiTargetBootSourceOverride": uefi_target,
                }
            },
            {
                "Boot": {
                    "BootSourceOverrideTarget": "UefiBootNext",
                    "BootSourceOverrideEnabled": enabled,
                    "BootNext": uefi_target,
                }
            },
            {
                "Boot": {
                    "BootNext": uefi_target,
                }
            },
        ]


    # ── BIOS Settings (standard Redfish, all manufacturers) ───────────

    def get_bios_settings(self) -> dict:
        """Get current BIOS settings/attributes.

        Returns:
            Dict with BIOS attributes, id, and description.
        """
        if self.manufacturer_class and hasattr(self.manufacturer_class, 'get_bios_settings'):
            return self.manufacturer_class.get_bios_settings()

        response = self.api.get(f'/redfish/v1/Systems/{self.system_id}/Bios')
        if response.status_code == 200:
            data = response.json()
            return {
                'attributes': data.get('Attributes', {}),
                'id': data.get('Id'),
                'description': data.get('Description'),
            }
        else:
            raise ValueError(f'Failed to get BIOS settings, status code: {response.status_code}')


    def get_boot_bios_settings(self) -> dict:
        """Get only boot-related BIOS token settings.

        Filters BIOS attributes to those containing common boot-related keywords.

        Returns:
            Dict of boot-related BIOS attributes.
        """
        if self.manufacturer_class and hasattr(self.manufacturer_class, 'get_boot_bios_settings'):
            return self.manufacturer_class.get_boot_bios_settings()

        bios = self.get_bios_settings()
        attributes = bios.get('attributes', {})

        boot_keywords = ['boot', 'pxe', 'uefi', 'network', 'efi', 'legacy', 'ipv4', 'ipv6']
        boot_attrs = {}
        for key, value in attributes.items():
            if any(kw in key.lower() for kw in boot_keywords):
                boot_attrs[key] = value

        return boot_attrs


    def set_bios_settings(self, attributes: dict) -> bool:
        """Set BIOS attributes (typically applied on next reboot).

        Most vendors use /Bios/Settings for pending BIOS changes.

        Args:
            attributes: Dict of BIOS attribute key/value pairs to set.

        Returns:
            True if the settings were accepted.
        """
        if self.manufacturer_class and hasattr(self.manufacturer_class, 'set_bios_settings'):
            return self.manufacturer_class.set_bios_settings(attributes)

        import json
        settings_uri = f'/redfish/v1/Systems/{self.system_id}/Bios/Settings'

        payload = {
            "Attributes": attributes
        }

        response = self.api.patch(settings_uri, data=payload)
        if response.status_code in [200, 202, 204]:
            return True
        else:
            error_detail = ""
            try:
                error_data = response.json()
                error_detail = f"\nError details: {json.dumps(error_data, indent=2)}"
            except:
                error_detail = f"\nResponse text: {response.text}"
            raise ValueError(f'Failed to set BIOS settings, status code: {response.status_code}{error_detail}')


    def get_system_inventory(self) -> dict:
        """Collect a comprehensive system inventory from Redfish.

        Aggregates system identity, processor/memory summaries, network
        interfaces, firmware inventory, boot order, and boot override into
        a single dict.  Each section is collected independently so a failure
        in one area does not prevent the rest from being returned.

        Returns:
            Dict with inventory sections.  Sections that could not be
            retrieved will have an ``"error"`` value instead.
        """
        inventory: dict = {}

        # ── System identity ────────────────────────────────────────────
        try:
            response = self.api.get(f'/redfish/v1/Systems/{self.system_id}')
            if response.status_code == 200:
                data = response.json()
                inventory['system'] = {
                    'manufacturer': data.get('Manufacturer'),
                    'model': data.get('Model'),
                    'serial_number': data.get('SerialNumber'),
                    'sku': data.get('SKU'),
                    'part_number': data.get('PartNumber'),
                    'uuid': data.get('UUID'),
                    'hostname': data.get('HostName'),
                    'bios_version': data.get('BiosVersion'),
                    'power_state': data.get('PowerState'),
                    'system_type': data.get('SystemType'),
                    'indicator_led': data.get('IndicatorLED'),
                    'status': data.get('Status'),
                }

                # Processor summary
                proc = data.get('ProcessorSummary')
                if proc:
                    inventory['processor_summary'] = {
                        'count': proc.get('Count'),
                        'model': proc.get('Model'),
                        'status': proc.get('Status'),
                    }

                # Memory summary
                mem = data.get('MemorySummary')
                if mem:
                    inventory['memory_summary'] = {
                        'total_gib': mem.get('TotalSystemMemoryGiB'),
                        'status': mem.get('Status'),
                    }
            else:
                inventory['system'] = {'error': f'HTTP {response.status_code}'}
        except Exception as e:
            inventory['system'] = {'error': str(e)}

        # ── BMC / Manager info ─────────────────────────────────────────
        try:
            response = self.api.get('/redfish/v1/Managers')
            if response.status_code == 200:
                members = response.json().get('Members', [])
                if members:
                    mgr_uri = members[0].get('@odata.id', '')
                    mgr_resp = self.api.get(mgr_uri)
                    if mgr_resp.status_code == 200:
                        mgr = mgr_resp.json()
                        inventory['bmc'] = {
                            'id': mgr.get('Id'),
                            'firmware_version': mgr.get('FirmwareVersion'),
                            'manager_type': mgr.get('ManagerType'),
                            'model': mgr.get('Model'),
                            'status': mgr.get('Status'),
                        }
        except Exception as e:
            inventory['bmc'] = {'error': str(e)}

        # ── Network interfaces / MAC addresses ─────────────────────────
        try:
            inventory['network_interfaces'] = self.get_network_interfaces()
        except Exception as e:
            inventory['network_interfaces'] = {'error': str(e)}

        # ── Firmware inventory ─────────────────────────────────────────
        try:
            inventory['firmware'] = self.get_firmware_inventory()
        except Exception as e:
            inventory['firmware'] = {'error': str(e)}

        # ── Boot order ─────────────────────────────────────────────────
        try:
            inventory['boot_order'] = self.get_boot_order()
        except Exception as e:
            inventory['boot_order'] = {'error': str(e)}

        # ── Boot options ───────────────────────────────────────────────
        try:
            inventory['boot_options'] = self.get_boot_options()
        except Exception as e:
            inventory['boot_options'] = {'error': str(e)}

        # ── Boot source override ───────────────────────────────────────
        try:
            inventory['boot_override'] = self.get_boot_override()
        except Exception as e:
            inventory['boot_override'] = {'error': str(e)}

        return inventory


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
