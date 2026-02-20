"""IPMI command handlers."""

import sys
from bmctools.cli.utils import (
    establish_ipmi_connection,
    print_verbose,
)
from bmctools.cli.commands.common import wrap_command


def setup_ipmi_commands(parser):
    """Setup IPMI subcommands.

    Args:
        parser: IPMI subparser
    """
    subparsers = parser.add_subparsers(dest='ipmi_group', help='IPMI operation group')

    # Power management commands
    power_parser = subparsers.add_parser('power', help='Power management')
    setup_power_commands(power_parser)

    # BMC management commands
    bmc_parser = subparsers.add_parser('bmc', help='BMC management')
    setup_bmc_commands(bmc_parser)

    # SEL commands
    sel_parser = subparsers.add_parser('sel', help='System Event Log')
    setup_sel_commands(sel_parser)

    # SOL commands
    sol_parser = subparsers.add_parser('sol', help='Serial Over LAN')
    setup_sol_commands(sol_parser)

    # Raw command
    raw_parser = subparsers.add_parser('raw', help='Execute raw IPMI command')
    raw_parser.add_argument('command', help='Raw IPMI command')


def setup_power_commands(parser):
    """Setup power management subcommands."""
    subparsers = parser.add_subparsers(dest='power_action', help='Power action')

    subparsers.add_parser('status', help='Get power status')
    subparsers.add_parser('on', help='Power on system')
    subparsers.add_parser('off', help='Power off system')
    subparsers.add_parser('reset', help='Hard reset system')


def setup_bmc_commands(parser):
    """Setup BMC management subcommands."""
    subparsers = parser.add_subparsers(dest='bmc_action', help='BMC action')

    subparsers.add_parser('reset-warm', help='Warm reset BMC')
    subparsers.add_parser('reset-cold', help='Cold reset BMC')


def setup_sel_commands(parser):
    """Setup SEL subcommands."""
    subparsers = parser.add_subparsers(dest='sel_action', help='SEL action')

    p = subparsers.add_parser('list', help='List system event log')
    p.add_argument('--elist', action='store_true',
                  help='Use extended list format')
    p.add_argument('--raw', action='store_true',
                  help='Show raw data')
    p.add_argument('--age',
                  help='Filter by age (e.g., 7d, 24h)')


def setup_sol_commands(parser):
    """Setup SOL subcommands."""
    subparsers = parser.add_subparsers(dest='sol_action', help='SOL action')

    subparsers.add_parser('deactivate', help='Deactivate Serial Over LAN')

    p = subparsers.add_parser('looptest', help='Run SOL loopback test')
    p.add_argument('--loops', type=int, default=10,
                  help='Number of loops (default: 10)')


# Power Management Handlers

def handle_power_status(args):
    """Handle 'ipmi power status' command."""
    ipmi = establish_ipmi_connection(args)
    status = ipmi.power_status()
    return {'power_status': status}


def handle_power_on(args):
    """Handle 'ipmi power on' command."""
    ipmi = establish_ipmi_connection(args)
    print_verbose("Powering on system...", args)
    result = ipmi.power_on()
    return {'message': 'Power on command sent', 'result': result}


def handle_power_off(args):
    """Handle 'ipmi power off' command."""
    ipmi = establish_ipmi_connection(args)
    print_verbose("Powering off system...", args)
    result = ipmi.power_off()
    return {'message': 'Power off command sent', 'result': result}


def handle_power_reset(args):
    """Handle 'ipmi power reset' command."""
    ipmi = establish_ipmi_connection(args)
    print_verbose("Resetting system...", args)
    result = ipmi.power_reset()
    return {'message': 'Power reset command sent', 'result': result}


# BMC Management Handlers

def handle_bmc_reset_warm(args):
    """Handle 'ipmi bmc reset-warm' command."""
    ipmi = establish_ipmi_connection(args)
    print_verbose("Performing warm reset of BMC...", args)
    result = ipmi.bmc_reset_warm()
    return {'message': 'BMC warm reset command sent', 'result': result}


def handle_bmc_reset_cold(args):
    """Handle 'ipmi bmc reset-cold' command."""
    ipmi = establish_ipmi_connection(args)
    print_verbose("Performing cold reset of BMC...", args)
    result = ipmi.bmc_reset_cold()
    return {'message': 'BMC cold reset command sent', 'result': result}


# SEL Handlers

def handle_sel_list(args):
    """Handle 'ipmi sel list' command."""
    ipmi = establish_ipmi_connection(args)

    elist = getattr(args, 'elist', False)
    raw = getattr(args, 'raw', False)
    age = getattr(args, 'age', None)

    print_verbose(f"Fetching SEL (elist={elist}, raw={raw}, age={age})...", args)

    result = ipmi.sel_list(elist=elist, raw=raw, age=age)

    return {'sel_entries': result}


# SOL Handlers

def handle_sol_deactivate(args):
    """Handle 'ipmi sol deactivate' command."""
    ipmi = establish_ipmi_connection(args)
    print_verbose("Deactivating Serial Over LAN...", args)
    result = ipmi.sol_deactivate()
    return {'message': 'SOL deactivate command sent', 'result': result}


def handle_sol_looptest(args):
    """Handle 'ipmi sol looptest' command."""
    ipmi = establish_ipmi_connection(args)
    loops = getattr(args, 'loops', 10)

    print_verbose(f"Running SOL loopback test ({loops} loops)...", args)

    result = ipmi.sol_looptest(num_loops=loops)

    return {'message': f'SOL loopback test completed', 'result': result}


# Raw Command Handler

def handle_raw(args):
    """Handle 'ipmi raw' command."""
    ipmi = establish_ipmi_connection(args)

    print_verbose(f"Executing raw IPMI command: {args.command}", args)

    result = ipmi.ipmitool_command(args.command)

    return {'command': args.command, 'result': result}


# Dispatch Functions

def dispatch(args):
    """Dispatch IPMI command to appropriate handler.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    group = args.ipmi_group

    if group == 'power':
        return dispatch_power(args)
    elif group == 'bmc':
        return dispatch_bmc(args)
    elif group == 'sel':
        return dispatch_sel(args)
    elif group == 'sol':
        return dispatch_sol(args)
    elif group == 'raw':
        return wrap_command(handle_raw, args)
    else:
        print(f"Error: Unknown IPMI group: {group}", file=sys.stderr)
        return 1


def dispatch_power(args):
    """Dispatch power command."""
    action = args.power_action
    handlers = {
        'status': handle_power_status,
        'on': handle_power_on,
        'off': handle_power_off,
        'reset': handle_power_reset,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown power action: {action}", file=sys.stderr)
        return 1


def dispatch_bmc(args):
    """Dispatch BMC command."""
    action = args.bmc_action
    handlers = {
        'reset-warm': handle_bmc_reset_warm,
        'reset-cold': handle_bmc_reset_cold,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown BMC action: {action}", file=sys.stderr)
        return 1


def dispatch_sel(args):
    """Dispatch SEL command."""
    action = args.sel_action
    handlers = {
        'list': handle_sel_list,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown SEL action: {action}", file=sys.stderr)
        return 1


def dispatch_sol(args):
    """Dispatch SOL command."""
    action = args.sol_action
    handlers = {
        'deactivate': handle_sol_deactivate,
        'looptest': handle_sol_looptest,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown SOL action: {action}", file=sys.stderr)
        return 1


def handle_alias(args, target):
    """Handle aliased commands.

    Args:
        args: Parsed arguments
        target: Alias target identifier

    Returns:
        Exit code
    """
    if target == 'ipmi_power_on':
        return wrap_command(handle_power_on, args)
    elif target == 'ipmi_power_off':
        return wrap_command(handle_power_off, args)
    elif target == 'ipmi_power_status':
        return wrap_command(handle_power_status, args)
    else:
        print(f"Error: Unknown IPMI alias: {target}", file=sys.stderr)
        return 1
