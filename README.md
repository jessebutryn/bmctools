# BMCTools

A Python library and CLI for managing Baseboard Management Controllers (BMCs) across multiple vendors. Supports Redfish, IPMI, and RACADM protocols with automatic manufacturer detection and vendor-specific extensions.

## Features

- **Multi-Protocol Support**: Redfish API, IPMI (via ipmitool), and RACADM (Dell)
- **Automatic Manufacturer Detection**: Connects to the BMC, identifies the vendor, and loads the correct implementation
- **Vendor-Specific Implementations**:
  - **Dell iDRAC**: Full boot management, PXE setup, NIC discovery, user roles, local access control
  - **ASUS**: Boot order staging via FutureState endpoint, TPM management, firmware updates
  - **Supermicro**: Boot order and boot option queries
- **Boot Management**: Get/set boot order, list boot options, search by MAC address or alias
- **PXE Automation**: Enable PXE on a NIC by MAC address, set boot order, and reboot - all in one command
- **Firmware Updates**: Upload BIOS and BMC firmware via Redfish
- **Multiple Output Formats**: JSON, pretty JSON, table, and plain text
- **Environment Variable Support**: Configure connections via env vars for scripting

## Installation

### From PyPI

```bash
pip install bmctools
```

### From Source

```bash
git clone https://github.com/jessebutryn/bmctools.git
cd bmctools
pip install -e .
```

### Requirements

- Python 3.9+
- `requests`
- `ipmitool` (optional, for IPMI commands)
- `racadm` (optional, for Dell RACADM commands)

## Quick Start

### CLI Usage

```bash
# Set connection details via environment variables
export BMC_HOST=10.10.10.10
export BMC_USERNAME=admin
export BMC_PASSWORD=password

# Get boot order
bmctools redfish boot get-order

# Or pass connection details inline
bmctools -i 10.10.10.10 -u admin -p password redfish boot get-order

# Force a specific manufacturer (skip auto-detection)
bmctools -m dell redfish dell get-nics
```

### Python Library Usage

```python
from bmctools.redfish.redfish import Redfish

# Auto-detects manufacturer and loads appropriate implementation
rf = Redfish('10.10.10.10', 'admin', 'password', verify_ssl=False)
print(f"Manufacturer: {rf.manufacturer}")
print(f"System ID: {rf.system_id}")

# Get boot order
boot_order = rf.get_boot_order()

# Find a boot option by MAC address
option = rf.get_boot_option_by_mac('04:32:01:D8:C0:B0')

# Set boot order (must include ALL boot options)
rf.set_boot_order(["Boot0003", "Boot0001", "Boot0000", "Boot0002"])
```

## Global Options

| Option | Env Variable | Description |
|---|---|---|
| `-i, --ip, --host` | `BMC_HOST` | BMC IP address or hostname |
| `-u, --username` | `BMC_USERNAME` | BMC username |
| `-p, --password` | `BMC_PASSWORD` | BMC password |
| `-m, --manufacturer` | `BMC_MANUFACTURER` | Force manufacturer: `asus`, `dell`, `supermicro` |
| `-k, --insecure` | `BMC_INSECURE` | Disable SSL verification |
| `-o, --output` | | Output format: `json`, `json-pretty`, `table`, `text` |
| `-v, --verbose` | | Enable verbose output |
| `-d, --debug` | | Enable debug mode (show stack traces) |
| `--no-color` | `NO_COLOR` | Disable colored output |
| `--version` | | Show version |

## CLI Command Reference

### Redfish Boot Management

```bash
bmctools redfish boot <command>
```

| Command | Description |
|---|---|
| `get-order [--staged]` | Get current boot order. `--staged` shows pending order (ASUS). |
| `set-order -o ORDER` | Set boot order. Comma-separated list (e.g., `Boot0003,Boot0001,Boot0000`). |
| `set-order --order-file FILE` | Set boot order from a file (one entry per line). |
| `list-options [--no-cache]` | List all available boot options. |
| `find-by-mac -m MAC [--type TYPE]` | Find boot option by MAC address. Optional type filter (e.g., `PXE`). |
| `find-by-alias -a ALIAS` | Find boot option by display name or alias. |
| `get-pending` | Get pending boot order (ASUS FutureState endpoint). |

**Examples:**

```bash
# Get current boot order
bmctools redfish boot get-order

# List all boot options with details
bmctools redfish boot list-options -o json-pretty

# Find the PXE boot option for a specific NIC
bmctools redfish boot find-by-mac -m 04:32:01:D8:C0:B0 --type PXE

# Set a new boot order
bmctools redfish boot set-order -o "Boot0003,Boot0001,Boot0000,Boot0002"
```

### Redfish Firmware Management

```bash
bmctools redfish firmware <command>
```

| Command | Description |
|---|---|
| `inventory` | Get firmware inventory (BIOS, BMC versions, etc.) |
| `status` | Get update service status |
| `update-bios -f FILE` | Update BIOS firmware from a local file |
| `update-bmc -f FILE [--no-preserve-config]` | Update BMC firmware. Preserves config by default. |

### Redfish System Management

```bash
bmctools redfish system <command>
```

| Command | Description |
|---|---|
| `reset [--type TYPE]` | Reset/reboot the system. Types: `GracefulRestart`, `ForceRestart`, `ForceOff`, `On`, etc. |
| `reset-types` | List supported reset types for this system |
| `info` | Get system information (manufacturer, system ID, IP) |

### Redfish TPM Management (ASUS)

```bash
bmctools redfish tpm <command>
```

| Command | Description |
|---|---|
| `set-state --state Enabled\|Disabled` | Set TPM state |

### Dell-Specific Commands

```bash
bmctools redfish dell <command>
```

#### NIC Discovery

| Command | Description |
|---|---|
| `get-nics` | List all NICs with MAC addresses, speed, and status |
| `get-nic-attrs -m MAC` | Get OEM network attributes for a specific NIC |

**Example:**

```bash
# List all NICs and their MAC addresses
bmctools redfish dell get-nics -o json-pretty

# Get detailed attributes for a specific NIC
bmctools redfish dell get-nic-attrs -m 04:32:01:D8:C0:B0
```

#### PXE Boot Setup

| Command | Description |
|---|---|
| `setup-pxe-boot -m MAC [--protocol PROTO] [--no-reboot]` | Enable PXE on a NIC and set it first in boot order. Handles the full workflow automatically. |
| `enable-pxe -m MAC [--protocol PROTO]` | Enable PXE on a NIC via BIOS Settings (stages only, requires reboot). |
| `boot-first-by-mac -m MAC [--type TYPE]` | Move a boot option to the front of the boot order by MAC address. |

The `setup-pxe-boot` command is the recommended way to configure PXE boot. It handles two scenarios automatically:

**Scenario 1: PXE already enabled on the NIC**
- Moves the PXE boot option to the front of the boot order
- No reboot required
- Returns `boot_order_set: true`

**Scenario 2: PXE not yet enabled**
- Configures a BIOS PxeDev slot for the NIC
- Sets one-time boot to PXE
- Reboots the system (unless `--no-reboot`)
- Returns `boot_order_set: false` - run `boot-first-by-mac` after reboot to make permanent

**Example automation workflow:**

```bash
# Step 1: Enable PXE and reboot if needed
result=$(bmctools redfish dell setup-pxe-boot -m 04:32:01:D8:C0:B0)

# Step 2: Check if boot order still needs to be set
boot_order_set=$(echo "$result" | jq -r '.boot_order_set')
if [ "$boot_order_set" = "false" ]; then
    # Wait for reboot to complete, then set permanent boot order
    sleep 300
    bmctools redfish dell boot-first-by-mac -m 04:32:01:D8:C0:B0 --type PXE
fi
```

**Protocol options:** `IPv4` (default), `IPv6`, `IPv4andIPv6`

#### Boot Options

| Command | Description |
|---|---|
| `get-boot-options [--no-cache]` | Get all Dell boot options |
| `onetime-boot --source SOURCE` | Set one-time boot source (`Pxe`, `Cd`, `Hdd`, `BiosSetup`, `None`) |

#### iDRAC Administration

| Command | Description |
|---|---|
| `create-role --name NAME --privileges PRIVS` | Create an iDRAC user role with a privilege bitmask |
| `local-access --enable\|--disable` | Toggle local iDRAC access |

### IPMI Commands

Requires `ipmitool` to be installed on the system.

```bash
bmctools ipmi <group> <command>
```

#### Power Management

| Command | Description |
|---|---|
| `ipmi power status` | Get power status |
| `ipmi power on` | Power on the system |
| `ipmi power off` | Power off the system |
| `ipmi power reset` | Hard reset the system |

#### BMC Management

| Command | Description |
|---|---|
| `ipmi bmc reset-warm` | Warm reset the BMC |
| `ipmi bmc reset-cold` | Cold reset the BMC |

#### System Event Log

| Command | Description |
|---|---|
| `ipmi sel list [--elist] [--raw] [--age AGE]` | List system event log. `--age` filters (e.g., `7d`, `24h`). |

#### Serial Over LAN

| Command | Description |
|---|---|
| `ipmi sol deactivate` | Deactivate SOL session |
| `ipmi sol looptest [--loops N]` | Run SOL loopback test |

#### Raw Commands

| Command | Description |
|---|---|
| `ipmi raw COMMAND` | Execute a raw IPMI command |

### RACADM Commands (Dell)

Requires `racadm` to be installed on the system.

```bash
bmctools racadm <group> <command>
```

| Command | Description |
|---|---|
| `get ENDPOINT [--format]` | Get configuration from an endpoint |
| `set ENDPOINT [--args ARGS]` | Set configuration on an endpoint |
| `storage get ENDPOINT` | Get storage configuration |
| `storage check-vdisk [--format]` | Check virtual disk status |
| `job view -j JOB_ID` | View job details |
| `job status -j JOB_ID` | Get job status |
| `job wait -j JOB_ID [--timeout SECS]` | Wait for job completion (default timeout: 300s) |

### Shorthand Aliases

These aliases map to the full commands for convenience:

| Alias | Equivalent Command |
|---|---|
| `bmctools get_boot_order` | `bmctools redfish boot get-order` |
| `bmctools set_boot_order` | `bmctools redfish boot set-order` |
| `bmctools get_boot_options` | `bmctools redfish boot list-options` |
| `bmctools reboot` | `bmctools redfish system reset` |
| `bmctools update_bios` | `bmctools redfish firmware update-bios` |
| `bmctools update_bmc` | `bmctools redfish firmware update-bmc` |
| `bmctools power_on` | `bmctools ipmi power on` |
| `bmctools power_off` | `bmctools ipmi power off` |
| `bmctools power_status` | `bmctools ipmi power status` |

## Python Library Reference

### Redfish Client

```python
from bmctools.redfish.redfish import Redfish

rf = Redfish(ip, username, password, verify_ssl=False, manufacturer=None)
```

The `manufacturer` parameter is optional. If not provided, it is auto-detected from the Redfish API. Valid values: `asus`, `dell`, `supermicro`.

#### Common Methods (All Manufacturers)

```python
rf.get_boot_order()                                    # -> list of boot option refs
rf.get_boot_options(nocache=False)                     # -> list of boot option dicts
rf.get_boot_option_by_mac(mac, type=None, nocache=False)  # -> boot option dict
rf.get_boot_option_by_alias(alias, nocache=False)      # -> boot option dict
rf.set_boot_order(["Boot0003", "Boot0001", ...])       # must include ALL options
rf.reset_system(reset_type=None)                       # GracefulRestart by default
rf.get_supported_reset_types()                         # -> dict with 'types' list
rf.get_firmware_inventory()                            # -> firmware version dict
rf.get_update_service_info()                           # -> update service status
rf.update_bmc_firmware(path, preserve_config=True)     # -> update status dict
rf.update_bios_firmware(path)                          # -> update status dict
```

#### Dell-Specific Methods

Access via `rf.manufacturer_class`:

```python
dell = rf.manufacturer_class

# NIC discovery
dell.get_network_interfaces()              # -> list of EthernetInterface dicts
dell.get_nic_attributes('04:32:01:D8:C0:B0')  # -> OEM attributes dict

# PXE setup
dell.setup_pxe_boot(mac, protocol='IPv4', reboot=True)  # -> result with boot_order_set flag
dell.enable_nic_pxe(mac, protocol='IPv4')                # -> stages BIOS PxeDev setting
dell.set_boot_first_by_mac(mac, boot_type='PXE')         # -> moves option to front

# Boot management
dell.set_next_onetime_boot('Pxe')          # one-time boot override

# iDRAC administration
dell.create_user_group(name, privileges)   # create iDRAC role
dell.toggle_local_idrac_access(disable)    # toggle local access (inverted semantics)
```

#### ASUS-Specific Methods

```python
asus = rf.manufacturer_class

asus.get_pending_boot_order()              # -> pending order from FutureState endpoint
asus.set_trusted_module_state('Enabled')   # TPM management
```

### Direct API Access

For operations not covered by the high-level interface:

```python
rf = Redfish('10.10.10.10', 'admin', 'password')

# Raw HTTP methods
response = rf.api.get('/redfish/v1/Systems')
response = rf.api.post('/redfish/v1/...', data={...})
response = rf.api.patch('/redfish/v1/...', data={...}, headers={...})
response = rf.api.delete('/redfish/v1/...')

# File uploads
rf.api.post_file('/redfish/v1/UpdateService/upload', '/path/to/firmware.bin')
rf.api.post_multipart('/redfish/v1/UpdateService/upload', '/path/to/firmware.bin', params)
```

### IPMI Client

```python
from bmctools.ipmi.ipmitool import IpmiTool

ipmi = IpmiTool('10.10.10.10', 'admin', 'password')
ipmi.power_status()       # -> power status string
ipmi.power_on()
ipmi.power_off()
ipmi.power_reset()
ipmi.bmc_reset_warm()
ipmi.bmc_reset_cold()
ipmi.sel_list(elist=False, raw=False, age='7d')
ipmi.sol_deactivate()
ipmi.ipmitool_command('raw 0x06 0x01')  # arbitrary ipmitool command
```

### RACADM Client

```python
from bmctools.racadm.racadm import Racadm

racadm = Racadm('10.10.10.10', 'admin', 'password')
racadm.get('BIOS.SysProfileSettings')
racadm.set('BIOS.SysProfileSettings', arguments=['SysProfile=Custom'])
racadm.check_vdisk()
racadm.jobqueue_view(job_id)
racadm.jobqueue_status(job_id)
racadm.jobqueue_wait(job_id)
```

## Architecture

### Manufacturer Detection Flow

```
Redfish.__init__()
  -> GET /redfish/v1/Systems          (find system ID)
  -> GET /redfish/v1/Systems/{id}     (read Manufacturer field)
  -> instantiate_manufacturer_class() (load DellFish, AsusFish, or SMCFish)
```

All high-level `Redfish` methods delegate to the manufacturer-specific class. You can also access the manufacturer class directly via `rf.manufacturer_class` for vendor-specific operations.

### Vendor Implementation Details

| Feature | Dell | ASUS | Supermicro |
|---|---|---|---|
| Boot order get/set | System + Settings endpoint | FutureState (SD) with ETag | Systems/1 |
| Boot option search by MAC | RelatedItem link traversal | UEFI device path parsing | Not implemented |
| Firmware updates | Not yet implemented | Multipart upload | Not yet implemented |
| PXE management | BIOS PxeDev attributes | N/A | N/A |
| NIC discovery | EthernetInterfaces | N/A | N/A |
| TPM management | N/A | OEM endpoint with ETag | N/A |

### Caching

Boot options are cached after the first retrieval to minimize API calls. Use `nocache=True` to force a fresh query:

```python
options = rf.get_boot_options()             # cached
options = rf.get_boot_options(nocache=True)  # fresh query
```

### Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error |
| 2 | Connection error |
| 3 | Feature not implemented for this manufacturer |
| 4 | Invalid arguments |
| 5 | File not found |
| 6 | Operation timeout |

## Development

### Docker Build

```bash
make build    # Build the Docker image
make shell    # Launch a shell in the container
```

The Docker build uses `--platform linux/amd64` for compatibility with vendor tools.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Author

Jesse Butryn
- GitHub: [@jessebutryn](https://github.com/jessebutryn)
