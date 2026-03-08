# Low Voltage Shore Connect Threshold

## Summary

Add a secondary shore connect trigger based on battery voltage. Whichever fires first — SOC or voltage — causes a SOLAR_ONLY -> GRID_ASSIST transition. Disconnect remains SOC-only (no high voltage disconnect). This is a safety measure to protect against deep discharge.

## Changes

### New sensor node: `batt_voltage`
- Type: victron-input-system
- Service: com.victronenergy.system/0
- Path: /Dc/Battery/Voltage
- Wired into State Machine (aa00000000000030)

### New dashboard slider: Voltage Threshold
- ui-slider in Thresholds group (aa00000000000013), order 3
- Label: "Connect Shore (Voltage)"
- Range: 40.0V–54.0V, step 0.1
- Default: 48.0V

### New function node: Set Voltage Threshold
- Validates input, stores to flow context as `voltage_threshold_low`
- Updates threshold status text

### State Machine modification
- Read `sensor_batt_voltage` and `voltage_threshold_low` from flow context
- SOLAR_ONLY -> GRID_ASSIST transition:
  - Before: `soc > 0 && soc <= thresholdLow`
  - After: `(soc > 0 && soc <= thresholdLow) || (voltage > 0 && voltage <= voltageThresholdLow)`
- Voltage > 0 guard prevents false trigger on sensor failure
- GRID_ASSIST -> SOLAR_ONLY remains unchanged (SOC >= thresholdHigh only)
- Add voltage to dashboard payload

### Threshold Text modification
- Before: `Connect: 47% → Disconnect: 55%`
- After: `Connect: 47% or ≤48.0V → Disconnect: 55%`

### Set Low Threshold / Set High Threshold text updates
- Include voltage threshold in the status text output

### Flow context additions
- `voltage_threshold_low`: number (default 48.0)
- `sensor_batt_voltage`: number

### Node IDs for new nodes
- batt_voltage sensor: aa000000000000f1
- Voltage Threshold slider: aa000000000000f2
- Set Voltage Threshold function: aa000000000000f3
