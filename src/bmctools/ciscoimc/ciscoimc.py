"""High-level Cisco IMC XML API wrapper.

Provides operations for power management, system info, firmware inventory,
boot order, network interfaces, storage, PSU/fan status, and BIOS settings
against a Cisco UCS C-Series rack server via the IMC XML API.
"""

from typing import Optional
from bmctools.ciscoimc.imcapi import ImcApi


class CiscoImc:
    """High-level Cisco IMC operations.

    Args:
        ip: CIMC IP address or hostname.
        username: CIMC username.
        password: CIMC password.
        verify_ssl: Verify SSL certificates (default True).
        port: Override HTTPS port (default None = 443).
    """

    # Valid adminPower values from the RACK-IN.xsd schema
    ADMIN_POWER_ACTIONS = [
        'up', 'down', 'soft-shut-down', 'cycle-immediate',
        'hard-reset-immediate', 'bmc-reset-immediate', 'bmc-reset-default',
        'cmos-reset-immediate', 'diagnostic-interrupt',
    ]

    def __init__(self, ip: str, username: str, password: str,
                 verify_ssl: bool = True, port: Optional[int] = None) -> None:
        self.api = ImcApi(ip, username, password, verify_ssl, port)
        self.ip = ip

    def logout(self) -> None:
        """Terminate the CIMC session."""
        self.api.logout()

    # ── System Information ────────────────────────────────────────────

    def get_system_info(self) -> dict:
        """Retrieve server summary (computeRackUnit).

        Returns:
            Dict of all computeRackUnit attributes (model, serial, memory,
            CPU count, power state, etc.).
        """
        out = self.api.config_resolve_class('computeRackUnit')
        items = self.api.elements_to_list(out)
        if items:
            return items[0]
        return {}

    def get_power_state(self) -> str:
        """Get the current operational power state.

        Returns:
            Power state string (e.g. ``'on'``, ``'off'``).
        """
        info = self.get_system_info()
        return info.get('operPower', 'unknown')

    # ── Power Control ─────────────────────────────────────────────────

    def power_on(self) -> dict:
        """Power on the server.

        Returns:
            Dict of resulting computeRackUnit attributes.
        """
        return self._set_admin_power('up')

    def power_off(self) -> dict:
        """Hard power off the server.

        Returns:
            Dict of resulting computeRackUnit attributes.
        """
        return self._set_admin_power('down')

    def power_off_graceful(self) -> dict:
        """Graceful (ACPI) shutdown of the server.

        Returns:
            Dict of resulting computeRackUnit attributes.
        """
        return self._set_admin_power('soft-shut-down')

    def power_cycle(self) -> dict:
        """Immediate power cycle.

        Returns:
            Dict of resulting computeRackUnit attributes.
        """
        return self._set_admin_power('cycle-immediate')

    def hard_reset(self) -> dict:
        """Immediate hard reset of the server.

        Returns:
            Dict of resulting computeRackUnit attributes.
        """
        return self._set_admin_power('hard-reset-immediate')

    def bmc_reset(self) -> dict:
        """Reset the BMC (CIMC) controller.

        Returns:
            Dict of resulting computeRackUnit attributes.
        """
        return self._set_admin_power('bmc-reset-immediate')

    def bmc_reset_default(self) -> dict:
        """Reset the BMC (CIMC) to factory defaults.

        Returns:
            Dict of resulting computeRackUnit attributes.
        """
        return self._set_admin_power('bmc-reset-default')

    def cmos_reset(self) -> dict:
        """Reset CMOS immediately.

        Returns:
            Dict of resulting computeRackUnit attributes.
        """
        return self._set_admin_power('cmos-reset-immediate')

    def diagnostic_interrupt(self) -> dict:
        """Send a diagnostic interrupt (NMI) to the server.

        Returns:
            Dict of resulting computeRackUnit attributes.
        """
        return self._set_admin_power('diagnostic-interrupt')

    def _set_admin_power(self, action: str) -> dict:
        """Set adminPower on computeRackUnit.

        Args:
            action: One of the ADMIN_POWER_ACTIONS values.

        Returns:
            Dict of resulting computeRackUnit attributes.

        Raises:
            ValueError: If action is not a valid adminPower value.
        """
        if action not in self.ADMIN_POWER_ACTIONS:
            raise ValueError(
                f"Invalid power action '{action}'. "
                f"Valid actions: {', '.join(self.ADMIN_POWER_ACTIONS)}"
            )
        in_config = f'<computeRackUnit adminPower="{action}" dn="sys/rack-unit-1"/>'
        out = self.api.config_conf_mo('sys/rack-unit-1', in_config)
        return self.api.element_to_dict(out.find('computeRackUnit') if out is not None else None)

    # ── Firmware ──────────────────────────────────────────────────────

    def get_firmware_inventory(self) -> list:
        """Retrieve running firmware versions for all components.

        Returns:
            List of dicts with dn, deployment, type, and version fields.
        """
        out = self.api.config_resolve_class('firmwareRunning')
        return self.api.elements_to_list(out)

    def get_bios_firmware(self) -> dict:
        """Get the BIOS firmware version.

        Returns:
            Dict with firmware attributes, or empty dict if not found.
        """
        out = self.api.config_resolve_dn('sys/rack-unit-1/bios/fw-boot-loader')
        if out is not None:
            elem = out.find('firmwareRunning')
            if elem is not None:
                return self.api.element_to_dict(elem)
        return {}

    def get_cimc_firmware(self) -> dict:
        """Get the CIMC (BMC) firmware version.

        Returns:
            Dict with firmware attributes, or empty dict if not found.
        """
        out = self.api.config_resolve_dn('sys/rack-unit-1/mgmt/fw-system')
        if out is not None:
            elem = out.find('firmwareRunning')
            if elem is not None:
                return self.api.element_to_dict(elem)
        return {}

    def get_backup_firmware(self) -> dict:
        """Get the backup firmware version on CIMC.

        Returns:
            Dict with firmwareUpdatable attributes.
        """
        out = self.api.config_resolve_dn('sys/rack-unit-1/mgmt/fw-updatable')
        if out is not None:
            elem = out.find('firmwareUpdatable')
            if elem is not None:
                return self.api.element_to_dict(elem)
        return {}

    def activate_backup_firmware(self, reset_on_activate: bool = True) -> dict:
        """Activate the backup firmware image on CIMC.

        Args:
            reset_on_activate: If True, reset CIMC after activation.

        Returns:
            Dict of resulting firmwareBootUnit attributes.
        """
        reset = 'yes' if reset_on_activate else 'no'
        in_config = (
            f'<firmwareBootUnit dn="sys/rack-unit-1/mgmt/fw-boot-def/bootunit-combined" '
            f'adminState="trigger" image="backup" resetOnActivate="{reset}" />'
        )
        out = self.api.config_conf_mo(
            'sys/rack-unit-1/mgmt/fw-boot-def/bootunit-combined', in_config
        )
        return self.api.element_to_dict(out.find('firmwareBootUnit') if out is not None else None)

    def get_huu_firmware_update_status(self) -> dict:
        """Get the status of a HUU (Host Upgrade Utility) firmware update.

        Returns:
            Dict with updater status and component-level details.
        """
        out = self.api.config_resolve_class('huuFirmwareUpdater', hierarchical=True)
        items = self.api.elements_to_list(out)
        if items:
            return items[0]
        return {}

    # ── Boot Order ────────────────────────────────────────────────────

    def get_boot_order(self) -> dict:
        """Get the current boot order (legacy lsbootDef).

        Returns:
            Dict with boot policy attributes and a ``devices`` list of
            boot device dicts sorted by order.
        """
        # Get the boot policy with children inline
        out = self.api.config_resolve_dn(
            'sys/rack-unit-1/boot-policy', hierarchical=True
        )
        result = {}
        if out is not None:
            elem = out.find('lsbootDef')
            if elem is not None:
                result = self.api.element_to_dict(elem)

        # Also explicitly fetch children in case hierarchical missed them
        if 'children' not in result or not result.get('children'):
            children_out = self.api.config_resolve_children(
                'sys/rack-unit-1/boot-policy'
            )
            devices = self.api.elements_to_list(children_out)
            if devices:
                result['devices'] = sorted(devices, key=lambda d: int(d.get('order', 99)))

        # Normalize: rename 'children' to 'devices' and sort by order
        if 'children' in result:
            result['devices'] = sorted(
                result.pop('children'),
                key=lambda d: int(d.get('order', 99))
            )

        return result

    def get_boot_precision(self) -> dict:
        """Get the precision boot order (UEFI/precision boot policy).

        Returns:
            Dict with lsbootDevPrecision attributes and a ``devices``
            list of boot device dicts sorted by order.
        """
        # Get precision boot policy with children inline
        out = self.api.config_resolve_dn(
            'sys/rack-unit-1/boot-precision', hierarchical=True
        )
        result = {}
        if out is not None:
            elem = out.find('lsbootDevPrecision')
            if elem is not None:
                result = self.api.element_to_dict(elem)

        # Also explicitly fetch children in case hierarchical missed them
        if 'children' not in result or not result.get('children'):
            children_out = self.api.config_resolve_children(
                'sys/rack-unit-1/boot-precision'
            )
            devices = self.api.elements_to_list(children_out)
            if devices:
                result['devices'] = sorted(devices, key=lambda d: int(d.get('order', 99)))

        # Normalize: rename 'children' to 'devices' and sort by order
        if 'children' in result:
            result['devices'] = sorted(
                result.pop('children'),
                key=lambda d: int(d.get('order', 99))
            )

        return result

    def set_boot_order(self, device_order: list, reboot_on_update: bool = False) -> dict:
        """Set the legacy boot order (lsbootDef).

        Args:
            device_order: List of device type strings in desired boot order.
                Valid types: ``storage``, ``lan``, ``efi``, ``vm-read-only``,
                ``vm-read-write``.
            reboot_on_update: If True, reboot immediately after applying.

        Returns:
            Dict of resulting lsbootDef attributes.
        """
        # Map device type keywords to their XML elements
        device_xml_map = {
            'storage': '<lsbootStorage rn="storage-read-write" access="read-write" '
                       'order="{order}" type="storage">'
                       '<lsbootLocalStorage rn="local-storage"/>'
                       '</lsbootStorage>',
            'lan': '<lsbootLan rn="lan-read-only" access="read-only" '
                   'order="{order}" prot="pxe" type="lan"/>',
            'efi': '<lsbootEfi rn="efi-read-only" access="read-only" '
                   'order="{order}" type="efi"/>',
            'vm-read-only': '<lsbootVirtualMedia access="read-only" '
                            'order="{order}" type="virtual-media" rn="vm-read-only"/>',
            'vm-read-write': '<lsbootVirtualMedia access="read-write" '
                             'order="{order}" type="virtual-media" rn="vm-read-write"/>',
        }

        xml_parts = []
        for order, dev_type in enumerate(device_order, 1):
            dev_type = dev_type.strip().lower()
            template = device_xml_map.get(dev_type)
            if not template:
                raise ValueError(
                    f"Unknown boot device type '{dev_type}'. "
                    f"Valid types: {', '.join(device_xml_map.keys())}"
                )
            xml_parts.append(template.format(order=order))

        reboot = 'yes' if reboot_on_update else 'no'
        devices_xml = ''.join(xml_parts)
        in_config = (
            f'<lsbootDef dn="sys/rack-unit-1/boot-policy" '
            f'rebootOnUpdate="{reboot}" status="modified">'
            f'{devices_xml}'
            f'</lsbootDef>'
        )
        out = self.api.config_conf_mo(
            'sys/rack-unit-1/boot-policy', in_config, hierarchical=True
        )
        return self.api.element_to_dict(out.find('lsbootDef') if out is not None else None)

    def set_boot_precision(self, devices_xml: str, reboot_on_update: bool = False) -> dict:
        """Set the precision boot order.

        Args:
            devices_xml: Inner XML string with boot device elements, e.g.
                ``'<lsbootHdd name="hdd1" order="1"/><lsbootPxe name="pxe1" order="2"/>'``
            reboot_on_update: If True, reboot immediately after applying.

        Returns:
            Dict of resulting lsbootDevPrecision attributes.
        """
        reboot = 'yes' if reboot_on_update else 'no'
        in_config = (
            f'<lsbootDevPrecision dn="sys/rack-unit-1/boot-precision" '
            f'rebootOnUpdate="{reboot}" status="modified">'
            f'{devices_xml}'
            f'</lsbootDevPrecision>'
        )
        out = self.api.config_conf_mo('sys/rack-unit-1/boot-precision', in_config)
        return self.api.element_to_dict(out.find('lsbootDevPrecision') if out is not None else None)

    # ── BIOS Settings ────────────────────────────────────────────────

    def get_bios_settings(self) -> list:
        """Get all BIOS token settings.

        Returns:
            List of dicts, one per BIOS setting/token.
        """
        out = self.api.config_resolve_dn('sys/rack-unit-1/bios', hierarchical=True)
        if out is not None:
            return self.api.elements_to_list(out)
        return []

    def get_bios_profile(self) -> dict:
        """Get the BIOS profile/unit info.

        Returns:
            Dict of biosUnit attributes.
        """
        out = self.api.config_resolve_dn('sys/rack-unit-1/bios')
        if out is not None:
            elem = out.find('biosUnit')
            if elem is not None:
                return self.api.element_to_dict(elem)
        return {}

    # ── Network Adapters ─────────────────────────────────────────────

    def get_adaptors(self) -> list:
        """Get all network adaptor units.

        Returns:
            List of dicts with adaptor attributes (model, serial, etc.).
        """
        out = self.api.config_resolve_class('adaptorUnit')
        return self.api.elements_to_list(out)

    def get_adaptor_detail(self, adaptor_id: str = '1') -> dict:
        """Get detailed info for a specific adaptor including child interfaces.

        Args:
            adaptor_id: Adaptor ID (default ``'1'``).

        Returns:
            Dict with adaptor attributes and children.
        """
        dn = f'sys/rack-unit-1/adaptor-{adaptor_id}'
        out = self.api.config_resolve_dn(dn, hierarchical=True)
        if out is not None:
            elem = out.find('adaptorUnit')
            if elem is not None:
                return self.api.element_to_dict(elem)
        return {}

    def get_network_interfaces(self) -> list:
        """Get all external ethernet interfaces across all adaptors.

        Returns:
            List of dicts with interface attributes (mac, linkState, etc.).
        """
        out = self.api.config_resolve_class('adaptorExtEthIf')
        return self.api.elements_to_list(out)

    def get_host_interfaces(self) -> list:
        """Get all host-facing ethernet interfaces (vNICs).

        Returns:
            List of dicts with host interface attributes.
        """
        out = self.api.config_resolve_class('adaptorHostEthIf')
        return self.api.elements_to_list(out)

    def get_vic_ports(self) -> list:
        """Get all VIC port information.

        Returns:
            List of dicts with external ethernet interface attributes.
        """
        return self.get_network_interfaces()

    # ── PSU / Fans / Sensors ─────────────────────────────────────────

    def get_psu(self) -> list:
        """Get power supply unit details.

        Returns:
            List of dicts with PSU attributes (model, power, presence, etc.).
        """
        out = self.api.config_resolve_class('equipmentPsu')
        return self.api.elements_to_list(out)

    def get_fans(self) -> list:
        """Get fan details.

        Returns:
            List of dicts with fan attributes.
        """
        out = self.api.config_resolve_class('equipmentFan')
        return self.api.elements_to_list(out)

    def get_fan_modules(self) -> list:
        """Get fan module details.

        Returns:
            List of dicts with fan module attributes.
        """
        out = self.api.config_resolve_class('equipmentFanModule')
        return self.api.elements_to_list(out)

    def get_temperature_stats(self) -> list:
        """Get temperature sensor readings.

        Returns:
            List of dicts with temperature stats attributes.
        """
        out = self.api.config_resolve_class('processorEnvStats')
        return self.api.elements_to_list(out)

    def get_power_stats(self) -> list:
        """Get power statistics.

        Returns:
            List of dicts with power stats attributes.
        """
        out = self.api.config_resolve_class('computeMbPowerStats')
        return self.api.elements_to_list(out)

    # ── Storage ───────────────────────────────────────────────────────

    def get_storage_controllers(self) -> list:
        """Get storage controller info.

        Returns:
            List of dicts with storage controller attributes.
        """
        out = self.api.config_resolve_class('storageController')
        return self.api.elements_to_list(out)

    def get_local_disks(self) -> list:
        """Get local physical disk info.

        Returns:
            List of dicts with disk attributes (model, health, status, etc.).
        """
        out = self.api.config_resolve_class('storageLocalDisk')
        return self.api.elements_to_list(out)

    def get_virtual_drives(self) -> list:
        """Get virtual drive (RAID volume) info.

        Returns:
            List of dicts with virtual drive attributes.
        """
        out = self.api.config_resolve_class('storageVirtualDrive')
        return self.api.elements_to_list(out)

    # ── CPU / Memory ──────────────────────────────────────────────────

    def get_cpus(self) -> list:
        """Get processor (CPU) info.

        Returns:
            List of dicts with processor attributes.
        """
        out = self.api.config_resolve_class('processorUnit')
        return self.api.elements_to_list(out)

    def get_memory(self) -> list:
        """Get DIMM/memory unit info.

        Returns:
            List of dicts with memory unit attributes.
        """
        out = self.api.config_resolve_class('memoryUnit')
        return self.api.elements_to_list(out)

    # ── PCI Devices ──────────────────────────────────────────────────

    def get_pci_equip_slots(self) -> list:
        """Get PCI equipment slot info.

        Returns:
            List of dicts with PCI slot attributes.
        """
        out = self.api.config_resolve_class('pciEquipSlot')
        return self.api.elements_to_list(out)

    # ── SNMP ──────────────────────────────────────────────────────────

    def get_snmp_config(self) -> dict:
        """Get SNMP configuration.

        Returns:
            Dict with SNMP settings.
        """
        out = self.api.config_resolve_class('commSnmp')
        items = self.api.elements_to_list(out)
        if items:
            return items[0]
        return {}

    # ── Faults / Events ──────────────────────────────────────────────

    def get_faults(self) -> list:
        """Get current fault events.

        Returns:
            List of dicts with fault attributes.
        """
        out = self.api.config_resolve_class('faultInst')
        return self.api.elements_to_list(out)

    # ── Network Settings ─────────────────────────────────────────────

    def get_network_settings(self) -> dict:
        """Get CIMC network settings (IP, VLAN, DNS, etc.).

        Returns:
            Dict with mgmtIf attributes.
        """
        out = self.api.config_resolve_class('mgmtIf')
        items = self.api.elements_to_list(out)
        if items:
            return items[0]
        return {}

    # ── User Management ──────────────────────────────────────────────

    def get_users(self) -> list:
        """Get all local user accounts.

        Returns:
            List of dicts with user attributes (name, priv, status, etc.).
        """
        out = self.api.config_resolve_class('aaaUser')
        return self.api.elements_to_list(out)

    # ── Raw Query ─────────────────────────────────────────────────────

    def resolve_dn(self, dn: str, hierarchical: bool = False) -> dict:
        """Resolve an arbitrary distinguished name.

        Args:
            dn: Distinguished name to query.
            hierarchical: If True, include child objects.

        Returns:
            Dict of the resolved object's attributes.
        """
        out = self.api.config_resolve_dn(dn, hierarchical)
        if out is not None:
            children = list(out)
            if children:
                return self.api.element_to_dict(children[0])
        return {}

    def resolve_class(self, class_id: str, hierarchical: bool = False) -> list:
        """Resolve all objects of an arbitrary class.

        Args:
            class_id: Class identifier.
            hierarchical: If True, include child objects.

        Returns:
            List of dicts for each matching object.
        """
        out = self.api.config_resolve_class(class_id, hierarchical)
        return self.api.elements_to_list(out)
