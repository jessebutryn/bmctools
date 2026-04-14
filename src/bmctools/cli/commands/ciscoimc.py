"""Cisco IMC XML API command handlers."""

import argparse
import sys
from bmctools.cli.utils import (
    establish_ciscoimc_connection,
    print_verbose,
)
from bmctools.cli.commands.common import wrap_command


def setup_ciscoimc_commands(parser: argparse.ArgumentParser) -> None:
    """Setup Cisco IMC XML API subcommands.

    Args:
        parser: ciscoimc subparser
    """
    subparsers = parser.add_subparsers(dest='ciscoimc_group', help='Cisco IMC operation group')

    # System info
    subparsers.add_parser('system', help='System information')

    # Power management
    power_parser = subparsers.add_parser('power', help='Power management')
    setup_power_commands(power_parser)

    # Firmware
    firmware_parser = subparsers.add_parser('firmware', help='Firmware management')
    setup_firmware_commands(firmware_parser)

    # Boot order
    boot_parser = subparsers.add_parser('boot', help='Boot order management')
    setup_boot_commands(boot_parser)

    # BIOS
    bios_parser = subparsers.add_parser('bios', help='BIOS settings')
    setup_bios_commands(bios_parser)

    # Inventory (adaptors, NICs, storage, CPU, memory, PCI)
    inventory_parser = subparsers.add_parser('inventory', help='Hardware inventory')
    setup_inventory_commands(inventory_parser)

    # Sensors (PSU, fans, temperature, power stats)
    sensor_parser = subparsers.add_parser('sensor', help='Sensors and health')
    setup_sensor_commands(sensor_parser)

    # Network settings
    subparsers.add_parser('network', help='CIMC network settings')

    # Users
    subparsers.add_parser('users', help='Local user accounts')

    # Faults
    subparsers.add_parser('faults', help='Current fault events')

    # SNMP
    subparsers.add_parser('snmp', help='SNMP configuration')

    # Raw query
    raw_parser = subparsers.add_parser('raw', help='Raw XML API query')
    setup_raw_commands(raw_parser)


def setup_power_commands(parser: argparse.ArgumentParser) -> None:
    """Setup power management subcommands."""
    subparsers = parser.add_subparsers(dest='power_action', help='Power action')

    subparsers.add_parser('status', help='Get power status')
    subparsers.add_parser('on', help='Power on')
    subparsers.add_parser('off', help='Hard power off')
    subparsers.add_parser('off-graceful', help='Graceful (ACPI) shutdown')
    subparsers.add_parser('cycle', help='Power cycle')
    subparsers.add_parser('hard-reset', help='Hard reset')
    subparsers.add_parser('bmc-reset', help='Reset the BMC (CIMC)')
    subparsers.add_parser('bmc-reset-default', help='Reset BMC to factory defaults')
    subparsers.add_parser('cmos-reset', help='Reset CMOS')
    subparsers.add_parser('diagnostic-interrupt', help='Send diagnostic interrupt (NMI)')


def setup_firmware_commands(parser: argparse.ArgumentParser) -> None:
    """Setup firmware management subcommands."""
    subparsers = parser.add_subparsers(dest='firmware_action', help='Firmware action')

    subparsers.add_parser('list', help='List all running firmware versions')
    subparsers.add_parser('bios', help='Get BIOS firmware version')
    subparsers.add_parser('cimc', help='Get CIMC firmware version')
    subparsers.add_parser('backup', help='Get backup firmware info')

    p = subparsers.add_parser('activate-backup', help='Activate backup firmware image')
    p.add_argument('--no-reset', action='store_true',
                   help='Do not reset CIMC after activation')

    subparsers.add_parser('huu-status', help='Get HUU firmware update status')


def setup_boot_commands(parser: argparse.ArgumentParser) -> None:
    """Setup boot order subcommands."""
    subparsers = parser.add_subparsers(dest='boot_action', help='Boot action')

    subparsers.add_parser('get-order', help='Get legacy boot order')

    p = subparsers.add_parser('set-order', help='Set legacy boot order')
    p.add_argument('-d', '--devices', required=True,
                   help='Comma-separated boot device types in order '
                        '(e.g. "storage,lan,efi"). '
                        'Valid types: storage, lan, efi, vm-read-only, vm-read-write')
    p.add_argument('--reboot', action='store_true',
                   help='Reboot immediately after applying')

    subparsers.add_parser('get-precision', help='Get precision boot order')

    p = subparsers.add_parser('set-precision', help='Set precision boot order')
    p.add_argument('-d', '--devices', required=True,
                   help='Comma-separated boot devices as type:name pairs in order '
                        '(e.g. "LOCALHDD:hdd1,PXE:pxe1,VMEDIA:cdrom1")')
    p.add_argument('--reboot', action='store_true',
                   help='Reboot immediately after applying')


def setup_bios_commands(parser: argparse.ArgumentParser) -> None:
    """Setup BIOS subcommands."""
    subparsers = parser.add_subparsers(dest='bios_action', help='BIOS action')

    subparsers.add_parser('get', help='Get all BIOS settings')
    subparsers.add_parser('profile', help='Get BIOS profile/unit info')


def setup_inventory_commands(parser: argparse.ArgumentParser) -> None:
    """Setup hardware inventory subcommands."""
    subparsers = parser.add_subparsers(dest='inventory_action', help='Inventory action')

    subparsers.add_parser('adaptors', help='List network adaptors')

    p = subparsers.add_parser('adaptor-detail', help='Detailed adaptor info')
    p.add_argument('--id', default='1', help='Adaptor ID (default: 1)')

    subparsers.add_parser('nics', help='List external ethernet interfaces')
    subparsers.add_parser('host-interfaces', help='List host-facing interfaces (vNICs)')
    subparsers.add_parser('storage-controllers', help='List storage controllers')
    subparsers.add_parser('local-disks', help='List local physical disks')
    subparsers.add_parser('virtual-drives', help='List virtual drives (RAID volumes)')
    subparsers.add_parser('cpus', help='List processors')
    subparsers.add_parser('memory', help='List DIMM/memory units')
    subparsers.add_parser('pci', help='List PCI equipment slots')


def setup_sensor_commands(parser: argparse.ArgumentParser) -> None:
    """Setup sensor/health subcommands."""
    subparsers = parser.add_subparsers(dest='sensor_action', help='Sensor action')

    subparsers.add_parser('psu', help='Power supply unit details')
    subparsers.add_parser('fans', help='Fan details')
    subparsers.add_parser('fan-modules', help='Fan module details')
    subparsers.add_parser('temperature', help='Temperature sensor readings')
    subparsers.add_parser('power-stats', help='Power statistics')


def setup_raw_commands(parser: argparse.ArgumentParser) -> None:
    """Setup raw query subcommands."""
    subparsers = parser.add_subparsers(dest='raw_action', help='Raw query action')

    p = subparsers.add_parser('resolve-dn', help='Resolve a distinguished name')
    p.add_argument('dn', help='Distinguished name (e.g. sys/rack-unit-1)')
    p.add_argument('--hierarchical', '-H', action='store_true',
                   help='Include child objects')

    p = subparsers.add_parser('resolve-class', help='Resolve all objects of a class')
    p.add_argument('class_id', help='Class ID (e.g. computeRackUnit, firmwareRunning)')
    p.add_argument('--hierarchical', '-H', action='store_true',
                   help='Include child objects')


# ── Handlers ──────────────────────────────────────────────────────────

def handle_system(args: argparse.Namespace) -> dict:
    """Handle 'ciscoimc system' command."""
    imc = establish_ciscoimc_connection(args)
    return imc.get_system_info()


# Power handlers

def handle_power_status(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    state = imc.get_power_state()
    return {'power_state': state}


def handle_power_on(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    print_verbose("Powering on system...", args)
    result = imc.power_on()
    return {'message': 'Power on command sent', 'result': result}


def handle_power_off(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    print_verbose("Powering off system...", args)
    result = imc.power_off()
    return {'message': 'Power off command sent', 'result': result}


def handle_power_off_graceful(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    print_verbose("Graceful shutdown...", args)
    result = imc.power_off_graceful()
    return {'message': 'Graceful shutdown command sent', 'result': result}


def handle_power_cycle(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    print_verbose("Power cycling system...", args)
    result = imc.power_cycle()
    return {'message': 'Power cycle command sent', 'result': result}


def handle_hard_reset(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    print_verbose("Hard resetting system...", args)
    result = imc.hard_reset()
    return {'message': 'Hard reset command sent', 'result': result}


def handle_bmc_reset(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    print_verbose("Resetting BMC (CIMC)...", args)
    result = imc.bmc_reset()
    return {'message': 'BMC reset command sent', 'result': result}


def handle_bmc_reset_default(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    print_verbose("Resetting BMC to factory defaults...", args)
    result = imc.bmc_reset_default()
    return {'message': 'BMC factory reset command sent', 'result': result}


def handle_cmos_reset(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    print_verbose("Resetting CMOS...", args)
    result = imc.cmos_reset()
    return {'message': 'CMOS reset command sent', 'result': result}


def handle_diagnostic_interrupt(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    print_verbose("Sending diagnostic interrupt...", args)
    result = imc.diagnostic_interrupt()
    return {'message': 'Diagnostic interrupt sent', 'result': result}


# Firmware handlers

def handle_firmware_list(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    firmware = imc.get_firmware_inventory()
    return {'firmware_count': len(firmware), 'firmware': firmware}


def handle_firmware_bios(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    return imc.get_bios_firmware()


def handle_firmware_cimc(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    return imc.get_cimc_firmware()


def handle_firmware_backup(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    return imc.get_backup_firmware()


def handle_firmware_activate_backup(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    reset = not getattr(args, 'no_reset', False)
    print_verbose(f"Activating backup firmware (reset={reset})...", args)
    result = imc.activate_backup_firmware(reset_on_activate=reset)
    return {'message': 'Backup firmware activation triggered', 'result': result}


def handle_firmware_huu_status(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    return imc.get_huu_firmware_update_status()


# Boot handlers

def handle_boot_get_order(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    return imc.get_boot_order()


def handle_boot_set_order(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    reboot = getattr(args, 'reboot', False)
    devices = [d.strip() for d in args.devices.split(',') if d.strip()]
    print_verbose(f"Setting boot order: {devices}", args)
    result = imc.set_boot_order(devices, reboot_on_update=reboot)
    return {'message': 'Boot order updated', 'result': result}


def handle_boot_get_precision(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    return imc.get_boot_precision()


def handle_boot_set_precision(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    reboot = getattr(args, 'reboot', False)

    # Parse "TYPE:name,TYPE:name,..." into XML boot device elements
    # Supported types from the Cisco IMC schema:
    #   LOCALHDD -> lsbootHdd
    #   PXE      -> lsbootPxe
    #   VMEDIA   -> lsbootVMedia
    #   EFI      -> lsbootEfi
    #   ISCSI    -> lsbootIscsi
    #   SAN      -> lsbootSan
    #   UEFISHELL -> lsbootUefiShell
    type_to_tag = {
        'LOCALHDD': 'lsbootHdd',
        'PXE': 'lsbootPxe',
        'VMEDIA': 'lsbootVMedia',
        'EFI': 'lsbootEfi',
        'ISCSI': 'lsbootIscsi',
        'SAN': 'lsbootSan',
        'UEFISHELL': 'lsbootUefiShell',
    }

    entries = [e.strip() for e in args.devices.split(',') if e.strip()]
    xml_parts = []
    for order, entry in enumerate(entries, 1):
        if ':' not in entry:
            raise ValueError(
                f"Invalid device format '{entry}'. Use TYPE:name "
                f"(e.g. LOCALHDD:hdd1). Valid types: {', '.join(type_to_tag.keys())}"
            )
        dev_type, name = entry.split(':', 1)
        dev_type = dev_type.strip().upper()
        name = name.strip()
        tag = type_to_tag.get(dev_type)
        if not tag:
            raise ValueError(
                f"Unknown device type '{dev_type}'. "
                f"Valid types: {', '.join(type_to_tag.keys())}"
            )
        xml_parts.append(f'<{tag} name="{name}" type="{dev_type}" order="{order}"/>')

    devices_xml = ''.join(xml_parts)
    print_verbose(f"Setting boot order: {entries}", args)
    result = imc.set_boot_precision(devices_xml, reboot_on_update=reboot)
    return {'message': 'Boot order updated', 'result': result}


# BIOS handlers

def handle_bios_get(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    settings = imc.get_bios_settings()
    return {'bios_settings': settings}


def handle_bios_profile(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    return imc.get_bios_profile()


# Inventory handlers

def handle_inventory_adaptors(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    adaptors = imc.get_adaptors()
    return {'adaptor_count': len(adaptors), 'adaptors': adaptors}


def handle_inventory_adaptor_detail(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    adaptor_id = getattr(args, 'id', '1')
    return imc.get_adaptor_detail(adaptor_id)


def handle_inventory_nics(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    nics = imc.get_network_interfaces()
    return {'nic_count': len(nics), 'nics': nics}


def handle_inventory_host_interfaces(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    ifaces = imc.get_host_interfaces()
    return {'interface_count': len(ifaces), 'interfaces': ifaces}


def handle_inventory_storage_controllers(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    controllers = imc.get_storage_controllers()
    return {'controller_count': len(controllers), 'controllers': controllers}


def handle_inventory_local_disks(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    disks = imc.get_local_disks()
    return {'disk_count': len(disks), 'disks': disks}


def handle_inventory_virtual_drives(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    drives = imc.get_virtual_drives()
    return {'drive_count': len(drives), 'drives': drives}


def handle_inventory_cpus(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    cpus = imc.get_cpus()
    return {'cpu_count': len(cpus), 'cpus': cpus}


def handle_inventory_memory(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    memory = imc.get_memory()
    return {'dimm_count': len(memory), 'memory': memory}


def handle_inventory_pci(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    pci = imc.get_pci_equip_slots()
    return {'pci_slot_count': len(pci), 'pci_slots': pci}


# Sensor handlers

def handle_sensor_psu(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    psu = imc.get_psu()
    return {'psu_count': len(psu), 'psu': psu}


def handle_sensor_fans(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    fans = imc.get_fans()
    return {'fan_count': len(fans), 'fans': fans}


def handle_sensor_fan_modules(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    modules = imc.get_fan_modules()
    return {'module_count': len(modules), 'fan_modules': modules}


def handle_sensor_temperature(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    temps = imc.get_temperature_stats()
    return {'sensor_count': len(temps), 'temperature': temps}


def handle_sensor_power_stats(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    stats = imc.get_power_stats()
    return {'stats': stats}


# Standalone command handlers

def handle_network(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    return imc.get_network_settings()


def handle_users(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    users = imc.get_users()
    return {'user_count': len(users), 'users': users}


def handle_faults(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    faults = imc.get_faults()
    return {'fault_count': len(faults), 'faults': faults}


def handle_snmp(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    return imc.get_snmp_config()


# Raw handlers

def handle_raw_resolve_dn(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    hier = getattr(args, 'hierarchical', False)
    return imc.resolve_dn(args.dn, hierarchical=hier)


def handle_raw_resolve_class(args: argparse.Namespace) -> dict:
    imc = establish_ciscoimc_connection(args)
    hier = getattr(args, 'hierarchical', False)
    results = imc.resolve_class(args.class_id, hierarchical=hier)
    return {'count': len(results), 'objects': results}


# ── Dispatch ──────────────────────────────────────────────────────────

def dispatch(args: argparse.Namespace) -> int:
    """Dispatch Cisco IMC command to appropriate handler.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    group = args.ciscoimc_group

    if group == 'system':
        return wrap_command(handle_system, args)
    elif group == 'power':
        return dispatch_power(args)
    elif group == 'firmware':
        return dispatch_firmware(args)
    elif group == 'boot':
        return dispatch_boot(args)
    elif group == 'bios':
        return dispatch_bios(args)
    elif group == 'inventory':
        return dispatch_inventory(args)
    elif group == 'sensor':
        return dispatch_sensor(args)
    elif group == 'network':
        return wrap_command(handle_network, args)
    elif group == 'users':
        return wrap_command(handle_users, args)
    elif group == 'faults':
        return wrap_command(handle_faults, args)
    elif group == 'snmp':
        return wrap_command(handle_snmp, args)
    elif group == 'raw':
        return dispatch_raw(args)
    else:
        print(f"Error: Unknown ciscoimc group: {group}", file=sys.stderr)
        return 1


def dispatch_power(args: argparse.Namespace) -> int:
    action = args.power_action
    handlers = {
        'status': handle_power_status,
        'on': handle_power_on,
        'off': handle_power_off,
        'off-graceful': handle_power_off_graceful,
        'cycle': handle_power_cycle,
        'hard-reset': handle_hard_reset,
        'bmc-reset': handle_bmc_reset,
        'bmc-reset-default': handle_bmc_reset_default,
        'cmos-reset': handle_cmos_reset,
        'diagnostic-interrupt': handle_diagnostic_interrupt,
    }
    if action in handlers:
        return wrap_command(handlers[action], args)
    print(f"Error: Unknown power action: {action}", file=sys.stderr)
    return 1


def dispatch_firmware(args: argparse.Namespace) -> int:
    action = args.firmware_action
    handlers = {
        'list': handle_firmware_list,
        'bios': handle_firmware_bios,
        'cimc': handle_firmware_cimc,
        'backup': handle_firmware_backup,
        'activate-backup': handle_firmware_activate_backup,
        'huu-status': handle_firmware_huu_status,
    }
    if action in handlers:
        return wrap_command(handlers[action], args)
    print(f"Error: Unknown firmware action: {action}", file=sys.stderr)
    return 1


def dispatch_boot(args: argparse.Namespace) -> int:
    action = args.boot_action
    handlers = {
        'get-order': handle_boot_get_order,
        'set-order': handle_boot_set_order,
        'get-precision': handle_boot_get_precision,
        'set-precision': handle_boot_set_precision,
    }
    if action in handlers:
        return wrap_command(handlers[action], args)
    print(f"Error: Unknown boot action: {action}", file=sys.stderr)
    return 1


def dispatch_bios(args: argparse.Namespace) -> int:
    action = args.bios_action
    handlers = {
        'get': handle_bios_get,
        'profile': handle_bios_profile,
    }
    if action in handlers:
        return wrap_command(handlers[action], args)
    print(f"Error: Unknown bios action: {action}", file=sys.stderr)
    return 1


def dispatch_inventory(args: argparse.Namespace) -> int:
    action = args.inventory_action
    handlers = {
        'adaptors': handle_inventory_adaptors,
        'adaptor-detail': handle_inventory_adaptor_detail,
        'nics': handle_inventory_nics,
        'host-interfaces': handle_inventory_host_interfaces,
        'storage-controllers': handle_inventory_storage_controllers,
        'local-disks': handle_inventory_local_disks,
        'virtual-drives': handle_inventory_virtual_drives,
        'cpus': handle_inventory_cpus,
        'memory': handle_inventory_memory,
        'pci': handle_inventory_pci,
    }
    if action in handlers:
        return wrap_command(handlers[action], args)
    print(f"Error: Unknown inventory action: {action}", file=sys.stderr)
    return 1


def dispatch_sensor(args: argparse.Namespace) -> int:
    action = args.sensor_action
    handlers = {
        'psu': handle_sensor_psu,
        'fans': handle_sensor_fans,
        'fan-modules': handle_sensor_fan_modules,
        'temperature': handle_sensor_temperature,
        'power-stats': handle_sensor_power_stats,
    }
    if action in handlers:
        return wrap_command(handlers[action], args)
    print(f"Error: Unknown sensor action: {action}", file=sys.stderr)
    return 1


def dispatch_raw(args: argparse.Namespace) -> int:
    action = args.raw_action
    handlers = {
        'resolve-dn': handle_raw_resolve_dn,
        'resolve-class': handle_raw_resolve_class,
    }
    if action in handlers:
        return wrap_command(handlers[action], args)
    print(f"Error: Unknown raw action: {action}", file=sys.stderr)
    return 1


def handle_alias(args: argparse.Namespace, target: str) -> int:
    """Handle aliased commands.

    Args:
        args: Parsed arguments
        target: Alias target identifier

    Returns:
        Exit code
    """
    alias_handlers = {
        'ciscoimc_system': handle_system,
        'ciscoimc_power_status': handle_power_status,
        'ciscoimc_power_on': handle_power_on,
        'ciscoimc_power_off': handle_power_off,
        'ciscoimc_power_cycle': handle_power_cycle,
        'ciscoimc_firmware_list': handle_firmware_list,
    }
    if target in alias_handlers:
        return wrap_command(alias_handlers[target], args)
    print(f"Error: Unknown ciscoimc alias: {target}", file=sys.stderr)
    return 1
