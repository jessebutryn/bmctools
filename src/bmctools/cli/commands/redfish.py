"""Redfish command handlers."""

import sys
from bmctools.cli.utils import (
    establish_redfish_connection,
    handle_error,
    get_exit_code,
    print_verbose,
    EXIT_SUCCESS,
)
from bmctools.cli.commands.common import (
    read_file_lines,
    parse_comma_list,
    validate_file_exists,
    wrap_command,
)
from bmctools.cli.formatters import format_output


def setup_redfish_commands(parser):
    """Setup Redfish subcommands.

    Args:
        parser: Redfish subparser
    """
    subparsers = parser.add_subparsers(dest='redfish_group', help='Redfish operation group')

    # Boot management commands
    boot_parser = subparsers.add_parser('boot', help='Boot management')
    setup_boot_commands(boot_parser)

    # Firmware management commands
    firmware_parser = subparsers.add_parser('firmware', help='Firmware management')
    setup_firmware_commands(firmware_parser)

    # System management commands
    system_parser = subparsers.add_parser('system', help='System management')
    setup_system_commands(system_parser)

    # TPM management commands (ASUS)
    tpm_parser = subparsers.add_parser('tpm', help='TPM management (ASUS)')
    setup_tpm_commands(tpm_parser)

    # Dell-specific commands
    dell_parser = subparsers.add_parser('dell', help='Dell-specific commands')
    setup_dell_commands(dell_parser)


def setup_boot_commands(parser):
    """Setup boot management subcommands."""
    subparsers = parser.add_subparsers(dest='boot_action', help='Boot action')

    # get-order
    p = subparsers.add_parser('get-order', help='Get current boot order')
    p.add_argument('--staged', action='store_true',
                  help='Show staged/pending boot order instead of current (ASUS /SD endpoint)')

    # set-order
    p = subparsers.add_parser('set-order', help='Set boot order')
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('-o', '--order',
                      help='Comma-separated boot order (e.g., "Boot0003,Boot0004,Boot0000")')
    group.add_argument('--order-file',
                      help='File containing boot order (one entry per line)')

    # list-options
    p = subparsers.add_parser('list-options', help='List all boot options')
    p.add_argument('--no-cache', action='store_true',
                  help='Force fresh query (bypass cache)')

    # find-by-mac
    p = subparsers.add_parser('find-by-mac', help='Find boot option by MAC address')
    p.add_argument('-m', '--mac', required=True,
                  help='MAC address (e.g., 10:70:FD:29:E5:22)')
    p.add_argument('--type',
                  help='Boot option type filter (e.g., PXE)')
    p.add_argument('--no-cache', action='store_true',
                  help='Force fresh query (bypass cache)')

    # find-by-alias
    p = subparsers.add_parser('find-by-alias', help='Find boot option by alias/name')
    p.add_argument('-a', '--alias', required=True,
                  help='Boot option alias')
    p.add_argument('--no-cache', action='store_true',
                  help='Force fresh query (bypass cache)')

    # get-pending
    subparsers.add_parser('get-pending', help='Get pending boot order (ASUS FutureState)')


def setup_firmware_commands(parser):
    """Setup firmware management subcommands."""
    subparsers = parser.add_subparsers(dest='firmware_action', help='Firmware action')

    # inventory
    subparsers.add_parser('inventory', help='Get firmware inventory')

    # status
    subparsers.add_parser('status', help='Get update service status')

    # update-bios
    p = subparsers.add_parser('update-bios', help='Update BIOS firmware')
    p.add_argument('-f', '--file', required=True,
                  help='Path to BIOS firmware file')

    # update-bmc
    p = subparsers.add_parser('update-bmc', help='Update BMC firmware')
    p.add_argument('-f', '--file', required=True,
                  help='Path to BMC firmware file')
    p.add_argument('--no-preserve-config', action='store_true',
                  help='Do not preserve BMC configuration')


def setup_system_commands(parser):
    """Setup system management subcommands."""
    subparsers = parser.add_subparsers(dest='system_action', help='System action')

    # reset
    p = subparsers.add_parser('reset', help='Reset/reboot system')
    p.add_argument('--type', dest='reset_type',
                  help='Reset type (e.g., GracefulRestart, ForceRestart)')

    # reset-types
    subparsers.add_parser('reset-types', help='List supported reset types')

    # info
    subparsers.add_parser('info', help='Get system information')


def setup_tpm_commands(parser):
    """Setup TPM management subcommands."""
    subparsers = parser.add_subparsers(dest='tpm_action', help='TPM action')

    # set-state
    p = subparsers.add_parser('set-state', help='Set TPM state')
    p.add_argument('--state', required=True,
                  choices=['Enabled', 'Disabled'],
                  help='TPM state')


def setup_dell_commands(parser):
    """Setup Dell-specific subcommands."""
    subparsers = parser.add_subparsers(dest='dell_action', help='Dell action')

    # onetime-boot
    p = subparsers.add_parser('onetime-boot', help='Set one-time boot source')
    p.add_argument('--source', required=True,
                  help='Boot source (e.g., Pxe, Cd, Hdd)')

    # create-role
    p = subparsers.add_parser('create-role', help='Create user role/group')
    p.add_argument('--name', required=True,
                  help='Role name')
    p.add_argument('--privileges', required=True,
                  help='Privilege bitmask')

    # get-boot-options
    p = subparsers.add_parser('get-boot-options', help='Get Dell boot options')
    p.add_argument('--no-cache', action='store_true',
                  help='Force fresh query (bypass cache)')

    # get-nics
    subparsers.add_parser('get-nics', help='Get NIC information and MAC addresses')

    # get-nic-attrs
    p = subparsers.add_parser('get-nic-attrs', help='Get OEM network attributes for a NIC by MAC')
    p.add_argument('-m', '--mac', required=True,
                  help='MAC address of the NIC (e.g., 04:32:01:D8:C0:B0)')

    # boot-first-by-mac
    p = subparsers.add_parser('boot-first-by-mac', help='Move a NIC to the front of the boot order by MAC')
    p.add_argument('-m', '--mac', required=True,
                  help='MAC address of the NIC')
    p.add_argument('--type',
                  help='Boot option type filter (e.g., PXE)')

    # setup-pxe-boot
    p = subparsers.add_parser('setup-pxe-boot',
                              help='Enable PXE on a NIC and set it first in boot order')
    p.add_argument('-m', '--mac', required=True,
                  help='MAC address of the NIC')
    p.add_argument('--protocol', default='IPv4',
                  choices=['IPv4', 'IPv6', 'IPv4andIPv6'],
                  help='PXE protocol (default: IPv4)')
    p.add_argument('--no-reboot', action='store_true',
                  help='Do not reboot if PXE needs enabling (stage only)')

    # enable-pxe
    p = subparsers.add_parser('enable-pxe', help='Enable PXE boot on a NIC by MAC address')
    p.add_argument('-m', '--mac', required=True,
                  help='MAC address of the NIC (e.g., 04:32:01:D8:C0:B0)')
    p.add_argument('--protocol', default='IPv4',
                  choices=['IPv4', 'IPv6', 'IPv4andIPv6'],
                  help='PXE protocol (default: IPv4)')

    # check-pxe
    p = subparsers.add_parser('check-pxe', help='Check if PXE is enabled for a NIC by MAC address')
    p.add_argument('-m', '--mac', required=True,
                  help='MAC address of the NIC (e.g., 04:32:01:D8:C0:B0)')

    # local-access
    p = subparsers.add_parser('local-access', help='Toggle local iDRAC access')
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--enable', action='store_true',
                      help='Enable local iDRAC access')
    group.add_argument('--disable', action='store_true',
                      help='Disable local iDRAC access')


# Boot Management Handlers

def handle_boot_get_order(args):
    """Handle 'redfish boot get-order' command."""
    rf = establish_redfish_connection(args)

    if getattr(args, 'staged', False):
        if not hasattr(rf.manufacturer_class, 'get_pending_boot_order'):
            raise NotImplementedError(
                f"Staged boot order not supported for manufacturer: {rf.manufacturer}"
            )
        boot_order = rf.manufacturer_class.get_pending_boot_order()
        return {
            'staged_boot_order': boot_order,
            'count': len(boot_order)
        }

    boot_order = rf.get_boot_order()
    return {
        'boot_order': boot_order,
        'count': len(boot_order)
    }


def handle_boot_set_order(args):
    """Handle 'redfish boot set-order' command."""
    rf = establish_redfish_connection(args)

    # Get boot order from args or file
    if args.order:
        boot_order = parse_comma_list(args.order)
    else:
        boot_order = read_file_lines(args.order_file)

    print_verbose(f"Setting boot order to: {boot_order}", args)

    rf.set_boot_order(boot_order)

    # Get updated boot order to confirm
    updated = rf.get_boot_order()

    return {
        'message': 'Boot order updated successfully',
        'boot_order': updated
    }


def handle_boot_list_options(args):
    """Handle 'redfish boot list-options' command."""
    rf = establish_redfish_connection(args)
    nocache = getattr(args, 'no_cache', False)
    boot_options = rf.get_boot_options(nocache=nocache)
    return {
        'boot_options': boot_options,
        'count': len(boot_options)
    }


def handle_boot_find_by_mac(args):
    """Handle 'redfish boot find-by-mac' command."""
    rf = establish_redfish_connection(args)
    nocache = getattr(args, 'no_cache', False)
    boot_type = getattr(args, 'type', None)

    boot_option = rf.get_boot_option_by_mac(
        args.mac,
        type=boot_type,
        nocache=nocache
    )

    return boot_option


def handle_boot_find_by_alias(args):
    """Handle 'redfish boot find-by-alias' command."""
    rf = establish_redfish_connection(args)
    nocache = getattr(args, 'no_cache', False)

    boot_option = rf.get_boot_option_by_alias(
        args.alias,
        nocache=nocache
    )

    return boot_option


def handle_boot_get_pending(args):
    """Handle 'redfish boot get-pending' command."""
    rf = establish_redfish_connection(args)

    # This is ASUS-specific
    if not hasattr(rf.manufacturer_class, 'get_pending_boot_order'):
        raise NotImplementedError(
            f"Pending boot order not supported for manufacturer: {rf.manufacturer}"
        )

    pending = rf.manufacturer_class.get_pending_boot_order()
    return {
        'pending_boot_order': pending,
        'count': len(pending)
    }


# Firmware Management Handlers

def handle_firmware_inventory(args):
    """Handle 'redfish firmware inventory' command."""
    rf = establish_redfish_connection(args)
    inventory = rf.get_firmware_inventory()
    return inventory


def handle_firmware_status(args):
    """Handle 'redfish firmware status' command."""
    rf = establish_redfish_connection(args)
    status = rf.get_update_service_info()
    return status


def handle_firmware_update_bios(args):
    """Handle 'redfish firmware update-bios' command."""
    validate_file_exists(args.file)
    rf = establish_redfish_connection(args)

    print_verbose(f"Uploading BIOS firmware from {args.file}...", args)

    result = rf.update_bios_firmware(args.file)

    return result


def handle_firmware_update_bmc(args):
    """Handle 'redfish firmware update-bmc' command."""
    validate_file_exists(args.file)
    rf = establish_redfish_connection(args)

    preserve_config = not getattr(args, 'no_preserve_config', False)

    print_verbose(f"Uploading BMC firmware from {args.file}...", args)
    print_verbose(f"Preserve config: {preserve_config}", args)

    result = rf.update_bmc_firmware(args.file, preserve_config=preserve_config)

    return result


# System Management Handlers

def handle_system_reset(args):
    """Handle 'redfish system reset' command."""
    rf = establish_redfish_connection(args)

    reset_type = getattr(args, 'reset_type', None)

    print_verbose(f"Resetting system (type: {reset_type or 'auto'})...", args)

    rf.reset_system(reset_type)

    return {
        'message': 'System reset command sent successfully',
        'reset_type': reset_type or 'auto-selected'
    }


def handle_system_reset_types(args):
    """Handle 'redfish system reset-types' command."""
    rf = establish_redfish_connection(args)

    reset_info = rf.get_supported_reset_types()

    return reset_info


def handle_system_info(args):
    """Handle 'redfish system info' command."""
    rf = establish_redfish_connection(args)

    info = {
        'manufacturer': rf.manufacturer,
        'system_id': rf.system_id,
        'ip': args.ip
    }

    return info


# TPM Management Handlers

def handle_tpm_set_state(args):
    """Handle 'redfish tpm set-state' command."""
    rf = establish_redfish_connection(args)

    # This is ASUS-specific
    if not hasattr(rf.manufacturer_class, 'set_trusted_module_state'):
        raise NotImplementedError(
            f"TPM management not supported for manufacturer: {rf.manufacturer}"
        )

    print_verbose(f"Setting TPM state to: {args.state}...", args)

    rf.manufacturer_class.set_trusted_module_state(args.state)

    return {
        'message': f'TPM state set to {args.state} successfully'
    }


# Dell-Specific Handlers

def handle_dell_get_boot_options(args):
    """Handle 'redfish dell get-boot-options' command."""
    rf = establish_redfish_connection(args)
    nocache = getattr(args, 'no_cache', False)
    boot_options = rf.manufacturer_class.get_boot_options(nocache=nocache)
    return {
        'boot_options': boot_options,
        'count': len(boot_options)
    }


def handle_dell_get_nics(args):
    """Handle 'redfish dell get-nics' command."""
    rf = establish_redfish_connection(args)
    interfaces = rf.manufacturer_class.get_network_interfaces()
    return {
        'network_interfaces': interfaces,
        'count': len(interfaces)
    }


def handle_dell_get_nic_attrs(args):
    """Handle 'redfish dell get-nic-attrs' command."""
    rf = establish_redfish_connection(args)
    result = rf.manufacturer_class.get_nic_attributes(args.mac)
    return result


def handle_dell_boot_first_by_mac(args):
    """Handle 'redfish dell boot-first-by-mac' command."""
    rf = establish_redfish_connection(args)
    boot_type = getattr(args, 'type', None)
    result = rf.manufacturer_class.set_boot_first_by_mac(args.mac, boot_type=boot_type)
    return result


def handle_dell_setup_pxe_boot(args):
    """Handle 'redfish dell setup-pxe-boot' command."""
    rf = establish_redfish_connection(args)
    protocol = getattr(args, 'protocol', 'IPv4')
    reboot = not getattr(args, 'no_reboot', False)
    result = rf.manufacturer_class.setup_pxe_boot(
        args.mac, protocol=protocol, reboot=reboot
    )
    return result


def handle_dell_enable_pxe(args):
    """Handle 'redfish dell enable-pxe' command."""
    rf = establish_redfish_connection(args)
    protocol = getattr(args, 'protocol', 'IPv4')
    result = rf.manufacturer_class.enable_nic_pxe(args.mac, protocol=protocol)
    return result


def handle_dell_check_pxe(args):
    """Handle 'redfish dell check-pxe' command."""
    rf = establish_redfish_connection(args)
    result = rf.manufacturer_class.check_pxe_status(args.mac)
    return result


def handle_dell_onetime_boot(args):
    """Handle 'redfish dell onetime-boot' command."""
    rf = establish_redfish_connection(args)

    if not hasattr(rf.manufacturer_class, 'set_next_onetime_boot'):
        raise NotImplementedError(
            f"One-time boot not supported for manufacturer: {rf.manufacturer}"
        )

    print_verbose(f"Setting one-time boot to: {args.source}...", args)

    rf.manufacturer_class.set_next_onetime_boot(args.source)

    return {
        'message': f'One-time boot set to {args.source} successfully'
    }


def handle_dell_create_role(args):
    """Handle 'redfish dell create-role' command."""
    rf = establish_redfish_connection(args)

    if not hasattr(rf.manufacturer_class, 'create_user_group'):
        raise NotImplementedError(
            f"User group creation not supported for manufacturer: {rf.manufacturer}"
        )

    print_verbose(f"Creating role: {args.name} with privileges: {args.privileges}...", args)

    rf.manufacturer_class.create_user_group(args.name, args.privileges)

    return {
        'message': f'Role {args.name} created successfully'
    }


def handle_dell_local_access(args):
    """Handle 'redfish dell local-access' command."""
    rf = establish_redfish_connection(args)

    if not hasattr(rf.manufacturer_class, 'toggle_local_idrac_access'):
        raise NotImplementedError(
            f"Local iDRAC access control not supported for manufacturer: {rf.manufacturer}"
        )

    disable = args.disable
    action = "Disabling" if disable else "Enabling"

    print_verbose(f"{action} local iDRAC access...", args)

    rf.manufacturer_class.toggle_local_idrac_access(disable)

    return {
        'message': f'Local iDRAC access {"disabled" if disable else "enabled"} successfully'
    }


# Dispatch Functions

def dispatch(args):
    """Dispatch Redfish command to appropriate handler.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    group = args.redfish_group

    if group == 'boot':
        return dispatch_boot(args)
    elif group == 'firmware':
        return dispatch_firmware(args)
    elif group == 'system':
        return dispatch_system(args)
    elif group == 'tpm':
        return dispatch_tpm(args)
    elif group == 'dell':
        return dispatch_dell(args)
    else:
        print(f"Error: Unknown redfish group: {group}", file=sys.stderr)
        return 1


def dispatch_boot(args):
    """Dispatch boot command."""
    action = args.boot_action
    handlers = {
        'get-order': handle_boot_get_order,
        'set-order': handle_boot_set_order,
        'list-options': handle_boot_list_options,
        'find-by-mac': handle_boot_find_by_mac,
        'find-by-alias': handle_boot_find_by_alias,
        'get-pending': handle_boot_get_pending,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown boot action: {action}", file=sys.stderr)
        return 1


def dispatch_firmware(args):
    """Dispatch firmware command."""
    action = args.firmware_action
    handlers = {
        'inventory': handle_firmware_inventory,
        'status': handle_firmware_status,
        'update-bios': handle_firmware_update_bios,
        'update-bmc': handle_firmware_update_bmc,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown firmware action: {action}", file=sys.stderr)
        return 1


def dispatch_system(args):
    """Dispatch system command."""
    action = args.system_action
    handlers = {
        'reset': handle_system_reset,
        'reset-types': handle_system_reset_types,
        'info': handle_system_info,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown system action: {action}", file=sys.stderr)
        return 1


def dispatch_tpm(args):
    """Dispatch TPM command."""
    action = args.tpm_action
    handlers = {
        'set-state': handle_tpm_set_state,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown TPM action: {action}", file=sys.stderr)
        return 1


def dispatch_dell(args):
    """Dispatch Dell-specific command."""
    action = args.dell_action
    handlers = {
        'get-boot-options': handle_dell_get_boot_options,
        'get-nics': handle_dell_get_nics,
        'get-nic-attrs': handle_dell_get_nic_attrs,
        'boot-first-by-mac': handle_dell_boot_first_by_mac,
        'setup-pxe-boot': handle_dell_setup_pxe_boot,
        'enable-pxe': handle_dell_enable_pxe,
        'check-pxe': handle_dell_check_pxe,
        'onetime-boot': handle_dell_onetime_boot,
        'create-role': handle_dell_create_role,
        'local-access': handle_dell_local_access,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown Dell action: {action}", file=sys.stderr)
        return 1


def handle_alias(args, target):
    """Handle aliased commands.

    Args:
        args: Parsed arguments
        target: Alias target identifier

    Returns:
        Exit code
    """
    if target == 'redfish_firmware_update_bios':
        return wrap_command(handle_firmware_update_bios, args)
    elif target == 'redfish_firmware_update_bmc':
        return wrap_command(handle_firmware_update_bmc, args)
    elif target == 'redfish_system_reset':
        return wrap_command(handle_system_reset, args)
    elif target == 'redfish_boot_get_order':
        return wrap_command(handle_boot_get_order, args)
    elif target == 'redfish_boot_set_order':
        return wrap_command(handle_boot_set_order, args)
    elif target == 'redfish_boot_list_options':
        return wrap_command(handle_boot_list_options, args)
    elif target == 'redfish_dell_enable_pxe':
        return wrap_command(handle_dell_enable_pxe, args)
    elif target == 'redfish_dell_setup_pxe_boot':
        return wrap_command(handle_dell_setup_pxe_boot, args)
    elif target == 'redfish_dell_get_nics':
        return wrap_command(handle_dell_get_nics, args)
    elif target == 'redfish_dell_boot_first_by_mac':
        return wrap_command(handle_dell_boot_first_by_mac, args)
    elif target == 'redfish_dell_check_pxe':
        return wrap_command(handle_dell_check_pxe, args)
    else:
        print(f"Error: Unknown redfish alias: {target}", file=sys.stderr)
        return 1
