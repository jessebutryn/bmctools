# Use bmctools to Check and Enable PXE on Dell Servers

**Purpose**
- Verify whether a Dell NIC has PXE enabled and enable it if not, using `bmctools`.

**Prerequisites**
- `bmctools` installed and on `PATH`.
- Network access to the target server BMC / iDRAC and valid Redfish credentials.
- Target NIC MAC address (example format: `04:32:01:D8:C0:B0`).
 - BMC IP and credentials must be provided either via command-line flags or environment variables (examples below).

### Authentication examples
- Using command-line flags (use the `check_pxe` CLI alias):
```bash
bmctools check_pxe -i 10.10.10.10 -u admin -p password -m 04:32:01:D8:C0:B0
```
- Using environment variables (recommended for scripts/CI):
```bash
export BMC_HOST=10.10.10.10
export BMC_USERNAME=admin
export BMC_PASSWORD=password
bmctools check_pxe -m 04:32:01:D8:C0:B0
```

## Quick workflow
- Check PXE status (CLI alias):
```bash
bmctools check_pxe -m 04:32:01:D8:C0:B0
```

- Find a PXE boot option by MAC:
```bash
bmctools redfish boot find-by-mac -m 04:32:01:D8:C0:B0 --type PXE
```

-- Enable PXE and (optionally) reboot to apply (recommended full flow, alias):
```bash
bmctools setup_pxe_boot -m 04:32:01:D8:C0:B0
```

-- Stage PXE without reboot (alias):
```bash
bmctools setup_pxe_boot -m 04:32:01:D8:C0:B0 --no-reboot
```

-- Enable PXE only (stage BIOS PxeDev slot; reboot required to apply, alias):
```bash
bmctools enable_pxe -m 04:32:01:D8:C0:B0
```

-- After reboot, make the PXE option permanent (move to front, alias):
```bash
bmctools boot_first_by_mac -m 04:32:01:D8:C0:B0 --type PXE
```

## What each command does (short)
- `check-pxe`: Reports whether a PXE boot option exists and whether a BIOS PxeDev slot is configured for the NIC.  
- `find-by-mac`: Locates a boot option entry matching the MAC (use `--type PXE` to filter).  
- `enable-pxe`: Patches Dell BIOS attributes to configure a PxeDev slot for the NIC (stages change; reboot required).  
- `setup-pxe-boot`: High-level flow — if PXE exists, promotes it; otherwise stages PXE and can reboot to apply.  
- `boot-first-by-mac`: Reorders boot order to put the NIC’s PXE option first (run after reboot if required).

## Example end-to-end
1. Check current state:
```bash
bmctools check_pxe -m 04:32:01:D8:C0:B0
```
2. If `pxe_boot_option.exists` is false or `pxe_bios_slot.enabled` is false:
```bash
bmctools setup_pxe_boot -m 04:32:01:D8:C0:B0
```
3. If `setup-pxe-boot` reboots the system, after it returns:
```bash
bmctools boot_first_by_mac -m 04:32:01:D8:C0:B0 --type PXE
```

## Expected outputs / keys to check
- From `check-pxe`: `pxe_boot_option.exists` (true/false), `pxe_bios_slot` (slot number and `enabled`).  
- From `setup-pxe-boot`: `pxe_already_enabled` (bool), `pxe_slot`, `rebooted` (bool), and `message`.  
- From `boot-first-by-mac`: `promoted` (boot reference) and `boot_order`.

## Troubleshooting
- "No NIC found": verify MAC format and network reachability to iDRAC/Redfish.  
- "No available PxeDev slot": PxeDev1–4 are all used; free a slot in iDRAC or use an already-assigned adapter.  
- PATCH or reset failures: confirm BMC account privileges and that Redfish endpoints are writable and reachable.  
- If you staged PXE (`--no-reboot` or `enable-pxe`), remember to reboot and run `boot-first-by-mac` to make changes persistent.

## Notes / tips
- MAC formats accepted: `04:32:01:D8:C0:B0` or `043201D8C0B0` (prefer colon-separated).  
- `setup-pxe-boot` is the recommended single-command workflow for most cases.  
- Use `--no-reboot` to stage changes during maintenance windows.

---

File created by automation: `PXE-Guide.md` — paste this directly into Notion.
