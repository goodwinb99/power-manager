# Victron Power Manager — Solar-Priority Shore Power Automation for Venus OS

A Node-RED flow for Venus OS (Cerbo GX) that automatically manages shore power based on battery state of charge and voltage, while keeping solar charging active at all times.

## What It Does

- **Auto mode**: connects shore power when SOC or voltage drops below configurable thresholds, disconnects when SOC recovers
- **Shore powers AC loads only** — an optional charger-disable relay prevents grid-to-battery charging, so solar remains the primary charge source
- **Manual overrides**: force shore on or off regardless of SOC
- **Independent AC charger control**: enable or disable the inverter/charger independently of shore mode
- **Dashboard**: real-time monitoring with SOC gauge, power readings, threshold sliders, and mode controls

## How It Works

The flow uses two independent control mechanisms:

1. **Shore acceptance** — writes `IgnoreAcIn2` via DBUS to accept or reject AC Input 2 (shore power)
2. **Charger disable** — energizes a Cerbo GX relay wired to the master inverter's AUX1 input, which triggers the Charge Current Control Assistant to set charge current to 0A

This means shore power can pass through to AC loads without charging the battery, leaving solar as the sole charge source.

## Requirements

### Hardware

- **Victron Cerbo GX** (or other Venus OS GX device) running Venus OS v3.60+
- **Victron inverter/charger** (MultiPlus, Quattro, etc.) on VE.Bus — single or split-phase
- **Battery with BMS** reporting SOC to Venus OS (via CAN, VE.Bus, serial, etc.)
- **MPPT solar charger** (optional but recommended — this is a solar-priority system)
- **One available Cerbo relay** set to Manual mode (for charger disable feature)

### Prerequisites

- **No ESS Assistant** — this project replaces ESS-style shore management. ESS also requires "switch as group" ON, which prevents single-phase shore input on split-phase inverter systems
- **No Virtual Switch** — the Virtual Switch is mutually exclusive with Assistants (like the Charge Current Control assistant used here). If Virtual Switch is configured, it must be removed in VEConfigure before adding the assistant

### Software

- **[Venus OS Large](https://www.victronenergy.com/live/venus-os:large)** firmware image — required for Node-RED support (the standard image does not include it)
- **[@flowfuse/node-red-dashboard](https://flows.nodered.org/node/@flowfuse/node-red-dashboard)** v1.20+ — install via Node-RED palette manager
- **@victronenergy/node-red-contrib-victron** — pre-installed with Venus OS

On your workstation (for SSH access and deployment):
- **Python 3** — for `flows_manager.py`
- **sshpass** — for non-interactive SSH (`brew install sshpass` on macOS, `apt install sshpass` on Debian/Ubuntu)

## Setup

### 1. Enable SSH and Node-RED on Venus OS

Via the Remote Console:
- Settings → General → Set Access Level → **Superuser**
- Settings → General → Set Root Password (set a strong password)
- Settings → Services → Node-RED → Enable

The `flows_manager.py deploy` command uses `curl` to POST to the Node-RED API over the network, so SSH isn't strictly required for deployment. However, SSH is needed for DBUS commands during setup and debugging.

To enable passwordless SSH from your workstation, save the root password to a file:
```bash
echo 'your-root-password' > ~/.ssh/.venus_pass
chmod 600 ~/.ssh/.venus_pass
```

Then connect with:
```bash
sshpass -f ~/.ssh/.venus_pass ssh root@venus.local
```

### 2. Install Dashboard

In the Node-RED editor (`https://<gx-device>:1881/`):
- Menu → Manage palette → Install tab
- Search for `@flowfuse/node-red-dashboard` and install

### 3. Configure Cerbo Relay for Charger Disable

Skip this section if you don't need the charger-disable feature.

Set one Cerbo relay to Manual mode via DBUS (replace relay index as needed):
```bash
dbus -y com.victronenergy.settings /Settings/Relay/1/Function SetValue 2
```

Wire the relay's COM and NO terminals to the **master** inverter's AUX1 input (polarity doesn't matter — it's a dry contact). Slave inverters in a parallel/split-phase system follow the master's charge current via VE.Bus and don't need wiring.

### 4. Install Charge Current Control Assistant

Via VEConfigure + MK3-USB cable.

> **Warning:** VEConfigure reboots the inverter when writing settings, which momentarily cuts AC power. Run VEConfigure on a laptop with a charged battery — do not rely on AC power from the inverter during this process.

**Master inverter:**
1. Assistants tab → Add → **"Charge Current Control"**
2. When to change: **"when AC Input 2 is active"** (or whichever input is shore)
3. How to change: **"Change the charge current based on voltage on auxiliary input 1"**
4. DC charge current regulation:
   - **0 A** when voltage is lower than **2.00 V** (relay closed = charger off)
   - **52 A** (or your max) when voltage is higher than **4.00 V** (relay open = charger on)
5. Check: **"Disable the charger when charge current should be zero"**
6. Write settings — VEConfigure will reboot the inverter automatically

**Slave inverter (if split-phase/parallel):**
1. Only the "Disable the charger when charge current should be zero" checkbox is presented — check it
2. Write settings — VEConfigure will reboot the inverter automatically

### 5. Disable BatteryLife

BatteryLife is a Venus OS feature that automatically manages grid/battery usage by controlling the `IgnoreAcIn` DBUS flags — the same flags this project uses. If BatteryLife is active, it will fight with Node-RED for control of shore acceptance, causing unpredictable behavior.

Since this project fully replaces that logic with its own SOC/voltage-based state machine, BatteryLife must be disabled:
```bash
dbus -y com.victronenergy.settings /Settings/CGwacs/BatteryLife/State SetValue 0
```

> If you're using ESS with BatteryLife for grid-tied self-consumption, this project is not the right fit — it's designed for off-grid systems where shore power is optional and solar is the primary charge source.

### 6. Update Service References in flows.json

The flow references specific DBUS services that vary by installation. Before deploying, update these in `flows.json` to match your system:

| Service in flows.json | What it is | How to find yours |
|---|---|---|
| `com.victronenergy.vebus/276` | VE.Bus inverter (device instance) | Remote Console → Device List → your inverter |
| `com.victronenergy.vebus.ttyS4` | VE.Bus inverter (serial port) | `dbus -y` and look for your vebus service |
| `com.victronenergy.solarcharger/0` | MPPT solar charger | Remote Console → Device List → your MPPT |
| `com.victronenergy.system/0` | System-level readings | Usually `system/0` on all installations |
| `IgnoreAcIn2`, `/Ac/In/2/CurrentLimit` | AC input number for shore | Most systems use AC Input 1 — change `2` to `1` in all DBUS paths if so |

For single-inverter systems, the service references work the same way — just use your inverter's device instance and serial port.

### 7. Deploy

```bash
# From this repo's root directory:
python3 flows_manager.py deploy
```

Or import `flows.json` manually via the Node-RED editor (Menu → Import).

## Dashboard

Access at `https://<gx-device>:1881/dashboard/power-manager`

- **Shore Mode** — AUTO / ON / OFF buttons for shore power acceptance
- **AC Charger** — AUTO / ON / OFF buttons for inverter/charger control
- **Shore / Charger Status** — current state with connect reason; shows warning when VE.Bus is unavailable
- **SOC Gauge** — battery state of charge
- **Shore Threshold Sliders** — SOC % to connect/disconnect shore (auto mode)
- **Charger Threshold Sliders** — SOC % to enable/disable AC charger (auto mode)
- **Voltage Safety Slider** — shared voltage threshold that triggers both shore + charger
- **AC Input Limit Slider** — shore input current limit
- **Power Gauges** — AC output L1/L2, shore input L1/L2, solar power
- **Battery** — current and voltage
- **History Charts** — SOC and power over time

## flows_manager.py

A utility for managing `flows.json` without hand-editing JSON. Use as a CLI or import in Python scripts.

```bash
python3 flows_manager.py deploy               # Deploy flows.json to Node-RED
python3 flows_manager.py get <node-id>         # Print a node as JSON
python3 flows_manager.py verify <id> [id...]   # Check that node IDs exist
python3 flows_manager.py list                  # List all nodes
```

See [CLAUDE.md](CLAUDE.md) for the full API when writing change scripts.

## Safety

- **Deploy is non-disruptive** — all state (mode, thresholds, actuators) persists across deploys
- **VEConfigure protection** — both state machines freeze when VE.Bus is unavailable (state 250), preventing shore disconnection during inverter programming
- **Sensor failure guards** — SOC = 0 and voltage = 0 are treated as sensor failures and won't trigger state transitions in either state machine
- **Dual-threshold disconnect** — shore will only disconnect when *both* SOC and voltage are above their thresholds, preventing premature disconnection if one reading recovers while the other hasn't
- **Separate 30-second cooldowns** — shore and charger auto transitions have independent minimum intervals to prevent relay cycling
- **Threshold cross-validation** — sliders reject values that violate the ordering constraint (charger enable < shore connect, charger disable ≤ shore disconnect)
- **Protective charger default** — charger auto defaults to CHARGER_ON in the hysteresis zone, assuming the battery may need help
- **Node-RED crash** — relay and IgnoreAcIn2 stay in their last state; shore continues if it was accepted

## Adapting to Your System

The flows ship configured for a specific system (dual Quattro 48/5000 split-phase, 628Ah 48V LFP bank, 150/100 MPPT). Most values are easy to adjust via `flows_manager.py` scripts.

### Voltage Threshold

The voltage safety slider and its defaults are battery-voltage-specific:

| Item | Current (48V) | 12V LFP | 24V LFP | 12V Lead-Acid |
|------|---------------|---------|---------|----------------|
| Voltage slider range | 40–54V | 10–14.6V | 20–29.2V | 10–15V |
| Default voltage threshold | 48.0V | 12.0V | 24.0V | 11.5V |

Update three nodes:

1. **Voltage Threshold slider** (`aa000000000000f2`) — `min`, `max`
2. **Set Voltage Threshold handler** (`aa000000000000f3`) — clamp range in `Math.max(min, Math.min(max, ...))`
3. **State Machine init** (`aa00000000000030`, `initialize` field) — default for `voltage_threshold_low`

### Single-Phase Systems

The dashboard ships with separate L1 and L2 gauges for AC Out and Shore In, designed for split-phase inverter setups. On a single-phase system, the L2 gauges will always read 0W.

To clean up the dashboard, remove the L2 gauge nodes:
- AC Out L2: `aa000000000000b0`
- Shore In L2: `aa000000000000b1`

The L2 sensor nodes and the rest of the flow are safe to leave as-is — all L2 values fall back to 0 when the DBUS paths don't exist, so the Power History chart (which sums L1+L2) works correctly on both single-phase and split-phase systems without changes.

### Gauge Ranges and Color Thresholds

Gauge maximums and color breakpoints reflect the installed inverter/charger/solar capacity:

| Gauge | Node ID | Max | Color breakpoints | Sized for |
|-------|---------|-----|-------------------|-----------|
| AC Out L1 | `aa00000000000072` | 5000W | green→orange 2500W, orange→red 4000W | 5kVA inverter |
| AC Out L2 | `aa000000000000b0` | 5000W | green→orange 2500W, orange→red 4000W | 5kVA inverter |
| Shore In L1 | `aa00000000000075` | 6000W | green→orange 3000W, orange→red 5000W | 50A shore |
| Shore In L2 | `aa000000000000b1` | 6000W | green→orange 3000W, orange→red 5000W | 50A shore |
| Solar | `aa00000000000073` | 5000W | grey→yellow 500W, yellow→green 2000W | 150/100 MPPT |

Update with `flows_manager.py`: `update(flows, '<id>', max=<new_max>, segments=[...])`.

### Battery Current Widget

The battery current bar graph (`aa00000000000074`, ui-template) is hardcoded for ±200A. To adjust for your battery bank, edit the template's `max` variable and the scale labels (`-200A`, `0`, `+200A`).

### Power History Chart

The Power History chart (`aa000000000000c3`) has `ymax=12000` (12kW), sized for dual 5kVA inverters. Update with `update(flows, 'aa000000000000c3', ymax=<your_max>)`.

### AC Input Limit Slider

The AC Input Limit slider (`aa000000000000e5`) ranges 0–50A. Adjust `max` to match your shore breaker rating or inverter input limit.

### DBUS Service References

See [Setup § Update Service References](#6-update-service-references-in-flowsjson) — these must match your specific hardware.

## File Structure

```
flows.json          # Node-RED flow definition
flows_manager.py    # Flow management utility
CLAUDE.md           # AI assistant instructions
SYSTEM_CONTEXT.md   # Hardware and software configuration reference
VENUS_PATCHES.md    # Venus OS patches (if needed)
```

## License

This project is provided as-is for personal use. Use at your own risk — always verify your electrical system configuration with qualified professionals.
