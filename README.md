# BMCTools

A Python library for interacting with Baseboard Management Controllers (BMCs) using various protocols and vendor-specific implementations.

## Features

- **Redfish API Support**: Unified interface for managing servers via Redfish
- **Vendor-Agnostic Implementations**: 
  - ASUS
  - Supermicro
  - Dell iDRAC
- **Boot Management**: Get/set boot order, query boot options, search by MAC address
- **IPMI Tools**: Interface for ipmitool operations
- **Session Management**: Automatic Redfish session handling with token-based authentication

## Supported Modules

- **redfish**: Redfish API client with manufacturer-specific implementations
- **racadm**: Tools for Dell iDRAC using RACADM
- **ipmi**: IPMI tool wrappers
- **sum**: Supermicro Update Manager (SUM) tools
- **misc**: Miscellaneous utilities

## Installation

### From Source

```bash
git clone https://github.com/jessebutryn/bmctools.git
cd bmctools
pip install -e .
```

### Requirements

- Python 3.9+
- requests

## Usage

### Basic Redfish Example

```python
from bmctools.redfish.redfish import Redfish

# Initialize connection
redfish = Redfish(
    ip='192.168.1.100',
    username='admin',
    password='password',
    verify_ssl=False
)

# Auto-detects manufacturer and loads appropriate implementation
print(f"Manufacturer: {redfish.manufacturer}")
print(f"System ID: {redfish.system_id}")
```

### Boot Management

```python
from bmctools.redfish.redfish import Redfish

redfish = Redfish('192.168.1.100', 'admin', 'password')

# Get current boot order
boot_order = redfish.get_boot_order()
print(f"Current boot order: {boot_order}")

# Get all boot options with details
boot_options = redfish.get_boot_options()
for option in boot_options:
    print(f"{option['Name']}: {option['DisplayName']}")

# Get boot option by MAC address
option = redfish.get_boot_option_by_mac('10:70:FD:29:E5:22')
print(f"Found: {option['BootOptionReference']}")

# Set new boot order (must include ALL boot options)
new_order = [
    "Boot0003",
    "Boot0004", 
    "Boot0000",
    "Boot0001",
    "Boot0002",
    "Boot0005"
]
redfish.set_boot_order(new_order)

# Get pending boot order (from FutureState/SD endpoint)
pending = redfish.get_pending_boot_order()

# Reboot to apply changes
redfish.reset_system()  # Auto-detects supported reset type
# Or specify reset type explicitly:
# redfish.manufacturer_class.reset_system('ForceRestart')
```

### Direct Redfish API Access

```python
from bmctools.redfish.redfish import Redfish

redfish = Redfish('192.168.1.100', 'admin', 'password')

# GET request
response = redfish.api.get('/redfish/v1/Systems')
print(response.json())

# POST request with data
payload = {'ResetType': 'ForceRestart'}
response = redfish.api.post(
    '/redfish/v1/Systems/Self/Actions/ComputerSystem.Reset',
    data=payload
)

# PATCH request with custom headers
headers = {'If-Match': 'W/"12345"'}
response = redfish.api.patch(
    '/redfish/v1/Systems/Self/SD',
    data={'Boot': {'BootOrder': ['Boot0000']}},
    headers=headers
)
```

## Architecture

### Redfish Module Structure

- `fishapi.py`: Low-level Redfish HTTP client with session management
- `redfish.py`: High-level interface with manufacturer detection
- `asusfish.py`: ASUS-specific implementation 
- `smcfish.py`: Supermicro-specific implementation

### Manufacturer Detection

The library automatically detects the manufacturer from the Redfish API and loads the appropriate vendor-specific implementation.  All methods can be executed from the redfish.py class regardless of manufacturer.

### Caching

Where possible options and methods are cached after the first retrieval to avoid redundant API calls:

```python
# Uses cache if available
options = redfish.get_boot_options()

# Force fresh API call
options = redfish.get_boot_options(nocache=True)
```

## Development

### Docker Build

Build the Docker image with all dependencies:

```bash
make build
```

Launch a shell in the container:

```bash
make shell
```

**Note**: The Docker build uses `--platform linux/amd64` for compatibility with vendor tools.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

Jesse Butryn
- GitHub: [@jessebutryn](https://github.com/jessebutryn)

