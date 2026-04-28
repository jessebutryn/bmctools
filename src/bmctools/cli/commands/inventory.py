"""Inventory command handler — aggregates system info via Redfish."""

import argparse
import sys
from bmctools.cli.utils import (
    establish_redfish_connection,
    EXIT_SUCCESS,
)
from bmctools.cli.commands.common import wrap_command


def setup_inventory_commands(parser: argparse.ArgumentParser) -> None:
    """Setup inventory subcommands.

    Args:
        parser: Inventory subparser
    """
    subparsers = parser.add_subparsers(dest='inventory_action', help='Inventory action')

    subparsers.add_parser('all', help='Collect full system inventory')
    subparsers.add_parser('system', help='System identity (manufacturer, model, serial, etc.)')
    subparsers.add_parser('bmc', help='BMC/Manager information')
    subparsers.add_parser('network', help='Network interfaces and MAC addresses')
    subparsers.add_parser('firmware', help='Firmware versions')
    subparsers.add_parser('boot', help='Boot order, options, and override')


# ── Handlers ───────────────────────────────────────────────────────────

def handle_inventory_all(args: argparse.Namespace) -> dict:
    """Collect full system inventory."""
    rf = establish_redfish_connection(args)
    return rf.get_system_inventory()


def handle_inventory_system(args: argparse.Namespace) -> dict:
    """Collect system identity information."""
    rf = establish_redfish_connection(args)
    inv = rf.get_system_inventory()
    result = {}
    if 'system' in inv:
        result['system'] = inv['system']
    if 'processor_summary' in inv:
        result['processor_summary'] = inv['processor_summary']
    if 'memory_summary' in inv:
        result['memory_summary'] = inv['memory_summary']
    return result


def handle_inventory_bmc(args: argparse.Namespace) -> dict:
    """Collect BMC/Manager information."""
    rf = establish_redfish_connection(args)
    inv = rf.get_system_inventory()
    return {'bmc': inv.get('bmc', {})}


def handle_inventory_network(args: argparse.Namespace) -> dict:
    """Collect network interface information."""
    rf = establish_redfish_connection(args)
    inv = rf.get_system_inventory()
    return {'network_interfaces': inv.get('network_interfaces', {})}


def handle_inventory_firmware(args: argparse.Namespace) -> dict:
    """Collect firmware inventory."""
    rf = establish_redfish_connection(args)
    inv = rf.get_system_inventory()
    return {'firmware': inv.get('firmware', {})}


def handle_inventory_boot(args: argparse.Namespace) -> dict:
    """Collect boot configuration."""
    rf = establish_redfish_connection(args)
    inv = rf.get_system_inventory()
    result = {}
    for key in ('boot_order', 'boot_options', 'boot_override'):
        if key in inv:
            result[key] = inv[key]
    return result


# ── Dispatch ───────────────────────────────────────────────────────────

def dispatch(args: argparse.Namespace) -> int:
    """Dispatch inventory command to appropriate handler.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    action = args.inventory_action

    # Default to 'all' when no subcommand is given
    if not action:
        action = 'all'

    handlers = {
        'all': handle_inventory_all,
        'system': handle_inventory_system,
        'bmc': handle_inventory_bmc,
        'network': handle_inventory_network,
        'firmware': handle_inventory_firmware,
        'boot': handle_inventory_boot,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown inventory action: {action}", file=sys.stderr)
        return 1


def handle_alias(args: argparse.Namespace, target: str) -> int:
    """Handle aliased inventory commands.

    Args:
        args: Parsed arguments
        target: Alias target identifier

    Returns:
        Exit code
    """
    if target == 'inventory_all':
        return wrap_command(handle_inventory_all, args)
    else:
        print(f"Error: Unknown inventory alias: {target}", file=sys.stderr)
        return 1
