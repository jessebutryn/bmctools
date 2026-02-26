"""BMCTools CLI main entry point."""

import argparse
import sys
from bmctools.cli import __version__
from bmctools.cli.utils import (
    apply_env_vars,
    EXIT_INVALID_ARGUMENTS,
)


def create_parser():
    """Create the main argument parser with all subcommands.

    Returns:
        ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog='bmctools',
        description='BMC management tool supporting Redfish, IPMI, and RACADM',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  BMC_HOST          BMC IP address or hostname
  BMC_USERNAME      BMC username
  BMC_PASSWORD      BMC password
  BMC_MANUFACTURER  Force manufacturer (asus, dell, supermicro)
  BMC_INSECURE      Disable SSL verification (1, true, yes)
  NO_COLOR          Disable colored output

Examples:
  # Get boot order using command-line args
  bmctools redfish boot get-order -i 10.10.10.10 -u admin -p password

  # Get boot order using environment variables
  export BMC_HOST=10.10.10.10
  export BMC_USERNAME=admin
  export BMC_PASSWORD=password
  bmctools redfish boot get-order

  # Update BIOS firmware (shorthand alias)
  bmctools update_bios -f /path/to/bios.bin -i 10.10.10.10 -u admin -p pass

  # List boot options with table output
  bmctools redfish boot list-options -o table

For more information, visit: https://github.com/yourusername/bmctools
"""
    )

    # Global options
    parser.add_argument('--version', action='version', version=f'bmctools {__version__}')

    parser.add_argument('-i', '--ip', '--host', dest='ip',
                       help='BMC IP address or hostname (env: BMC_HOST)')
    parser.add_argument('-u', '--username',
                       help='BMC username (env: BMC_USERNAME)')
    parser.add_argument('-p', '--password',
                       help='BMC password (env: BMC_PASSWORD)')
    parser.add_argument('-k', '--insecure', action='store_true',
                       help='Disable SSL verification (env: BMC_INSECURE)')
    parser.add_argument('-m', '--manufacturer',
                       choices=['asus', 'dell', 'supermicro'],
                       help='Force manufacturer (env: BMC_MANUFACTURER)')

    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    parser.add_argument('-d', '--debug', action='store_true',
                       help='Enable debug mode (show stack traces)')

    parser.add_argument('-o', '--output',
                       choices=['json', 'json-pretty', 'table', 'text'],
                       default='json',
                       help='Output format (default: json)')
    parser.add_argument('--no-color', action='store_true',
                       help='Disable colored output')

    # Create subparsers for modules and aliases
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Import command setup functions
    try:
        from bmctools.cli.commands import redfish as redfish_cmd
        redfish_parser = subparsers.add_parser('redfish', help='Redfish operations')
        redfish_cmd.setup_redfish_commands(redfish_parser)
    except ImportError:
        pass  # Module not yet implemented

    try:
        from bmctools.cli.commands import ipmi as ipmi_cmd
        ipmi_parser = subparsers.add_parser('ipmi', help='IPMI operations')
        ipmi_cmd.setup_ipmi_commands(ipmi_parser)
    except ImportError:
        pass  # Module not yet implemented

    try:
        from bmctools.cli.commands import racadm as racadm_cmd
        racadm_parser = subparsers.add_parser('racadm', help='RACADM operations (Dell only)')
        racadm_cmd.setup_racadm_commands(racadm_parser)
    except ImportError:
        pass  # Module not yet implemented

    # Shorthand aliases (map to full commands)
    setup_aliases(subparsers)

    return parser


def setup_aliases(subparsers):
    """Setup shorthand aliases for common commands.

    Args:
        subparsers: Subparsers object from main parser
    """
    # update_bios alias
    alias = subparsers.add_parser('update_bios',
                                   help='Update BIOS firmware (alias for: redfish firmware update-bios)')
    alias.add_argument('-f', '--file', required=True,
                      help='Path to BIOS firmware file')
    alias.set_defaults(alias_target='redfish_firmware_update_bios')

    # update_bmc alias
    alias = subparsers.add_parser('update_bmc',
                                   help='Update BMC firmware (alias for: redfish firmware update-bmc)')
    alias.add_argument('-f', '--file', required=True,
                      help='Path to BMC firmware file')
    alias.add_argument('--no-preserve-config', action='store_true',
                      help='Do not preserve BMC configuration')
    alias.set_defaults(alias_target='redfish_firmware_update_bmc')

    # power_on alias
    alias = subparsers.add_parser('power_on',
                                   help='Power on system (alias for: ipmi power on)')
    alias.set_defaults(alias_target='ipmi_power_on')

    # power_off alias
    alias = subparsers.add_parser('power_off',
                                   help='Power off system (alias for: ipmi power off)')
    alias.set_defaults(alias_target='ipmi_power_off')

    # power_status alias
    alias = subparsers.add_parser('power_status',
                                   help='Get power status (alias for: ipmi power status)')
    alias.set_defaults(alias_target='ipmi_power_status')

    # reboot alias
    alias = subparsers.add_parser('reboot',
                                   help='Reboot system (alias for: redfish system reset)')
    alias.add_argument('--type', dest='reset_type',
                      help='Reset type (e.g., GracefulRestart, ForceRestart)')
    alias.set_defaults(alias_target='redfish_system_reset')

    # get_boot_order alias
    alias = subparsers.add_parser('get_boot_order',
                                   help='Get boot order (alias for: redfish boot get-order)')
    alias.add_argument('--staged', action='store_true',
                      help='Show staged/pending boot order instead of current')
    alias.set_defaults(alias_target='redfish_boot_get_order')

    # set_boot_order alias
    alias = subparsers.add_parser('set_boot_order',
                                   help='Set boot order (alias for: redfish boot set-order)')
    group = alias.add_mutually_exclusive_group(required=True)
    group.add_argument('-o', '--order',
                      help='Comma-separated boot order (e.g., "Boot0003,Boot0004,Boot0000")')
    group.add_argument('--order-file',
                      help='File containing boot order (one entry per line)')
    alias.set_defaults(alias_target='redfish_boot_set_order')

    # get_boot_options alias
    alias = subparsers.add_parser('get_boot_options',
                                   help='Get boot options (alias for: redfish boot list-options)')
    alias.add_argument('--no-cache', action='store_true',
                      help='Force fresh query (bypass cache)')
    alias.set_defaults(alias_target='redfish_boot_list_options')


def dispatch_alias(args):
    """Dispatch aliased command to its target handler.

    Args:
        args: Parsed arguments with alias_target

    Returns:
        Exit code
    """
    target = args.alias_target

    # Import and dispatch based on target
    if target.startswith('redfish_'):
        from bmctools.cli.commands import redfish as redfish_cmd
        return redfish_cmd.handle_alias(args, target)
    elif target.startswith('ipmi_'):
        from bmctools.cli.commands import ipmi as ipmi_cmd
        return ipmi_cmd.handle_alias(args, target)
    elif target.startswith('racadm_'):
        from bmctools.cli.commands import racadm as racadm_cmd
        return racadm_cmd.handle_alias(args, target)
    else:
        print(f"Error: Unknown alias target: {target}", file=sys.stderr)
        return EXIT_INVALID_ARGUMENTS


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Apply environment variables
    args = apply_env_vars(args)

    # Check if a command was provided
    if not args.command:
        parser.print_help()
        return EXIT_INVALID_ARGUMENTS

    # Handle aliases
    if hasattr(args, 'alias_target'):
        return dispatch_alias(args)

    # Dispatch to module handler
    if args.command == 'redfish':
        try:
            from bmctools.cli.commands import redfish as redfish_cmd
            return redfish_cmd.dispatch(args)
        except ImportError as e:
            print(f"Error: Redfish module not available: {e}", file=sys.stderr)
            return EXIT_INVALID_ARGUMENTS

    elif args.command == 'ipmi':
        try:
            from bmctools.cli.commands import ipmi as ipmi_cmd
            return ipmi_cmd.dispatch(args)
        except ImportError as e:
            print(f"Error: IPMI module not available: {e}", file=sys.stderr)
            return EXIT_INVALID_ARGUMENTS

    elif args.command == 'racadm':
        try:
            from bmctools.cli.commands import racadm as racadm_cmd
            return racadm_cmd.dispatch(args)
        except ImportError as e:
            print(f"Error: RACADM module not available: {e}", file=sys.stderr)
            return EXIT_INVALID_ARGUMENTS

    else:
        print(f"Error: Unknown command: {args.command}", file=sys.stderr)
        return EXIT_INVALID_ARGUMENTS


if __name__ == '__main__':
    sys.exit(main())
