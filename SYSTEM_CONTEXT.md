# Victron RV System — Configuration Reference

## Access

| Resource | Details |
|----------|---------|
| SSH | `sshpass -f ~/.ssh/.venus_pass ssh root@venus.local` |
| Node-RED editor | `https://venus.local:1881/` |
| Node-RED dashboard | `https://venus.local:1881/dashboard/power-manager` |
| Remote Console | `https://venus.local/` |

---

## Hardware Inventory

### Inverter/Chargers
- **2x Quattro 48/5000/70-2x100 120V** on VE.Bus (`/dev/ttyS4`)
- Split-phase output; accepts 120V single-phase (L1 only, L2 inverts) or 240V split-phase (L1+L2 from shore)
- **"Switch as group" = OFF** — critical, enables 120V single-phase shore input
- DBUS service: `com.victronenergy.vebus.ttyS4` (aliased as `com.victronenergy.vebus/276` in Node-RED)
- Device instance: 276

### Battery
- **628Ah / 48V** bank
- **JK-BMS** on CAN1 (`com.victronenergy.battery.socketcan_can1`)
- **Lynx Shunt 1000A** on VE.Can / CAN0 (`com.victronenergy.battery.socketcan_can0_vi1_uc619137`)
- BMS actively controls DVCC charge limits — do NOT override DVCC

### Solar
- **SmartSolar MPPT VE.Can 150/100 rev2** on CAN0
- DBUS service: `com.victronenergy.solarcharger.socketcan_can0_vi0_uc279698`
- Node-RED alias: `com.victronenergy.solarcharger/0`

### Cerbo GX
- Venus OS v3.70
- **Relay 0**: `/Settings/Relay/Function` = 0 (Alarm) — **do not repurpose**
- **Relay 1**: `/Settings/Relay/1/Function` = 2 (Manual) — **used for charger disable**
- DBUS relay control: `com.victronenergy.system /Relay/1/State` (0=open, 1=closed)

### AC Inputs
- **AC Input 1**: Not configured (type 0)
- **AC Input 2**: Shore Power (type 3) — this is the active shore connection

### Other Devices
- 4x Ruuvi temperature sensors (BLE)
- 2x Mopeka propane sensors (BLE)

---

## Software

| Component | Version |
|-----------|---------|
| Venus OS | v3.70 |
| Node-RED | 4.1.1 |
| @victronenergy/node-red-contrib-victron | 1.6.60 |
| @flowfuse/node-red-dashboard | 1.30.1 |

Node-RED system paths:
- User dir: `/data/home/nodered/.node-red/`
- Flows file: `/data/home/nodered/.node-red/flows.json`
- Victron nodes (system): `/usr/lib/node_modules/@victronenergy/node-red-contrib-victron/`
- Dashboard nodes (user): `/data/home/nodered/.node-red/node_modules/@flowfuse/node-red-dashboard/`

---

## Current Node-RED Project: Power Manager

### Goal
Solar-priority operation with automatic shore power management:
1. **Auto mode**: connect shore when SOC drops to low threshold, disconnect at high threshold
2. **Shore powers AC loads only** — charger disable prevents grid-to-battery charging
3. **Solar continues charging** from MPPT regardless of shore state
4. **Manual overrides**: force shore on or off independent of SOC
5. **Independent AC charger control**: enable/disable charger separately from shore mode
6. Dashboard with mode switch, SOC gauge, threshold sliders, AC charger control, AC input limit, live readings

### Approach: Charge Current Control Assistant + Cerbo Relay 1

**Why other approaches were rejected:**
- **ESS Assistant + DisableCharge**: ESS requires "switch as group" ON — hard blocker
- **Load-following AC input current limit**: 13.4A minimum per Quattro = ~3,200W floor — too high
- **DVCC MaxChargeCurrent override**: Caps MPPT solar too; BMS controls DVCC actively
- **CGwacs MaxChargePower = 0**: Broken since Venus OS 3.5x

**How it works:**
1. Cerbo Relay 1 (Manual mode) is wired to both Quattros' AUX1 inputs in parallel
2. Charge Current Control Assistant on each Quattro: "disable charger at 0A when AUX1 closed"
3. Node-RED controls `IgnoreAcIn2` (DBUS) for shore acceptance and Cerbo Relay 1 (DBUS) for charger disable
4. Relay energized (State=1) → AUX1 shorted → charger disabled, AC passthrough continues
5. MPPT solar unaffected (DC-coupled, independent of Quattro charger)

### Shore Mode (Auto / On / Off)

The dashboard `Shore Mode` button group (`ui-button-group`) controls shore power acceptance:

```
AUTO (shore_mode = "auto")
  State machine enabled — IgnoreAcIn2 driven by SOC/voltage thresholds
  SHORE_OFF: IgnoreAcIn2 = 1 (reject shore)
  SHORE_ON:  IgnoreAcIn2 = 0 (accept shore)

ON (shore_mode = "on")
  State machine disabled — IgnoreAcIn2 = 0 (accept shore always)

OFF (shore_mode = "off")
  State machine disabled — IgnoreAcIn2 = 1 (reject shore always)
```

### Auto Mode State Machine

```
SHORE_OFF (default)
  IgnoreAcIn2 = 1 (reject shore)
  Battery powers loads, solar charges battery

  SOC <= threshold_low OR voltage <= voltage_threshold_low ──>

SHORE_ON
  IgnoreAcIn2 = 0 (accept shore)
  Shore powers loads, solar continues charging battery
  connect_reason = "soc" or "voltage" (whichever triggered)

  <── SOC >= threshold_high AND voltage > voltage_threshold_low
```

- 30-second minimum between state transitions
- SOC = 0 and voltage = 0 guards prevent false transitions on sensor failure
- State machine runs every 5 seconds
- **Deploy is non-disruptive** — all state (mode, thresholds, actuators) persists across deploys
- Init code only sets defaults for missing keys (fresh install)

### AC Charger Control (Independent)

The `AC Charger Toggle` (`ui-button-group`, ENABLED / DISABLED) controls the relay independently of shore mode:
- **ENABLED**: Relay 1 = 0 (open) — charger active
- **DISABLED**: Relay 1 = 1 (closed) — charger disabled via AUX1

This is a manual override — the state machine does NOT control the relay.
Typical use: keep charger disabled while shore is on (loads-only mode), or enable charger to bulk-charge from shore/generator.

### AC Input Current Limit

The `AC Input Limit Slider` sets `/Ac/In/2/CurrentLimit` on the VE.Bus (10–50A, 0.5A steps).
Reads current value on deploy via `ac_in2_limit_read` sensor node.

### Node-RED Flow Details

**Flow tab:** "Power Manager" (`id: aa00000000000001`)

**Sensor nodes:**
| Node name | Type | Service | Path |
|-----------|------|---------|------|
| `soc` | victron-input-system | com.victronenergy.system/0 | /Dc/Battery/Soc |
| `batt_current` | victron-input-system | com.victronenergy.system/0 | /Dc/Battery/Current |
| `batt_temp` | victron-input-system | com.victronenergy.system/0 | /Dc/Battery/Temperature |
| `batt_voltage` | victron-input-system | com.victronenergy.system/0 | /Dc/Battery/Voltage |
| `ac_out_l1` | victron-input-vebus | com.victronenergy.vebus/276 | /Ac/Out/L1/P |
| `ac_out_l2` | victron-input-vebus | com.victronenergy.vebus/276 | /Ac/Out/L2/P |
| `shore_in_l1` | victron-input-vebus | com.victronenergy.vebus/276 | /Ac/ActiveIn/L1/P |
| `shore_in_l2` | victron-input-vebus | com.victronenergy.vebus/276 | /Ac/ActiveIn/L2/P |
| `mppt_power` | victron-input-solarcharger | com.victronenergy.solarcharger/0 | /Yield/Power |
| `ac_in2_limit_read` | victron-input-vebus | com.victronenergy.vebus/276 | /Ac/In/2/CurrentLimit |

**Actuator nodes:**
| Node name | Type | Service | Path |
|-----------|------|---------|------|
| Set IgnoreAcIn2 | victron-output-custom | com.victronenergy.vebus/276 | /Ac/Control/IgnoreAcIn2 |
| Set Relay 1 (Charger Disable) | victron-output-relay | com.victronenergy.system/0 | /Relay/1/State |
| Set AC In 2 Limit | victron-output-custom | com.victronenergy.vebus.ttyS4 | /Ac/In/2/CurrentLimit |

**Dashboard controls:**
| Node name | Type | Purpose |
|-----------|------|---------|
| Shore Mode | ui-button-group | AUTO / ON / OFF shore power mode |
| Shore Status | ui-text | Shore status with connect reason (HTML colored) |
| AC Charger Toggle | ui-button-group | ENABLED / DISABLED AC charger control |
| AC Input Limit Slider | ui-slider | Shore input current limit (10–50A) |
| Low Threshold | ui-slider | SOC % to connect shore (auto mode) |
| High Threshold | ui-slider | SOC % to disconnect shore (auto mode) |
| Voltage Threshold | ui-slider | Battery voltage to connect shore (40–54V, auto mode) |

**Flow context keys** (readable via `GET https://venus.local:1881/context/flow/aa00000000000001`):
- `state`: "SHORE_OFF" | "SHORE_ON" (auto mode internal state)
- `connect_reason`: "soc" | "voltage" | null (what triggered SHORE_ON)
- `enabled`: boolean (true when shore_mode = "auto")
- `shore_mode`: "auto" | "on" | "off"
- `threshold_low`: number (default 40)
- `threshold_high`: number (default 60)
- `voltage_threshold_low`: number (default 48.0, volts)
- `manual_relay`: boolean (true = charger disabled)
- `ac_limit`: number (current limit in amps)
- `sensor_soc`, `sensor_batt_current`, `sensor_batt_temp`, `sensor_batt_voltage`
- `sensor_ac_out_l1`, `sensor_ac_out_l2`
- `sensor_shore_in_l1`, `sensor_shore_in_l2`
- `sensor_mppt_power`
- `last_state_change`: timestamp (ms)

**Dashboard:** `https://venus.local:1881/dashboard/power-manager`
- SOC gauge, shore mode buttons (auto/on/off), shore status text, threshold sliders
- AC charger buttons (enabled/disabled), AC input limit slider
- AC Out L1/L2 gauges, Shore In L1/L2 gauges, solar gauge
- Battery current widget, SOC and power history charts

---

## Key DBUS Paths

```bash
# Read SOC
dbus -y com.victronenergy.system /Dc/Battery/Soc GetValue

# Read battery current (positive = charging, negative = discharging)
dbus -y com.victronenergy.system /Dc/Battery/Current GetValue

# Read battery temperature (Celsius)
dbus -y com.victronenergy.system /Dc/Battery/Temperature GetValue

# Read battery voltage
dbus -y com.victronenergy.system /Dc/Battery/Voltage GetValue

# Read AC output power
dbus -y com.victronenergy.vebus.ttyS4 /Ac/Out/L1/P GetValue
dbus -y com.victronenergy.vebus.ttyS4 /Ac/Out/L2/P GetValue

# Read shore input power
dbus -y com.victronenergy.vebus.ttyS4 /Ac/ActiveIn/L1/P GetValue
dbus -y com.victronenergy.vebus.ttyS4 /Ac/ActiveIn/L2/P GetValue

# Control shore power acceptance
dbus -y com.victronenergy.vebus.ttyS4 /Ac/Control/IgnoreAcIn2 SetValue 0  # accept
dbus -y com.victronenergy.vebus.ttyS4 /Ac/Control/IgnoreAcIn2 SetValue 1  # reject

# Control Cerbo Relay 1 (charger disable via AUX1 wiring)
dbus -y com.victronenergy.system /Relay/1/State SetValue 1  # close (disable charger)
dbus -y com.victronenergy.system /Relay/1/State SetValue 0  # open (enable charger)

# AC input current limit
dbus -y com.victronenergy.vebus.ttyS4 /Ac/In/2/CurrentLimit GetValue
dbus -y com.victronenergy.vebus.ttyS4 /Ac/In/2/CurrentLimit SetValue 16

# Relay function (2 = manual, required for Node-RED control)
dbus -y com.victronenergy.settings /Settings/Relay/1/Function GetValue   # should be 2
dbus -y com.victronenergy.settings /Settings/Relay/Function GetValue     # Relay 0: 0 = alarm

# BatteryLife (should be 0 = disabled so Node-RED owns IgnoreAcIn2)
dbus -y com.victronenergy.settings /Settings/CGwacs/BatteryLife/State GetValue  # should be 0

# Hub4Mode (1 = BatteryLife mode, was not changed)
dbus -y com.victronenergy.settings /Settings/CGwacs/Hub4Mode GetValue

# VE.Bus state (8 = passthru/shore, 9 = inverting)
dbus -y com.victronenergy.vebus.ttyS4 /State GetValue

# AC Input 2 ignored state (read-only actual state)
dbus -y com.victronenergy.vebus.ttyS4 /Ac/State/IgnoreAcIn2 GetValue
```

---

## Configuration Already Applied

| Setting | Value | How |
|---------|-------|-----|
| Cerbo Relay 1 function | 2 (Manual) | SSH DBUS |
| BatteryLife State | 0 (Disabled) | SSH DBUS |
| Node-RED flow | Deployed | Admin API |

## Configuration Still Required (User Action)

### 1. Install Charge Current Control Assistant on both Quattros
Via VEConfigure + MK3-USB cable, connect to each Quattro individually:
- Assistants tab → Add → "Charge Current Control"
- Input: **AUX1**
- Enable: **"Disable the charger at 0A charge current"**
- Both trigger voltage thresholds: **~2V** (ensures dry-contact on/off behavior)
- Disable Virtual Switch first if enabled (VS and Assistants are mutually exclusive)
- Program each Quattro separately; reboot after both are done

### 2. Wire Cerbo Relay 1 → Both Quattros' AUX1 Inputs

```
Cerbo GX Relay 1                 Quattro #1 AUX1    Quattro #2 AUX1
  COM ──────────────┬──────────── Terminal 1 ─┐
                    │                         │
                    └──────────── Terminal 1 ─┘
  NO  ──────────────┬──────────── Terminal 2 ─┐
                    │                         │
                    └──────────── Terminal 2 ─┘
```

- Dry contact only — AUX1 has internal 5V pull-up, no external power needed
- Relay energized (Node-RED writes 1) → contacts close → AUX1 shorted → charger disabled
- Relay de-energized (0) → contacts open → AUX1 open → charger enabled

### 3. Verify After Wiring
```bash
# Test charger disable
dbus -y com.victronenergy.system /Relay/1/State SetValue 1
# Observe: battery current drops to near zero (only solar remains)

dbus -y com.victronenergy.system /Relay/1/State SetValue 0
# Observe: battery charging from AC resumes
```

---

## Safety Notes

- **Deploy is non-disruptive** — state persists, system continues operating through deploys
- **Shore ON/OFF modes**: direct manual control of IgnoreAcIn2, state machine inactive
- **AC charger control is independent**: can disable charger in any shore mode
- **Node-RED crash**: relay and IgnoreAcIn2 stay in last state; shore continues powering loads if accepted
- **Sensor failure guards**: SOC = 0 and voltage = 0 prevent false SHORE_ON transitions
- **30s minimum** between auto mode state transitions prevents relay cycling
- **PreventFeedback**: already set (no grid backfeed)
- **Switch-as-group OFF is safe**: no ESS algorithm, no phase coordination needed
