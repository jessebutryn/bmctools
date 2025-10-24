# BMCTools

A collection of Python tools for interacting with Baseboard Management Controllers (BMCs) using various protocols.

## Modules

- **misc**: Miscellaneous utilities
- **racadm**: Tools for Dell iDRAC using RACADM
- **redfish**: Redfish API client for managing servers
- **sum**: Tools for Supermicro IPMI using SUM (SuperMicro Update Manager)

## Installation

Clone the repository and install the package:

```bash
git clone https://github.com/yourusername/bmctools.git
cd bmctools
pip install .
```

## Usage

Import the desired module and use the classes provided.

### Redfish Example

```python
from src.bmctools.redfish.fishapi import RedfishAPI

api = RedfishAPI(ip='192.168.1.100', user='admin', password='password')
response = api.get('/redfish/v1/Systems')
print(response.json())
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
