"""RACADM command handlers."""

import sys
from bmctools.cli.utils import (
    establish_racadm_connection,
    print_verbose,
)
from bmctools.cli.commands.common import wrap_command


def setup_racadm_commands(parser):
    """Setup RACADM subcommands.

    Args:
        parser: RACADM subparser
    """
    subparsers = parser.add_subparsers(dest='racadm_group', help='RACADM operation group')

    # Get configuration
    p = subparsers.add_parser('get', help='Get configuration')
    p.add_argument('endpoint', help='Configuration endpoint')
    p.add_argument('--format', action='store_true',
                  help='Use formatted output')

    # Set configuration
    p = subparsers.add_parser('set', help='Set configuration')
    p.add_argument('endpoint', help='Configuration endpoint')
    p.add_argument('--args',
                  help='Comma-separated arguments')

    # Storage commands
    storage_parser = subparsers.add_parser('storage', help='Storage management')
    setup_storage_commands(storage_parser)

    # Job queue commands
    job_parser = subparsers.add_parser('job', help='Job queue management')
    setup_job_commands(job_parser)


def setup_storage_commands(parser):
    """Setup storage subcommands."""
    subparsers = parser.add_subparsers(dest='storage_action', help='Storage action')

    p = subparsers.add_parser('get', help='Get storage configuration')
    p.add_argument('endpoint', help='Storage endpoint')

    p = subparsers.add_parser('check-vdisk', help='Check virtual disks')
    p.add_argument('--format', action='store_true',
                  help='Use formatted output')


def setup_job_commands(parser):
    """Setup job queue subcommands."""
    subparsers = parser.add_subparsers(dest='job_action', help='Job action')

    p = subparsers.add_parser('view', help='View job details')
    p.add_argument('-j', '--job-id', required=True,
                  help='Job ID')

    p = subparsers.add_parser('status', help='Get job status')
    p.add_argument('-j', '--job-id', required=True,
                  help='Job ID')

    p = subparsers.add_parser('wait', help='Wait for job completion')
    p.add_argument('-j', '--job-id', required=True,
                  help='Job ID')
    p.add_argument('--timeout', type=int, default=300,
                  help='Timeout in seconds (default: 300)')


# Configuration Handlers

def handle_get(args):
    """Handle 'racadm get' command."""
    racadm = establish_racadm_connection(args)

    use_format = getattr(args, 'format', False)

    print_verbose(f"Getting config: {args.endpoint} (format={use_format})", args)

    result = racadm.get(
        endpoint=args.endpoint,
        arguments=None,
        format=use_format
    )

    return {
        'endpoint': args.endpoint,
        'result': result
    }


def handle_set(args):
    """Handle 'racadm set' command."""
    racadm = establish_racadm_connection(args)

    # Parse arguments
    arguments = None
    if args.args:
        arguments = [arg.strip() for arg in args.args.split(',')]

    print_verbose(f"Setting config: {args.endpoint} (args={arguments})", args)

    result = racadm.set(
        endpoint=args.endpoint,
        arguments=arguments
    )

    return {
        'endpoint': args.endpoint,
        'arguments': arguments,
        'result': result
    }


# Storage Handlers

def handle_storage_get(args):
    """Handle 'racadm storage get' command."""
    racadm = establish_racadm_connection(args)

    print_verbose(f"Getting storage config: {args.endpoint}", args)

    result = racadm.storage_get(
        endpoint=args.endpoint,
        arguments=None
    )

    return {
        'endpoint': args.endpoint,
        'result': result
    }


def handle_storage_check_vdisk(args):
    """Handle 'racadm storage check-vdisk' command."""
    racadm = establish_racadm_connection(args)

    use_format = getattr(args, 'format', False)

    print_verbose(f"Checking virtual disks (format={use_format})", args)

    result = racadm.check_vdisk(format=use_format)

    return {
        'result': result
    }


# Job Queue Handlers

def handle_job_view(args):
    """Handle 'racadm job view' command."""
    racadm = establish_racadm_connection(args)

    print_verbose(f"Viewing job: {args.job_id}", args)

    result = racadm.jobqueue_view(job=args.job_id)

    return {
        'job_id': args.job_id,
        'details': result
    }


def handle_job_status(args):
    """Handle 'racadm job status' command."""
    racadm = establish_racadm_connection(args)

    print_verbose(f"Getting job status: {args.job_id}", args)

    result = racadm.jobqueue_status(job=args.job_id)

    return {
        'job_id': args.job_id,
        'status': result
    }


def handle_job_wait(args):
    """Handle 'racadm job wait' command."""
    racadm = establish_racadm_connection(args)

    timeout = getattr(args, 'timeout', 300)

    print_verbose(f"Waiting for job completion: {args.job_id} (timeout={timeout}s)", args)

    result = racadm.jobqueue_wait(job=args.job_id)

    return {
        'job_id': args.job_id,
        'completed': True,
        'result': result
    }


# Dispatch Functions

def dispatch(args):
    """Dispatch RACADM command to appropriate handler.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    group = args.racadm_group

    if group == 'get':
        return wrap_command(handle_get, args)
    elif group == 'set':
        return wrap_command(handle_set, args)
    elif group == 'storage':
        return dispatch_storage(args)
    elif group == 'job':
        return dispatch_job(args)
    else:
        print(f"Error: Unknown RACADM group: {group}", file=sys.stderr)
        return 1


def dispatch_storage(args):
    """Dispatch storage command."""
    action = args.storage_action
    handlers = {
        'get': handle_storage_get,
        'check-vdisk': handle_storage_check_vdisk,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown storage action: {action}", file=sys.stderr)
        return 1


def dispatch_job(args):
    """Dispatch job queue command."""
    action = args.job_action
    handlers = {
        'view': handle_job_view,
        'status': handle_job_status,
        'wait': handle_job_wait,
    }

    if action in handlers:
        return wrap_command(handlers[action], args)
    else:
        print(f"Error: Unknown job action: {action}", file=sys.stderr)
        return 1


def handle_alias(args, target):
    """Handle aliased commands.

    Args:
        args: Parsed arguments
        target: Alias target identifier

    Returns:
        Exit code
    """
    # No RACADM aliases currently defined
    print(f"Error: Unknown RACADM alias: {target}", file=sys.stderr)
    return 1
