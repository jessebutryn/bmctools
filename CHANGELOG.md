# Changelog

All notable changes to bmctools are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [0.1.6] - 2026-03-21

### Added
- Full type annotations across the entire codebase (all public and private methods)
- Google-style docstrings with `Args`, `Returns`, and `Raises` sections on all functions

### Changed
- `redfish/fishapi.py`: `post_file()` and `post_multipart()` now have explicit parameter and return type annotations
- `redfish/redfish.py`: `Redfish.__init__` has a full docstring; `get_system_id()` and `get_manufacturer()` have expanded docstrings
- `redfish/gigafish.py`: All previously undocumented methods (`get_boot_order`, `get_boot_options`, `get_boot_option_by_mac`, `get_boot_option_by_alias`, `set_boot_order`, `get_supported_reset_types`, `reset_system`, `get_firmware_inventory`, `get_network_interfaces`, `_system_uri`) now have docstrings
- `redfish/ciscofish.py`: Same — all methods now documented
- `misc/utils.py`: `is_command()`, `is_dir_writeable()`, `is_older_than_unit()` rewritten with proper Google-style docstrings
- `cli/formatters/__init__.py`: `format_output()` now typed `(Any, str) -> str`
- `cli/commands/common.py`: All helpers (`wrap_command`, `read_file_lines`, `parse_comma_list`, `confirm_action`, `show_progress`, `validate_file_exists`, `parse_key_value_pairs`) fully typed
- `cli/commands/ipmi.py`, `cli/commands/racadm.py`, `cli/commands/redfish.py`: All setup, handler, dispatch, and alias functions typed with `argparse.Namespace` and return types

### Fixed
- Version inconsistency between `bmctools/__init__.py` (`0.1.4`) and `setup.py` / `cli/__init__.py` (`0.1.5`) — all sources now unified at `0.2.0`

---

## [0.1.5] - 2026-02-01

### Added
- Cisco (CIMC/UCS) Redfish implementation (`CiscoFish`)
- Boot management, NIC discovery, and firmware inventory for Cisco systems
- `boot-first-by-mac` support for Gigabyte and Cisco
- `get_network_interfaces()` on all manufacturer classes
- BIOS settings commands (`redfish bios get`, `set`, `get-boot`)
- Boot source override get/set (`redfish boot get-override`, `set-override`)

### Changed
- Gigabyte ETag support added for PATCH requests
- Dell `get_boot_option_by_mac` now follows `RelatedItem` links for more reliable MAC matching
- CLI `--insecure` defaults to `True` (most BMC environments use self-signed certs)

---

## [0.1.4] - 2026-01-10

### Added
- Gigabyte (GIGA Computing) Redfish implementation (`GigaFish`)
- `get_boot_option_by_alias()` for Gigabyte and ASUS
- `set_boot_first_by_mac()` helper on manufacturer classes
- Dell PXE automation: `enable_nic_pxe()`, `setup_pxe_boot()`, `check_pxe_status()`
- Dell NIC attribute discovery: `get_nic_attributes()`
- Shorthand CLI aliases (`enable_pxe`, `setup_pxe_boot`, `boot_first_by_mac`, etc.)

---

## [0.1.3] - 2025-12-15

### Added
- ASUS TPM management (`set_trusted_module_state`)
- ASUS pending boot order via FutureState endpoint
- Firmware update commands for BIOS and BMC (`redfish firmware update-bios/update-bmc`)
- Firmware inventory and update service status

---

## [0.1.2] - 2025-11-20

### Added
- Dell iDRAC Redfish implementation (`DellFish`)
- Boot order management for Dell systems
- One-time boot source override (`set_next_onetime_boot`)
- User role/group creation on Dell iDRAC
- Local iDRAC access toggle

---

## [0.1.1] - 2025-10-30

### Added
- ASUS Redfish implementation (`AsusFish`)
- Boot order get/set with full validation
- `get_boot_option_by_mac()` with UEFI device path parsing

---

## [0.1.0] - 2025-10-01

### Added
- Initial release
- Supermicro Redfish implementation (`SMCFish`)
- Core `RedfishAPI` HTTP session wrapper
- `IpmiTool` wrapper for power management, SEL, and SOL
- `Racadm` wrapper for Dell racadm CLI
- CLI entry point (`bmctools`) with `redfish`, `ipmi`, and `racadm` subcommands
- JSON, table, and text output formatters
- Environment variable configuration (`BMC_HOST`, `BMC_USERNAME`, `BMC_PASSWORD`, etc.)
