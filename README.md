# BMCTools

A Python library and CLI for managing Baseboard Management Controllers (BMCs) across multiple vendors. Supports Redfish, IPMI, and RACADM protocols with automatic manufacturer detection and vendor-specific extensions.

## Features

- **Multi-Protocol Support**: Redfish API, IPMI (via ipmitool), and RACADM (Dell)
- **Automatic Manufacturer Detection**: Connects to the BMC, identifies the vendor, and loads the correct implementation
- **Vendor-Specific Implementations**:
  - **Dell iDRAC**: Full boot management, PXE setup, NIC discovery, user roles, local access control
  - **ASUS**: Boot order staging via FutureState endpoint, TPM management, firmware updates
  - **Supermicro**: Boot order and boot option queries
  - **Gigabyte (GIGA Computing)**: Boot management with ETag support, NIC discovery, boot-first-by-MAC
  - **Cisco (CIMC/UCS)**: Boot management, NIC discovery, boot-first-by-MAC
  - **Lenovo (XClarity Controller / ThinkSystem)**: Boot management with standard and OEM boot order, one-time network boot, NIC discovery, boot-first-by-MAC
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
| `-m, --manufacturer` | `BMC_MANUFACTURER` | Force manufacturer: `asus`, `dell`, `supermicro`, `gigabyte`, `cisco`, `lenovo` |
| `-k, --insecure` | `BMC_INSECURE` | Disable SSL verification (default: enabled) |
| `--secure` | | Enable SSL verification (overrides `-k`) |
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

**Network boot on Aivres (AMI-based BMC):** Aivres systems expose no writable
`Boot.BootOrder`, and `BootSourceOverrideTarget` only allows the generic
targets (`None`, `Pxe`, `Hdd`, `Cd`, `Diags`, `BiosSetup`, `Usb`) — there is no
`UefiBootNext`/`UefiTarget` to point at a specific NIC. Network boot therefore
sets the generic `Pxe` one-time override and leaves NIC selection to the BIOS
boot order. The PATCH to `/redfish/v1/Systems/1` requires an `If-Match` ETag
header (the BMC returns HTTP 428 without one), which is handled automatically.

```bash
# Trigger a one-time PXE (network) boot on Aivres, then reboot to apply
bmctools redfish boot set-override -t Pxe --mode Once
bmctools redfish system reset --type ForceRestart
```

**Network boot on Lenovo (XClarity Controller):** XCC honors the standard
one-time boot source override, so `-t Pxe --mode Once` is all a network boot
needs — the choice of *port* then falls to the network boot order.

```bash
# Trigger a one-time PXE (network) boot on Lenovo, then reboot to apply
bmctools redfish boot set-override -t Pxe --mode Once
bmctools redfish system reset --type ForceRestart
```

Three XCC behaviours are worth knowing, all verified on a ThinkSystem SR685a V3
(XCC `16E-6.10`, UEFI `R5E122B`):

- **`Boot.BootOrder` is read-only.** It is published and reflects the in-effect
  order, but PATCHing it returns `PropertyNotWritable`. The only writable boot
  order is the Lenovo OEM resource
  `/Systems/1/Oem/Lenovo/BootSettings/BootOrder.BootOrder`, whose
  `BootOrderNext` is a list of device *names* (`Network`, `Ubuntu`,
  `CD/DVD Rom`, `Hard Disk`). `set_boot_order()` accepts either namespace and
  translates `BootNNNN` references to device names automatically when the
  standard array is refused, so callers need not care which the firmware allows.
- **A specific device cannot be named in an override.** XCC advertises
  `UefiTarget` (not `UefiBootNext`) but restricts
  `UefiTargetBootSourceOverride` to an undisclosed value list, rejecting both
  UEFI device paths and `BootNNNN` references; `BootNext` is read-only. To
  network boot a chosen port, promote it in the network boot order and set a
  generic one-time `Pxe` override — which is what `set_boot_first_by_mac()` and
  `set_next_onetime_boot(mac_address=...)` do.
- **The OEM boot settings wedge after a write.** Following any PATCH to a
  `BootSettings` member, the whole sub-tree answers HTTP 500 ("internal service
  error") for several minutes — and indefinitely while the host sits in the UEFI
  setup menu (`Oem.Lenovo.SystemStatus == "SystemRunningInSetup"`), which holds
  the settings and blocks the BMC's sync. The rest of the Redfish service stays
  healthy. Read the order *before* writing; read-after-write will fail.
  `BootOrderNext` (staged) is the writable list and `BootOrderCurrent` is what
  is in effect, so reverting means writing `BootOrderCurrent` back to
  `BootOrderNext`.

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

### Raw Redfish API Access

Explore any Redfish endpoint directly:

```bash
bmctools redfish raw <URI>
```

| Command | Description |
|---|---|
| `raw /redfish/v1` | Get Redfish service root |
| `raw /redfish/v1/Systems` | List systems |
| `raw /redfish/v1/Systems/{id}` | Get full system resource |
| `raw /redfish/v1/Managers` | List BMC managers |

**Examples:**

```bash
# Browse the Redfish service root
bmctools redfish raw /redfish/v1 -o json-pretty

# Inspect a specific system
bmctools redfish raw /redfish/v1/Systems/1 -o json-pretty

# Check available Redfish endpoints
bmctools redfish raw /redfish/v1/Chassis

# Explore OEM extensions
bmctools redfish raw /redfish/v1/Managers/1
```

### KCS Control (OS-to-BMC passthrough)

Disable the KCS interface — the in-band IPMI passthrough that lets the host OS
talk to the BMC — so the BMC can only be managed out-of-band. Applied entirely
over Redfish; the manufacturer is auto-detected.

```bash
bmctools redfish kcs <command>
```

| Command | Description |
|---|---|
| `disable` | Disable KCS / OS-to-BMC passthrough (BMC accessible out-of-band only) |
| `enable` | Enable KCS / OS-to-BMC passthrough |
| `status` | Show the current KCS interface state |

**Supported manufacturers:**

| Manufacturer | Mechanism |
|---|---|
| Dell (iDRAC) | Sets iDRAC attribute `LocalSecurity.1.LocalConfig` to `Enabled`/`Disabled` (tries the iDRAC 9 `Attributes` endpoint, then the iDRAC 10 OEM `DellAttributes` endpoint). |
| Supermicro | Lowers/raises the KCS interface privilege — `Administrator` (enabled) vs `Operator` (disabled). May require a BMC license (SKU). |
| ASUS and others | Not supported (reported as `NotImplementedError`). |

**Examples:**

```bash
# Disable in-band OS-to-BMC access (harden to out-of-band only)
bmctools redfish kcs disable -i 10.10.10.10 -u admin -p password

# Check the current state
bmctools redfish kcs status -o json-pretty

# Re-enable in-band access
bmctools redfish kcs enable
```

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
| `bmctools get_nics` | `bmctools redfish dell get-nics` |
| `bmctools boot_first_by_mac` | `bmctools redfish dell boot-first-by-mac` |
| `bmctools power_on` | `bmctools ipmi power on` |
| `bmctools power_off` | `bmctools ipmi power off` |
| `bmctools power_status` | `bmctools ipmi power status` |

## Python Library Reference

### Redfish Client

```python
from bmctools.redfish.redfish import Redfish

rf = Redfish(ip, username, password, verify_ssl=False, manufacturer=None)
```

The `manufacturer` parameter is optional. If not provided, it is auto-detected from the Redfish API. Valid values: `asus`, `dell`, `supermicro`, `gigabyte`, `cisco`, `lenovo`.

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

#### Gigabyte-Specific Methods

```python
giga = rf.manufacturer_class

giga.get_network_interfaces()                          # -> list of EthernetInterface dicts
giga.set_boot_first_by_mac(mac, boot_type='PXE')      # -> moves option to front of boot order
giga.get_firmware_inventory()                          # -> firmware version dict
```

Gigabyte BMCs (AMI-based) require ETag headers on PATCH operations. This is handled automatically by the `GigaFish` implementation.

#### Cisco-Specific Methods

```python
cisco = rf.manufacturer_class

cisco.get_network_interfaces()                         # -> list of EthernetInterface dicts
cisco.set_boot_first_by_mac(mac, boot_type='PXE')     # -> moves option to front of boot order
cisco.get_firmware_inventory()                         # -> firmware version dict
```

Cisco CIMC systems use serial-number-based system IDs (e.g., `WZP...`), which are auto-discovered.

#### Lenovo-Specific Methods

```python
lenovo = rf.manufacturer_class

lenovo.set_next_onetime_boot('Pxe')                     # one-time boot override
lenovo.set_next_onetime_boot('Pxe', mac_address=mac)    # promote that NIC, then PXE once
lenovo.set_boot_first_by_mac(mac, boot_type='PXE')      # network-boot that NIC first (persistent)
lenovo.get_network_boot_order()                         # -> per-NIC network boot order
lenovo.find_network_boot_entry(mac, boot_type='PXE')    # -> the UEFI boot string for a NIC
lenovo.set_network_boot_first_by_mac(mac)               # promote a NIC among network devices
lenovo.get_network_interfaces()                         # -> list of EthernetInterface dicts
lenovo.get_firmware_inventory()                         # -> firmware version dict
lenovo.get_bios_settings()                              # -> BIOS attributes
lenovo.set_bios_settings({'BootModes_SystemBootMode': 'UEFIMode'})  # staged on /Bios/Pending
```

`get_boot_order()` reads the standard `Boot.BootOrder` array when present and
falls back to the OEM `BootOrderNext` list. `set_boot_order()` accepts either
`BootNNNN` references or OEM device names, and — because `Boot.BootOrder` is
read-only on current XCC — translates references to device names and writes the
OEM resource when the standard PATCH is refused. The result's `mechanism` key
reports which path was used.

Boot options on ThinkSystem are **category-level** (`Network`, `HardDisk`,
`CD_DVDRom`, plus installed OS loaders) with `VenHw_`-style device paths that
encode no MAC, so a NIC cannot be named in the main boot order. Individual ports
live in the OEM `BootOrder.NetworkBootOrder` resource, whose entries name slot,
protocol and adapter — and, depending on the adapter, the MAC:

```
UEFI:   SLOT 10 (C7/0/0) PXE IPv4  Mellanox ConnectX-6 Dx ... - E8:EB:D3:FD:CD:60
UEFI:   SLOT 11 (28/0/0) PXE IPv4  Broadcom 57416 10GBASE-T 2-port OCP Ethernet Adapter
```

`set_boot_first_by_mac()` therefore does two things on this platform: it promotes
the port in the network boot order *and* puts the generic network option first in
the main boot order. Adapters whose entry carries no MAC (the Broadcom OCP ports
above) can only be selected by string, via `set_boot_order()` on the network
member.

BIOS attributes are staged on the pending-settings resource discovered from
`@Redfish.Settings` (`/Bios/Pending` on XCC) rather than the conventional
`/Bios/Settings`.

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
  -> instantiate_manufacturer_class() (load DellFish, AsusFish, SMCFish, GigaFish, or CiscoFish)
```

All high-level `Redfish` methods delegate to the manufacturer-specific class. You can also access the manufacturer class directly via `rf.manufacturer_class` for vendor-specific operations.

### Vendor Implementation Details

| Feature | Dell | ASUS | Supermicro | Gigabyte | Cisco |
|---|---|---|---|---|---|
| Boot order get/set | System + Settings endpoint | FutureState (SD) with ETag | Systems/1 | Systems/{id} with ETag | Systems/{id} |
| Boot option search by MAC | RelatedItem link traversal | UEFI device path parsing | Not implemented | UEFI device path parsing | UEFI device path parsing |
| Boot-first-by-MAC | Yes | N/A | N/A | Yes | Yes |
| Firmware inventory | Not yet implemented | Multipart upload | Not yet implemented | FirmwareInventory | FirmwareInventory |
| PXE management | BIOS PxeDev attributes | N/A | N/A | N/A | N/A |
| NIC discovery | EthernetInterfaces | EthernetInterfaces | N/A | EthernetInterfaces | EthernetInterfaces |
| TPM management | N/A | OEM endpoint with ETag | N/A | N/A | N/A |

### Manufacturer Detection Strings

The following strings are matched (case-insensitive) from the Redfish `Manufacturer` field:

| Manufacturer | Matched Strings |
|---|---|
| Dell | `dell`, `dell inc.` |
| ASUS | `asus`, `asustekcomputerinc.`, `asustek computer inc.` |
| Supermicro | `supermicro` |
| Gigabyte | `gigabyte`, `giga computing` |
| Cisco | `cisco`, `cisco systems inc`, `cisco systems inc.` |
| Lenovo | any string starting with `lenovo` (e.g. `Lenovo`, `Lenovo(R)`, `Lenovo Global Technology (United States) Inc.`) |

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
