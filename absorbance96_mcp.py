#!/usr/bin/env python3
"""
Automated Absorbance MCP Server - AI Agent interface to Byonoy Automate Absorbance 96 Reader
"""
from mcp.server.fastmcp import FastMCP
import requests
import json

# Initialize the FastMCP server
mcp = FastMCP("Agent AutoAbsorb")

import byonoy_devices as byonoy
import statistics

# Global variable to store device handle
#byonoy_device_handle = None

@mcp.tool()
def connect_byonoy_reader() -> str:
    """Connect to the Byonoy plate reader"""
    global byonoy_device_handle
    try:
        num_devices = byonoy.available_devices_count()
        if num_devices == 0:
            return "No Byonoy devices found"
        
        devices = byonoy.available_devices()
        result_code, device_handle = byonoy.open_device(devices[0])
        
        if result_code == byonoy.ErrorCode.NO_ERROR:
            byonoy_device_handle = device_handle
            return f"Connected to Byonoy device successfully. Handle: {device_handle}"
        else:
            return f"Failed to connect: {result_code}"
    except Exception as e:
        return f"Error: {str(e)}"



"""  Need to update the initialize and measure tooling.
"""

@mcp.tool()

def read_tartrazine_absorbance(wavelength: int = 450, step: str = "initialize") -> str:
    """Read absorbance values. Use step='initialize' first, then step='measure' after inserting plate"""
    global byonoy_device_handle
    try:
        if byonoy_device_handle is None:
            return "Please connect to Byonoy reader first"
        
        if step == "initialize":
            # Check slot is empty for initialization
            if byonoy.device_slot_status_supported(byonoy_device_handle):
                result_code, slot_status = byonoy.get_device_slot_status(byonoy_device_handle)
                if result_code == byonoy.ErrorCode.NO_ERROR and slot_status != byonoy.DeviceSlotState.EMPTY:
                    return f"❌ Remove plate first - slot status: {slot_status}"
            
            # Initialize measurement
            if byonoy.abs96_available_wavelengths_supported(byonoy_device_handle):
                result_code, abs_wavelengths = byonoy.abs96_get_available_wavelengths(byonoy_device_handle)
                if wavelength not in abs_wavelengths:
                    return f"Wavelength {wavelength} not available. Available: {abs_wavelengths}"
                
                config = byonoy.Abs96SingleMeasurementConfig()
                config.sample_wavelength = wavelength
                
                result_code = byonoy.abs96_initialize_single_measurement(byonoy_device_handle, config)
                if result_code == byonoy.ErrorCode.NO_ERROR:
                    return f"✅ Measurement initialized at {wavelength}nm. INSERT PLATE NOW, then run with step='measure'"
                else:
                    return f"❌ Initialize failed: {result_code}"
            
        elif step == "measure":
            # Check if plate is inserted
            if byonoy.device_slot_status_supported(byonoy_device_handle):
                result_code, slot_status = byonoy.get_device_slot_status(byonoy_device_handle)
                if result_code == byonoy.ErrorCode.NO_ERROR and slot_status == byonoy.DeviceSlotState.EMPTY:
                    return "❌ No plate detected. Please insert plate first."
            
            # Take actual measurement
            config = byonoy.Abs96SingleMeasurementConfig()
            config.sample_wavelength = wavelength

            result_code, values = byonoy.abs96_single_measure(byonoy_device_handle, config)
            if result_code == byonoy.ErrorCode.NO_ERROR:
                return f"📊 Absorbance values at {wavelength}nm: {values}"
            else:
                return f"❌ Measurement failed: {result_code}. Check plate positioning."
        
        else:
            return "Invalid step. Use step='initialize' or step='measure'"
            
    except Exception as e:
        return f"Error: {str(e)}"


#Bullshit
@mcp.tool()
def calculate_assay_metrics(absorbance_values: str, concentrations: str = "0,10,20,50,100,200") -> str:
    """Calculate R² and CV from tartrazine standard curve data"""
    try:
        # Parse inputs
        abs_list = [float(x.strip()) for x in absorbance_values.split(',')]
        conc_list = [float(x.strip()) for x in concentrations.split(',')]
        
        # Take first 6 values for standard curve
        abs_curve = abs_list[:6]
        
        # Calculate R² (simplified linear regression)
        n = len(abs_curve)
        mean_conc = statistics.mean(conc_list)
        mean_abs = statistics.mean(abs_curve)
        
        numerator = sum((conc_list[i] - mean_conc) * (abs_curve[i] - mean_abs) for i in range(n))
        denom_conc = sum((conc_list[i] - mean_conc) ** 2 for i in range(n))
        denom_abs = sum((abs_curve[i] - mean_abs) ** 2 for i in range(n))
        
        r_squared = (numerator ** 2) / (denom_conc * denom_abs) if denom_conc * denom_abs > 0 else 0
        
        # Calculate CV for replicates (assuming triplicates)
        cv_values = []
        for i in range(0, min(len(abs_list), 18), 3):  # Every 3 values
            replicate_group = abs_list[i:i+3]
            if len(replicate_group) == 3:
                cv = (statistics.stdev(replicate_group) / statistics.mean(replicate_group)) * 100
                cv_values.append(cv)
        
        avg_cv = statistics.mean(cv_values) if cv_values else 0
        
        return f"R²: {r_squared:.4f}, Average CV: {avg_cv:.2f}%"
    except Exception as e:
        return f"Error calculating metrics: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport='stdio')