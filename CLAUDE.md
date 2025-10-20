# SiLA2-Based MCPs for Lab Automation

## Overview

This guide covers building Model Context Protocols (MCPs) for lab automation equipment using the SiLA2 (Standardized in Laboratory Automation 2) framework. The focus is on the Byonoy absorbance 96 microplate reader as the first hardware integration.

## Why SiLA2?

SiLA2 provides a standardized, command-based communication protocol for laboratory devices. It abstracts hardware differences into consistent command structures, making it ideal for creating MCPs that can scale across different instruments and vendors. Rather than writing device-specific code, you define capabilities and commands that the AI agent can understand and execute.

## Project Context

You're building an AI agent for automated optimization of liquid handling parameters in colorimetric assays. The Byonoy reader generates the quantitative feedback (absorbance measurements) that closes the optimization loop. A SiLA2-based MCP ensures this feedback mechanism is reliable, standardized, and AI-accessible.

## SiLA2 Fundamentals

SiLA2 defines three core elements:

**Commands**: Actions the device performs (e.g., `RunAssay`, `ReadPlate`). Commands take parameters, execute, and return results.

**Properties**: State information about the device (e.g., `TemperatureControl`, `LightSource`). Properties can be queried or set.

**Metadata**: Definitions of what the device can do, written in XML. This tells the AI agent what commands exist and what parameters they accept.

## Architecture: Byonoy MCP Structure

```
byonoy-mcp/
├── server.py                 # Main MCP server (FastMCP)
├── sila2_definitions.xml     # SiLA2 command/property definitions
├── byonoy_driver.py          # Byonoy SDK wrapper
├── commands/
│   ├── run_assay.py
│   ├── read_plate.py
│   ├── set_wavelength.py
│   └── validate_plate.py
├── properties/
│   ├── device_status.py
│   ├── temperature.py
│   └── available_wavelengths.py
├── utils/
│   ├── data_parser.py        # Parse Byonoy SDK responses
│   ├── validation.py         # Input validation
│   └── error_handling.py
└── tests/
    ├── test_commands.py
    └── test_integration.py
```

## Step 1: Understand the Byonoy SDK

Before writing the MCP, map the Byonoy absorbance 96 capabilities from its SDK documentation (referenced in your setup guide):

**Key information to extract**:
- Available methods for reading wells
- Wavelength range and resolution
- Temperature control options
- Plate format support
- Data output format (raw absorbance, kinetic reads, etc.)
- Error states and recovery procedures

Document this as a capabilities matrix:

```
| Capability         | Method           | Input Parameters        | Output              |
|--------------------|------------------|-------------------------|---------------------|
| Read absorbance    | read_plate()     | wavelength, wells       | Dict[well, value]   |
| Set temperature    | set_temp()       | temp_celsius            | bool (success)      |
| Get device status  | get_status()     | None                    | DeviceStatus object |
```

## Step 2: Define SiLA2 Commands

Map Byonoy capabilities to SiLA2 commands. Each command should represent a discrete, meaningful action for your optimization workflow.

### Example: ReadPlate Command

```xml
<Command Name="ReadPlate">
  <Description>Read absorbance from specified wells at a given wavelength</Description>
  <Parameter Name="wavelength_nm" Type="Integer">
    <Description>Wavelength in nanometers</Description>
    <Constraint Min="350" Max="750"/>
  </Parameter>
  <Parameter Name="wells" Type="StringList">
    <Description>Well positions (e.g., ['A1', 'A2', 'B1'] or 'AllWells')</Description>
  </Parameter>
  <ReturnValue Name="absorbance_data" Type="DataMap">
    <Description>Dictionary mapping well ID to absorbance value</Description>
  </ReturnValue>
  <ReturnValue Name="timestamp" Type="DateTime">
    <Description>Server-side timestamp of measurement</Description>
  </ReturnValue>
</Command>
```

### Example: RunAssay Command

```xml
<Command Name="RunAssay">
  <Description>Execute a complete assay protocol with multiple reads</Description>
  <Parameter Name="plate_id" Type="String">
    <Description>Unique identifier for the plate</Description>
  </Parameter>
  <Parameter Name="wavelengths" Type="IntegerList">
    <Description>List of wavelengths to measure</Description>
  </Parameter>
  <Parameter Name="number_of_reads" Type="Integer">
    <Description>Number of kinetic reads to perform</Description>
    <Constraint Min="1" Max="100"/>
  </Parameter>
  <Parameter Name="interval_seconds" Type="Integer">
    <Description>Time between reads</Description>
    <Constraint Min="5" Max="3600"/>
  </Parameter>
  <ReturnValue Name="assay_result_id" Type="String">
    <Description>Unique identifier for this assay run</Description>
  </ReturnValue>
</Command>
```

Define commands that directly serve your optimization loop:
- **ReadPlate**: Core measurement action
- **RunAssay**: Multi-point kinetic measurement
- **ValidatePlate**: Check plate presence and integrity before reading
- **GetCalibrationStatus**: Verify device calibration

## Step 3: Define SiLA2 Properties

Properties expose device state and configuration:

```xml
<Property Name="DeviceStatus" Type="String">
  <Description>Current device operational state</Description>
  <AllowedValues>
    <Value>Ready</Value>
    <Value>Busy</Value>
    <Value>Calibrating</Value>
    <Value>Error</Value>
  </AllowedValues>
</Property>

<Property Name="TemperatureControl" Type="Boolean">
  <Description>Whether temperature control is active</Description>
  <Settable/>
</Property>

<Property Name="CurrentTemperature" Type="Float">
  <Description>Current plate temperature in Celsius</Description>
</Property>

<Property Name="AvailableWavelengths" Type="IntegerList">
  <Description>Wavelengths the device can measure</Description>
</Property>
```

Properties enable the AI agent to:
- Check if the device is ready before sending commands
- Monitor device state during an optimization run
- Query capabilities (wavelengths, temp range) to validate parameters

## Step 4: Implement the MCP Server

Use FastMCP (as shown in your setup guide) to expose SiLA2 commands as MCP tools:

```python
#!/usr/bin/env python3
"""
SiLA2-based MCP for Byonoy Absorbance 96 Microplate Reader
"""
from mcp.server.fastmcp import FastMCP
from byonoy_driver import ByonoyReader
from commands import ReadPlate, RunAssay, ValidatePlate
from properties import DeviceStatus, CurrentTemperature
from utils import validate_wavelength, parse_well_list
import json

# Initialize
mcp = FastMCP("Byonoy SiLA2 MCP")
reader = ByonoyReader(sdk_path="path/to/byonoy/sdk")

# Properties (queryable device state)
@mcp.property()
def device_status() -> str:
    """Current operational state of the reader"""
    try:
        status = reader.get_status()
        return status.state  # "Ready", "Busy", "Error", etc.
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.property()
def current_temperature() -> float:
    """Current plate temperature in Celsius"""
    return reader.get_temperature()

@mcp.property()
def available_wavelengths() -> list:
    """Wavelengths available on this device"""
    return reader.get_wavelengths()

# Commands (actions the device performs)
@mcp.tool()
def read_plate(wavelength_nm: int, wells: str = "AllWells") -> dict:
    """
    Read absorbance from specified wells at a given wavelength.
    
    Parameters:
    - wavelength_nm: Wavelength in nanometers (350-750)
    - wells: Well positions as comma-separated string (e.g., 'A1,A2,B1') or 'AllWells'
    
    Returns: Dictionary with well IDs as keys and absorbance values as values
    """
    # Validation
    validate_wavelength(wavelength_nm)
    well_list = parse_well_list(wells)
    
    try:
        result = reader.read_absorbance(wavelength_nm, well_list)
        return {
            "success": True,
            "data": result,
            "wavelength": wavelength_nm,
            "timestamp": reader.get_timestamp()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "wavelength": wavelength_nm
        }

@mcp.tool()
def run_assay(plate_id: str, wavelengths: list, num_reads: int, 
              interval_seconds: int) -> dict:
    """
    Execute a complete assay with kinetic measurements.
    
    Parameters:
    - plate_id: Unique identifier for this plate
    - wavelengths: List of wavelengths to measure [e.g., 405, 450]
    - num_reads: Number of kinetic reads (1-100)
    - interval_seconds: Time between reads in seconds (5-3600)
    
    Returns: Assay result ID and summary
    """
    try:
        assay_id = reader.start_assay(
            plate_id=plate_id,
            wavelengths=wavelengths,
            num_reads=num_reads,
            interval=interval_seconds
        )
        return {
            "success": True,
            "assay_id": assay_id,
            "plate_id": plate_id,
            "expected_duration_seconds": interval_seconds * (num_reads - 1)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "plate_id": plate_id
        }

@mcp.tool()
def get_assay_result(assay_id: str) -> dict:
    """
    Retrieve results from a completed or running assay.
    
    Parameters:
    - assay_id: Assay ID returned from run_assay
    
    Returns: Raw data dictionary or status if still running
    """
    try:
        result = reader.get_assay_data(assay_id)
        return {
            "success": True,
            "assay_id": assay_id,
            "data": result,
            "status": "complete"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "assay_id": assay_id
        }

@mcp.tool()
def validate_plate() -> dict:
    """
    Check plate presence and device readiness before measurement.
    
    Returns: Validation status and any warnings
    """
    try:
        is_valid = reader.check_plate()
        device_ok = reader.check_device_health()
        return {
            "success": True,
            "plate_detected": is_valid,
            "device_ready": device_ok,
            "device_status": reader.get_status().state
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    mcp.run(transport='stdio')
```

## Step 5: Byonoy Driver Wrapper

Create a robust wrapper around the Byonoy SDK that handles connection, error recovery, and data parsing:

```python
# byonoy_driver.py
from byonoy.sdk import ByonoySDK
from typing import Dict, List
import time

class ByonoyReader:
    def __init__(self, sdk_path: str):
        self.sdk = ByonoySDK(sdk_path)
        self.connected = False
        self.last_error = None
        self.connect()
    
    def connect(self):
        """Establish connection to reader"""
        try:
            self.sdk.connect()
            self.connected = True
        except Exception as e:
            self.last_error = e
            self.connected = False
            raise
    
    def read_absorbance(self, wavelength: int, wells: List[str]) -> Dict[str, float]:
        """
        Read absorbance with error handling and retry logic
        """
        if not self.connected:
            raise RuntimeError("Reader not connected")
        
        if wavelength < 350 or wavelength > 750:
            raise ValueError(f"Wavelength {wavelength} out of range")
        
        try:
            raw_data = self.sdk.read_plate(wavelength, wells)
            return self._parse_absorbance_data(raw_data)
        except Exception as e:
            self.last_error = e
            raise
    
    def get_status(self):
        """Get device operational state"""
        return self.sdk.get_device_status()
    
    def check_plate(self) -> bool:
        """Verify plate is present and properly positioned"""
        return self.sdk.check_plate_present()
    
    def _parse_absorbance_data(self, raw_data) -> Dict[str, float]:
        """Parse SDK response into clean well:value dictionary"""
        parsed = {}
        for well, value in raw_data.items():
            parsed[well] = float(value)
        return parsed
```

## Step 6: Integration with Your Optimization Agent

The AI agent will interact with these tools to close the optimization loop:

```
1. Agent decides on liquid handling parameters (aspiration speed, mixing volume, etc.)
2. Agent calls OpenTrons protocol with those parameters
3. Agent calls read_plate or run_assay via this MCP
4. Byonoy returns absorbance measurements
5. Agent calculates R² and CV from measurements
6. Agent adjusts parameters based on metrics
7. Loop repeats
```

This MCP provides the quantitative feedback mechanism. Every iteration, the agent can validate its parameter choices against real measurement data.

## Step 7: Testing and Deployment

**Unit tests**: Mock the Byonoy SDK to test command logic without hardware

```python
# tests/test_commands.py
def test_read_plate_validation():
    """Ensure wavelength validation works"""
    mock_reader = MagicMock()
    result = read_plate(wavelength_nm=1000, wells="A1")
    assert result["success"] == False
    assert "wavelength" in result["error"].lower()
```

**Integration tests**: Test against actual hardware or SDK simulator

**Deployment**:
```bash
uv add mcp
mcp install server.py
mcp dev server.py  # For development
```


# SiLA Client Example

This example demonstrates how to remotely perform a readout and retrieve the results using the Absorbance/Luminescence 96 App's SiLA remote control server.
## Setup

Install the Python dependencies, preferably into a virtual environment.

```
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## First Run

Start the Absorbance/Luminescence 96 App with command line switch `--sila --sila-insecure` to start the app's SiLA server with disabled transport security. Make sure the device is attached and recognized by the app.

Now run the client script.

```
python sila_client.py
```

The app should load the example protocol included with this example and perform the readout. The script should then write the results to text files in the working directory.

## Further Reading and Troubleshooting

Refer to the [SiLA IFU](https://byonoy.com/site/assets/files/2100/ifu_sila2_abs96_230921.pdf) for a complete description of the available configuration options and SiLA commands.

The app logs errors and diagnostics. To access the log file click the cog wheel in the lower left corner and then click "Export app log file..." in the "Maintenance" section.
