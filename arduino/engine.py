#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Moteur commun ESP32 extrait du builder B4E ; configuration propre a chaque projet.

Point d entree utilisateur : python3 build.py depuis la racine du depot.
Reglages : build-config.json. Ne pas lancer ce moteur directement.

This script provides a command-line interface to compile, upload, and manage
firmware for ESP32 projects using arduino-cli and esptool.

Features:
- Auto-detect serial port
- Build sketch with arduino-cli
- Flash firmware, partitions, and LittleFS
- SHA256 verification
- Colored output

Author: David Baldwin – B4E SRL
Date: 2025-11-11
"""

import os
from common.console import safe_print as print
import csv
import sys
import argparse
import subprocess
import shutil
from typing import List, Dict, Optional, Tuple
import hashlib
from datetime import datetime
from pathlib import Path
import re
from .lib_manager import LibraryManager
from .library_checker import check_requirements
from .partitions import validate_layout

# ============================================================================
# CONFIGURATION
# ============================================================================

# This is an internal engine. User configuration and entry point live at repo root.
from .project import load_config, fqbn, project_path, firmware_version, check_environment
from .project import current
ROOT, BUILD_CONFIG = current()
SKETCH_FOLDER = str(project_path(ROOT, BUILD_CONFIG['paths']['sketch']))


def find_sketch_file():
    files = list(Path(SKETCH_FOLDER).glob('*.ino'))
    if len(files) != 1:
        raise FileNotFoundError(f'Exactly one .ino expected in {SKETCH_FOLDER}')
    return files[0].name


SKETCH_NAME = find_sketch_file()
FQBN = fqbn(BUILD_CONFIG)
PARTITIONS_CSV = str(project_path(ROOT, BUILD_CONFIG['paths']['partitions']))
BUILD_PATH = str(project_path(ROOT, BUILD_CONFIG['paths']['build']))
BAUD_RATE = str(BUILD_CONFIG['upload_baud'])
ARDUINO_CLI_PATH = 'arduino-cli'
LITTLEFS_FILENAME = SKETCH_NAME.replace('.ino', '-littlefs.bin')
FIRMWARE_DIR = str(project_path(ROOT, BUILD_CONFIG['paths']['firmware']))
LITTLEFS_PATH = os.path.join(FIRMWARE_DIR, LITTLEFS_FILENAME)

# ============================================================================
# FIRMWARE METADATA (read from .ino file)
# ============================================================================

def read_firmware_metadata() -> Dict[str, str]:
    """Extract firmware metadata from version.h and .ino sketch file."""
    metadata = {
        "FW_VERSION": "unknown",
        "FW_DATE": "unknown",
        "FW_TIME": "unknown",
        "FW_BOARD": "unknown",
        "FW_AUTHOR": "unknown",
    }

    # Files to search for metadata (in order of priority)
    files_to_check = [
        os.path.join(SKETCH_FOLDER, "src", "fw_config", "version.h"),
        SKETCH_NAME,
    ]

    try:
        for filepath in files_to_check:
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    content = f.read()

                # Extract #define values
                for key in metadata.keys():
                    if metadata[key] == "unknown":  # Only update if not already found
                        pattern = rf'#define {key}\s+"([^"]+)"'
                        match = re.search(pattern, content)
                        if match:
                            metadata[key] = match.group(1)

        return metadata
    except Exception as e:
        print_color(f"⚠️  Could not read firmware metadata: {e}", "yellow")
        return metadata

# Load firmware metadata at startup
FW_METADATA = read_firmware_metadata()
FW_METADATA["FW_VERSION"] = firmware_version(ROOT, BUILD_CONFIG)[1]
FW_METADATA["FW_BOARD"] = BUILD_CONFIG["board"]["id"]
FW_VERSION = FW_METADATA["FW_VERSION"]
FW_DATE = FW_METADATA["FW_DATE"]
FW_TIME = FW_METADATA["FW_TIME"]
FW_BOARD = FW_METADATA["FW_BOARD"]
FW_AUTHOR = FW_METADATA["FW_AUTHOR"]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def print_color(message: str, color: str = "default", end: str = "\n"):
    """Prints a message in a given color."""
    colors = {
        "header": "\033[95m",
        "blue": "\033[94m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "bold": "\033[1m",
        "underline": "\033[4m",
        "end": "\033[0m",
    }
    color_code = colors.get(color, "")
    print(f"{color_code}{message}{colors['end']}", end=end)


def run_command(command: List[str], cwd: str = ".") -> bool:
    """Runs a command and streams its output."""
    print_color(f"▶️  Running: {' '.join(command)}", "blue")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd,
            bufsize=1,
            universal_newlines=True,
        )
        if process.stdout:
            for line in process.stdout:
                print(line, end="")
        process.wait()
        if process.returncode != 0:
            print_color(f"❌ Command failed with exit code {process.returncode}", "red")
            return False
        print_color("✅ Command completed successfully", "green")
        return True
    except FileNotFoundError:
        print_color(f"❌ Command not found: {command[0]}", "red")
        return False
    except Exception as e:
        print_color(f"❌ Unexpected error: {e}", "red")
        return False


def get_partitions() -> Optional[Dict[str, Dict[str, str]]]:
    """Parses the partitions.csv file."""
    partitions = {}
    try:
        with open(PARTITIONS_CSV, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or row[0].strip().startswith("#"):
                    continue
                parts = [item.strip() for item in row]
                if len(parts) >= 5:
                    name, type_, subtype, offset, size = parts[0:5]
                    partitions[name] = {"offset": offset, "size": size}
        return partitions
    except FileNotFoundError:
        print_color(f"❌ Partitions file not found: {PARTITIONS_CSV}", "red")
        return None


def find_serial_port() -> Optional[List[str]]:
    """
    Intelligently finds serial ports connected to ESP32 devices.

    Detects across platforms:
    - macOS: /dev/cu.usbmodem* (CDC-ACM)
    - Linux: /dev/ttyUSB*, /dev/ttyACM*
    - Windows: COM*

    Filters by manufacturer/product info when available.
    """
    try:
        from serial.tools import list_ports
    except ImportError:
        print_color("⚠️  'pyserial' not installed. Cannot auto-detect port.", "yellow")
        print_color("   Install with: pip install pyserial", "yellow")
        return None

    print_color("🔎 Searching for ESP32 serial port(s)...", "blue")

    esp32_ports = []

    for port in list_ports.comports():
        device = port.device
        manufacturer = port.manufacturer or ""
        description = port.description or ""
        product = port.product or ""

        # Debug info
        # print(f"  Found: {device} | {manufacturer} | {description}")

        # Check for ESP32 indicators
        is_esp32 = (
            "ESP32" in description.upper() or
            "ESP32" in product.upper() or
            "Espressif" in manufacturer or
            "Silicon Labs" in manufacturer or  # CP2102 (common ESP32 programmer)
            "FTDI" in manufacturer or          # FTDI (alternative programmer)
            "CH340" in description or          # CH340 (another common programmer)
            "CH341" in description
        )

        # Platform-specific detection
        is_likely_esp32_port = (
            (device.startswith("/dev/cu.usbmodem")) or  # macOS CDC-ACM
            (device.startswith("/dev/cu.wch")) or       # macOS WCH chips
            (device.startswith("/dev/ttyUSB")) or       # Linux USB
            (device.startswith("/dev/ttyACM")) or       # Linux CDC-ACM
            (device.startswith("COM") and len(device) <= 4)  # Windows
        )

        # Add port if it matches ESP32 signature or likely pattern
        if is_esp32 or is_likely_esp32_port:
            esp32_ports.append({
                "device": device,
                "description": description,
                "manufacturer": manufacturer,
                "product": product,
                "confidence": "high" if is_esp32 else "medium"
            })

    if not esp32_ports:
        print_color("❌ No ESP32 serial port found", "red")
        return None

    # Print found ports with details
    for i, p in enumerate(esp32_ports):
        conf = p["confidence"]
        color = "green" if conf == "high" else "yellow"
        details = p["description"] or p["product"] or p["manufacturer"] or "Unknown device"
        print_color(f"   {i+1}. {p['device']:20} [{conf:6}] {details}", color)

    return [p["device"] for p in esp32_ports]


def get_port_with_confirmation() -> Optional[str]:
    """Interactively gets a serial port from the user with confirmation."""
    detected_ports = find_serial_port()

    if detected_ports is None:
        print_color("❓ Enter serial port manually (e.g., /dev/cu.usbmodem123): ", "yellow", end="")
        port = input().strip()
        return port if port else None

    if len(detected_ports) > 1:
        print_color("⚠️  Multiple ports found:", "yellow")
        for i, p in enumerate(detected_ports):
            print(f"   {i+1}. {p}")
        print_color("❓ Enter number or type manually: ", "yellow", end="")
        choice = input().strip().lower()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(detected_ports):
                return detected_ports[idx]
            else:
                print_color("❌ Invalid choice", "red")
                return None
        except ValueError:
            return choice if choice else None
    else:
        port = detected_ports[0]
        print_color(f"❓ Use detected port '{port}'? (Y/n): ", "yellow", end="")
        confirm = input().strip().lower()
        if confirm == 'n':
            print_color("❓ Enter serial port manually: ", "yellow", end="")
            port = input().strip()
            return port if port else None
        return port


def find_esptool_path() -> Optional[str]:
    from .toolchain import selected_tool
    return selected_tool('esptool_py')


def build_esptool_cmd(esptool_path: str, args: list) -> list:
    """
    Build esptool command with proper invocation.
    Args:
        esptool_path: Path to esptool or esptool.py
        args: List of arguments for esptool
    Returns:
        Complete command as list
    """
    if esptool_path.endswith('.py'):
        return [sys.executable, esptool_path] + args
    else:
        return [esptool_path] + args


def find_boot_app0_path() -> Optional[str]:
    from .toolchain import selected_boot_app0
    return selected_boot_app0()


def calculate_sha256(filepath: str) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def read_partition_file(filepath: str) -> Optional[str]:
    """Read partition CSV file content."""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except Exception:
        return None


def partitions_differ(file1: str, file2: str) -> bool:
    """Check if two partition files have different content."""
    content1 = read_partition_file(file1)
    content2 = read_partition_file(file2)

    if content1 is None or content2 is None:
        return True  # Assume they differ if we can't read

    return content1.strip() != content2.strip()


def prompt_partition_conflict() -> str:
    """
    Prompt user to handle partition file conflict.

    Returns:
        'keep' - Keep existing root partitions.csv
        'overwrite' - Overwrite with locals/B4E-ESP32C6-4MB-LittleFS-OTA.csv
        'cancel' - Abort build
    """
    print_color("\n⚠️  Partition file mismatch detected!", "yellow")
    print_color("=" * 70, "yellow")
    print_color("  Root partitions.csv differs from config/arduino_board/B4E-ESP32C6-4MB-LittleFS-OTA.csv", "yellow")
    print()
    print_color("Options:", "bold")
    print_color("  1. KEEP      - Use existing root partitions.csv", "yellow")
    print_color("  2. OVERWRITE - Replace with config/arduino_board/B4E-ESP32C6-4MB-LittleFS-OTA.csv", "yellow")
    print_color("  3. CANCEL    - Abort build", "red")
    print()

    while True:
        try:
            response = input("Choose option (1-3): ").strip().lower()

            if response in ['1', 'keep']:
                return 'keep'
            elif response in ['2', 'overwrite']:
                return 'overwrite'
            elif response in ['3', 'cancel']:
                return 'cancel'
            else:
                print_color("Invalid choice. Please enter 1-3:", "red")
        except KeyboardInterrupt:
            return 'cancel'


def validate_partition_file() -> bool:
    """The project has one authoritative CSV; never replace it with a board preset."""
    from .partitions import validate_layout
    try:
        validate_layout(os.path.join(SKETCH_FOLDER, PARTITIONS_CSV))
        return True
    except (ValueError, OSError) as exc:
        print_color(f"Invalid partition table: {exc}", "red")
        return False


def parse_partition_csv() -> Optional[List[Dict[str, str]]]:
    """Parse partition CSV file and return list of partitions."""
    partition_path = os.path.join(SKETCH_FOLDER, PARTITIONS_CSV)

    if not os.path.exists(partition_path):
        return None

    try:
        partitions = []
        with open(partition_path, 'r') as f:
            reader = csv.DictReader(f, skipinitialspace=True)
            for row in reader:
                # Skip comment rows (empty or starting with #)
                if not row or all(v == '' for v in row.values()):
                    continue

                # Fix the Name field which comes with # prefix from comment header
                if '# Name' in row:
                    row['Name'] = row.pop('# Name')

                # Skip rows without Name
                if not row.get('Name', '').strip():
                    continue

                partitions.append(row)
        return partitions if partitions else None
    except Exception:
        return None


def format_hex_size(hex_str: str) -> str:
    """Convert hex string to human-readable size."""
    try:
        size_bytes = int(hex_str, 16)
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.0f} KB"
        else:
            return f"{size_bytes} bytes"
    except ValueError:
        return hex_str


def ensure_build_dir() -> str:
    """Ensure build directory exists."""
    build_dir = os.path.join(SKETCH_FOLDER, BUILD_PATH)
    os.makedirs(build_dir, exist_ok=True)
    return build_dir


def find_compiled_firmware() -> Optional[str]:
    """Find the compiled firmware binary in ./firmware directory.

    Prefers merged.bin (complete image with bootloader) over .bin (app only).
    """
    firmware_dir = FIRMWARE_DIR

    # Prefer merged.bin - complete image with bootloader, partitions, and app
    merged_bin = os.path.join(firmware_dir, f"{SKETCH_NAME}.merged.bin")
    if os.path.exists(merged_bin):
        return merged_bin

    # Fallback: app binary only
    firmware_bin = os.path.join(firmware_dir, f"{SKETCH_NAME}.bin")
    if os.path.exists(firmware_bin):
        return firmware_bin

    # Last resort: search in firmware directory
    import glob
    search_patterns = [
        os.path.join(firmware_dir, f"**", f"{SKETCH_NAME}.merged.bin"),
        os.path.join(firmware_dir, f"**", f"{SKETCH_NAME}.bin"),
    ]

    for pattern in search_patterns:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            # Return the most recently modified one
            return max(matches, key=lambda x: os.path.getmtime(x))

    return None


def copy_firmware_to_local(source_path: str) -> Optional[str]:
    """Firmware is already in ./firmware, just confirm the path."""
    # Binaries are exported to ./firmware by arduino-cli
    # Also copy to sketch root for convenience
    dest_path = os.path.join(SKETCH_FOLDER, f"{SKETCH_NAME}.bin")

    if source_path == dest_path:
        return dest_path

    try:
        shutil.copy2(source_path, dest_path)
        return dest_path
    except Exception as e:
        # Not critical if copy fails - binaries are already in ./firmware
        return source_path


def build_sketch(verbose: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Compile the sketch using arduino-cli.
    Always uses -v to capture library info for build logs.
    Uses --export-binaries and --output-dir to copy binaries to ./firmware
    Saves full output to build.log, displays on console only if --verbose
    Returns: (success: bool, build_output: str or None)
    """
    print_color("\n🏗️  Building sketch...", "bold")

    # Validate partition files before building
    if not validate_partition_file():
        return False, None

    ensure_build_dir()

    # Create firmware output directory
    firmware_dir = FIRMWARE_DIR
    os.makedirs(firmware_dir, exist_ok=True)

    # Use local libraries if available
    libraries_dir = os.path.join(SKETCH_FOLDER, "libraries")

    cmd = [
        ARDUINO_CLI_PATH,
        "compile",
        "-b", FQBN,
        "--build-property", f"upload.maximum_size={validate_layout(project_path(ROOT, BUILD_CONFIG['paths']['partitions']))['app0'][3]}",
        "--build-path", BUILD_PATH,
        "--export-binaries",
        "--output-dir", firmware_dir,
        "-v",  # Always verbose to capture libraries for build log
        "-e",
    ]

    # Add local libraries path if it exists
    if os.path.exists(libraries_dir):
        cmd.extend(["--libraries", libraries_dir])

    if verbose:
        print_color("📋 Verbose output enabled (terminal)", "yellow")

    cmd.append(SKETCH_NAME)

    print_color(f"🔨 Compiling...", "blue")

    # Build output file path
    build_log_path = os.path.join(SKETCH_FOLDER, "build.log")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        build_output = ""

        # Open build.log for writing
        with open(build_log_path, "w") as log_file:
            log_file.write(f"Build started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write(f"Command: {' '.join(cmd)}\n")
            log_file.write("=" * 80 + "\n\n")

            if process.stdout:
                for line in process.stdout:
                    build_output += line
                    log_file.write(line)
                    log_file.flush()

                    # Only print to console if verbose mode
                    if verbose:
                        print(line, end="")

            log_file.write("\n" + "=" * 80 + "\n")
            log_file.write(f"Build completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        process.wait()

        if process.returncode != 0:
            print_color(f"❌ Compilation failed (see build.log for details)", "red")
            return False, None

        print_color("✅ Compilation successful", "green")
        print_color(f"📋 Build output saved to: build.log", "blue")
        return True, build_output

    except FileNotFoundError:
        print_color(f"❌ Command not found: {cmd[0]}", "red")
        return False, None
    except Exception as e:
        print_color(f"❌ Unexpected error: {e}", "red")
        return False, None


def verify_firmware_signature(firmware_path: str) -> Tuple[bool, Optional[Dict[str, str]]]:
    """
    Check if firmware binary contains the FW_SIGNATURE_BLOCK.
    Returns: (found: bool, signature_data: dict or None)
    """
    if not os.path.exists(firmware_path):
        print_color(f"❌ Firmware file not found: {firmware_path}", "red")
        return False, None

    try:
        with open(firmware_path, "rb") as f:
            binary_content = f.read()

        # Search for signature markers
        start_marker = b"---FW_SIGNATURE_START---"
        end_marker = b"---FW_SIGNATURE_END---"

        start_idx = binary_content.find(start_marker)
        end_idx = binary_content.find(end_marker)

        if start_idx == -1 or end_idx == -1:
            # This bench does not embed SxS metadata markers.
            return False, None

        # Extract signature block
        sig_start = start_idx
        sig_end = end_idx + len(end_marker)
        signature_bytes = binary_content[sig_start:sig_end]

        # Decode and parse
        try:
            signature_text = signature_bytes.decode('utf-8', errors='ignore')
        except:
            signature_text = signature_bytes.decode('latin-1', errors='ignore')

        # Parse fields
        sig_data = {}
        lines = signature_text.split('\n')
        for line in lines:
            line = line.strip()
            if '=' in line:
                key, value = line.split('=', 1)
                sig_data[key] = value

        # Verify required fields
        required = ['FW_VERSION', 'FW_DATE', 'FW_BOARD', 'FW_AUTHOR']
        missing = [k for k in required if k not in sig_data]

        if missing:
            print_color(f"⚠️  Signature incomplete. Missing: {', '.join(missing)}", "yellow")
            return False, sig_data

        print_color("✅ FW_SIGNATURE_BLOCK verified in binary", "green")
        return True, sig_data

    except Exception as e:
        print_color(f"❌ Error verifying signature: {e}", "red")
        return False, None


def extract_build_info(build_output: str) -> Dict[str, any]:
    """Extract memory usage, libraries, and platform info from build output."""
    # Remove ANSI color codes for easier parsing
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_output = ansi_escape.sub('', build_output)

    info = {
        "sketch_size": None,
        "max_sketch_size": None,
        "global_vars": None,
        "max_global_vars": None,
        "local_vars_available": None,
        "libraries": [],
        "platform": None,
    }

    # Extract sketch memory usage
    sketch_match = re.search(r"(\d+)\s+octets?\s*\((\d+)%\)\s+de l'espace", clean_output)
    if sketch_match:
        info["sketch_size"] = int(sketch_match.group(1))
        info["sketch_percent"] = int(sketch_match.group(2))

    max_sketch_match = re.search(r"maximum est de (\d+)\s+octets", clean_output)
    if max_sketch_match:
        info["max_sketch_size"] = int(max_sketch_match.group(1))

    # Extract global variables
    global_match = re.search(r"Les variables globales utilisent (\d+)\s+octets?\s*\((\d+)%\)", clean_output)
    if global_match:
        info["global_vars"] = int(global_match.group(1))
        info["global_percent"] = int(global_match.group(2))

    local_match = re.search(r"laisse (\d+)\s+octets?\s+pour les variables locales", clean_output)
    if local_match:
        info["local_vars_available"] = int(local_match.group(1))

    max_global_match = re.search(r"maximum est de (\d+)\s+octets?\s*$", clean_output, re.MULTILINE)
    if max_global_match:
        info["max_global_vars"] = int(max_global_match.group(1))

    # Arduino CLI reports in English on this bench (retain French support above).
    english = re.search(r"Sketch uses (\d+) bytes \((\d+)%\).*Maximum is (\d+) bytes", clean_output)
    if english:
        info["sketch_size"], info["sketch_percent"], info["max_sketch_size"] = map(int, english.groups())
    english_ram = re.search(r"Global variables use (\d+) bytes \((\d+)%\).*leaving (\d+) bytes.*Maximum is (\d+) bytes", clean_output)
    if english_ram:
        info["global_vars"], info["global_percent"], info["local_vars_available"], info["max_global_vars"] = map(int, english_ram.groups())

    # Extract libraries
    lib_section = re.search(r"Used library\s+(.*?)(?:Used platform|$)", clean_output, re.DOTALL)
    if lib_section:
        lib_lines = lib_section.group(1).strip().split('\n')
        for line in lib_lines:
            line = line.strip()
            if line and not line.startswith('Version'):
                # Parse: LibraryName  Version  Path
                # Format: "LibraryName <spaces> Version <spaces> Path"
                # Version is typically X.Y.Z format, match it specifically
                match = re.match(r'(.+?)\s+(\d+(?:\.\d+){1,3})\s+(.+)$', line)
                if match:
                    info["libraries"].append({
                        "name": match.group(1).strip(),
                        "version": match.group(2),
                        "path": match.group(3),
                    })

    # Extract platform
    platform_match = re.search(r"Used platform\s+Version\s+Path\s+(\S+)\s+(\S+)\s+(.+?)$", clean_output, re.MULTILINE)
    if platform_match:
        info["platform"] = {
            "name": platform_match.group(1).strip(),
            "version": platform_match.group(2),
            "path": platform_match.group(3).strip(),
        }

    return info


def get_partition_size(partition_name: str = "app0") -> Optional[int]:
    """
    Read the actual app partition size from partitions.csv.
    Returns the size in bytes, or None if not found.
    """
    partitions_file = os.path.join(SKETCH_FOLDER, "partitions.csv")
    if not os.path.exists(partitions_file):
        return None

    try:
        with open(partitions_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 5 and parts[0] == partition_name:
                    # Size is in the 5th column, in hex format
                    size_str = parts[4]
                    return int(size_str, 16)
    except Exception as e:
        print_color(f"⚠️  Could not read partition size: {e}", "yellow")

    return None


def extract_includes_from_sketch() -> List[str]:
    """Extract all #include statements from the sketch file (user libraries only)."""
    # Standard system includes to ignore
    SYSTEM_INCLUDES = {
        'arduino.h', 'arduino_config.h',  # Arduino core
        'wire.h', 'spi.h', 'serial.h',    # Common interfaces
        'rom/', 'esp_', 'freertos/',      # ESP32 system
        'mbedtls/', 'certs/', 'openssl/', # Security/crypto
        'sys/', 'errno.h', 'stdint.h',    # Standard C
        'arpa/', 'netinet/',              # Network
    }

    # Exact names: do not hide a third-party header containing e.g. "atomic".
    cpp_headers = set("algorithm any array atomic bitset chrono codecvt complex condition_variable deque exception execution filesystem forward_list fstream functional future initializer_list iomanip ios iosfwd iostream istream iterator limits list locale map memory memory_resource mutex new numeric optional ostream queue random ratio regex scoped_allocator set shared_mutex sstream stack stdexcept streambuf string string_view strstream system_error thread tuple type_traits typeindex typeinfo unordered_map unordered_set utility valarray variant vector cassert cctype cerrno cfenv cfloat cinttypes ciso646 climits clocale cmath csetjmp csignal cstdarg cstddef cstdint cstdio cstdlib cstring ctgmath ctime cuchar cwchar cwctype".split())
    includes = []
    try:
        sketch_path = os.path.join(SKETCH_FOLDER, SKETCH_NAME)
        with open(sketch_path, 'r') as f:
            content = f.read()

        # Match both #include <lib.h> and #include "lib.h"
        matches = re.findall(r'#include\s+[<"]([^>"]+)[>"]', content)

        # Filter out system includes and project-local headers
        for match in matches:
            if match in cpp_headers or os.path.isfile(os.path.join(SKETCH_FOLDER, match)):
                continue
            include_lower = match.lower()
            is_system = False

            # Skip project-local headers (src/*, lib/*, libraries/*, etc.)
            if match.startswith(("src/", "lib/", "libraries/", "../")):
                continue

            for system_pattern in SYSTEM_INCLUDES:
                if system_pattern in include_lower or include_lower.startswith(system_pattern.rstrip('/')):
                    is_system = True
                    break

            if not is_system:
                includes.append(match)

    except Exception as e:
        print_color(f"⚠️  Could not extract includes from sketch: {e}", "yellow")

    return includes


def get_incomplete_libraries() -> Dict[str, str]:
    """
    Check libraries folder for incomplete/empty libraries.
    Returns dict of {library_name: reason}
    """
    incomplete = {}
    libraries_dir = os.path.join(SKETCH_FOLDER, "libraries")

    if not os.path.exists(libraries_dir):
        return incomplete

    try:
        for lib_folder in os.listdir(libraries_dir):
            lib_path = os.path.join(libraries_dir, lib_folder)

            if not os.path.isdir(lib_path):
                continue

            # Check if src folder exists and has content
            src_path = os.path.join(lib_path, "src")
            if os.path.exists(src_path):
                src_files = [f for f in os.listdir(src_path) if f.endswith(('.h', '.cpp', '.c'))]
                if not src_files:
                    incomplete[lib_folder] = "src/ folder is empty"
            else:
                # Check for direct .h/.cpp files in root
                root_files = [f for f in os.listdir(lib_path) if f.endswith(('.h', '.cpp', '.c'))]
                if not root_files:
                    incomplete[lib_folder] = "No source files found (empty repository?)"
    except Exception as e:
        print_color(f"⚠️  Error checking libraries: {e}", "yellow")

    return incomplete


def normalize_name(name: str) -> str:
    """Normalize library names for matching (remove spaces, underscores, convert to lowercase)."""
    return re.sub(r'[_\s\-]+', '', name).lower()


def validate_libraries(build_info: Dict) -> Dict[str, list]:
    """
    Validate that all included libraries are actually compiled.

    Returns:
        Dict with 'missing', 'incomplete' keys
    """
    validation = {
        "missing": [],      # #included but not compiled
        "incomplete": []    # Folder exists but no source files
    }

    # Get all #include statements (system includes already filtered)
    includes = extract_includes_from_sketch()
    if not includes:
        return validation

    # Get compiled libraries - create mapping by normalized name
    compiled_libs = {}
    for lib in build_info.get("libraries", []):
        normalized = normalize_name(lib["name"])
        compiled_libs[normalized] = lib

    # Get incomplete libraries in /libraries folder
    incomplete_libs = get_incomplete_libraries()

    for include_file in includes:
        # Extract just the base name (remove .h, handle path separators)
        include_base = os.path.basename(include_file).replace('.h', '')
        normalized_include = normalize_name(include_base)

        # Try to find the library
        found_compiled = False
        found_incomplete = False

        # Check compiled libraries using normalized matching
        if normalized_include in compiled_libs:
            found_compiled = True

        # If not found by name, check if header exists in any compiled library's src folder
        if not found_compiled:
            for lib in build_info.get("libraries", []):
                lib_path = lib.get("path", "")
                # Check both /src and root of library
                for subdir in ["/src", ""]:
                    header_path = os.path.join(lib_path + subdir, include_file)
                    if os.path.exists(header_path):
                        found_compiled = True
                        break
                if found_compiled:
                    break

        # Check incomplete libraries using normalized matching
        for incomplete_name in incomplete_libs.keys():
            if normalized_include == normalize_name(incomplete_name):
                found_incomplete = True
                validation["incomplete"].append({
                    "include": include_file,
                    "library": incomplete_name,
                    "reason": incomplete_libs[incomplete_name]
                })
                break

        # If not found in compiled or incomplete, it's missing
        if not found_compiled and not found_incomplete:
            # Only report as missing if it looks like a user library
            # (not a single-word core library)
            if len(include_base) > 1:  # Skip very short includes
                validation["missing"].append(include_file)

    return validation


def generate_build_log(build_output: str, firmware_path: str = None) -> str:
    """Generate a beautiful build log with firmware info and build details."""

    # Extract build info
    build_info = extract_build_info(build_output)

    # Get file info and verify signature
    file_size = None
    file_hash = None
    sig_valid = False
    sig_data = None
    if firmware_path and os.path.exists(firmware_path):
        file_size = os.path.getsize(firmware_path)
        file_hash = calculate_sha256(firmware_path)
        sig_valid, sig_data = verify_firmware_signature(firmware_path)

    # Use signature data from compiled binary if available, otherwise fallback to source
    if sig_data:
        fw_version = sig_data.get("FW_VERSION", "unknown")
        fw_board = sig_data.get("FW_BOARD", "unknown")
        fw_author = sig_data.get("FW_AUTHOR", "unknown")

        # FW_DATE in signature contains both date and time (e.g., "Nov 13 2025 16:54:06")
        # Split into date and time parts
        fw_date_combined = sig_data.get("FW_DATE", "unknown")
        if fw_date_combined != "unknown":
            # Split at the last space to separate date from time
            parts = fw_date_combined.rsplit(" ", 1)
            if len(parts) == 2:
                fw_date = parts[0]  # "Nov 13 2025"
                fw_time = parts[1]  # "16:54:06"
            else:
                fw_date = fw_date_combined
                fw_time = "unknown"
        else:
            fw_date = "unknown"
            fw_time = "unknown"
    else:
        # Fallback to source file values
        fw_version = FW_VERSION
        fw_date = FW_DATE
        fw_time = FW_TIME
        fw_board = FW_BOARD
        fw_author = FW_AUTHOR

    # Build log content
    log = []
    log.append("=" * 80)
    log.append("ESP32 FIRMWARE BUILD LOG")
    log.append("=" * 80)
    log.append("")

    # Timestamp
    log.append(f"Build Date:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.append("")

    # Firmware Info
    log.append("FIRMWARE INFORMATION")
    log.append("-" * 80)
    log.append(f"Version:           {fw_version}")
    log.append(f"Board:             {fw_board}")
    log.append(f"Compiled:          {fw_date} at {fw_time}")
    log.append(f"Author:            {fw_author}")
    log.append("")

    # Binary Info
    if file_size:
        log.append("BINARY FILE INFORMATION")
        log.append("-" * 80)
        log.append(f"File:              {os.path.basename(firmware_path)}")
        log.append(f"Size:              {file_size:,} bytes ({file_size/1024:.2f} kB)")
        if file_hash:
            log.append(f"SHA256:            {file_hash}")

        # Signature verification
        if sig_valid:
            log.append(f"Signature Block:   ✅ PRESENT & VALID")
        elif sig_data:
            log.append(f"Signature Block:   ⚠️  INCOMPLETE (missing fields)")
        else:
            log.append(f"Signature Block:   ❌ NOT FOUND")

        log.append("")

    # Memory Usage
    log.append("MEMORY USAGE")
    log.append("-" * 80)
    if build_info["sketch_size"]:
        # Use actual partition size from partitions.csv if available
        actual_partition_size = get_partition_size("app0")
        if actual_partition_size:
            max_size = actual_partition_size
            used_pct = int((build_info['sketch_size'] / max_size) * 100)
        else:
            max_size = build_info['max_sketch_size']
            used_pct = build_info.get("sketch_percent", 0)
        log.append(f"Program Storage:   {build_info['sketch_size']:,} / {max_size:,} bytes ({used_pct}%)")
    if build_info["global_vars"]:
        global_pct = build_info.get("global_percent", 0)
        max_global = build_info.get("max_global_vars") or 0
        if max_global > 0:
            log.append(f"Global Variables:  {build_info['global_vars']:,} / {max_global:,} bytes ({global_pct}%)")
        else:
            log.append(f"Global Variables:  {build_info['global_vars']:,} bytes ({global_pct}%)")
        if build_info["local_vars_available"]:
            log.append(f"Local Variables:   {build_info['local_vars_available']:,} bytes available")
    log.append("")

    # Partition Table
    partitions = parse_partition_csv()
    if partitions:
        log.append("PARTITION TABLE")
        log.append("-" * 80)
        # Header
        log.append(f"{'Name':<14} {'Type':<8} {'SubType':<12} {'Offset':<20} {'Size':<20}")
        log.append("-" * 80)
        # Partitions
        for part in partitions:
            name = part.get('Name', '').strip()
            ptype = part.get('Type', '').strip()
            subtype = part.get('SubType', '').strip()
            offset = part.get('Offset', '').strip()
            size = part.get('Size', '').strip()

            # Format offset and size for display
            offset_display = f"{offset} ({format_hex_size(offset)})"
            size_display = f"{size} ({format_hex_size(size)})"

            log.append(f"{name:<14} {ptype:<8} {subtype:<12} {offset_display:<20} {size_display:<20}")

        log.append("-" * 80)
        # Calculate total
        try:
            total_bytes = 0
            for part in partitions:
                size_hex = part.get('Size', '0x0').strip()
                total_bytes += int(size_hex, 16)
            log.append(f"Total Flash:       {total_bytes:,} bytes ({format_hex_size(hex(total_bytes))})")
        except Exception:
            pass
        log.append("")

    # Libraries - Organized by source
    if build_info["libraries"]:
        log.append("USED LIBRARIES")
        log.append("-" * 80)

        # Separate libraries by source
        arduino_libs = []
        external_libs = []

        for lib in build_info["libraries"]:
            lib_path = lib['path']
            # Check if library is from Arduino core/packages
            if 'Arduino15/packages' in lib_path or 'arduino15/packages' in lib_path:
                arduino_libs.append(lib)
            else:
                external_libs.append(lib)

        # Sort both lists by name
        arduino_libs.sort(key=lambda x: x['name'].lower())
        external_libs.sort(key=lambda x: x['name'].lower())

        # Display Arduino libraries first
        if arduino_libs:
            log.append("📦 FROM Arduino Installation:")
            for lib in arduino_libs:
                log.append(f"  • {lib['name']:<35} v{lib['version']:<8} {lib['path']}")

        # Display external libraries
        if external_libs:
            if arduino_libs:
                log.append("")
            log.append("📚 FROM External Libraries:")
            for lib in external_libs:
                log.append(f"  • {lib['name']:<35} v{lib['version']:<8} {lib['path']}")

        log.append("")

    # Library Validation
    lib_validation = validate_libraries(build_info)
    if lib_validation["incomplete"] or lib_validation["missing"]:
        log.append("LIBRARY VALIDATION")
        log.append("-" * 80)

        if lib_validation["incomplete"]:
            log.append("⚠️  INCOMPLETE LIBRARIES (folder exists but no source files):")
            for item in lib_validation["incomplete"]:
                log.append(f"  ❌ {item['include']}")
                log.append(f"     Library: {item['library']}")
                log.append(f"     Issue: {item['reason']}")
            log.append("")

        if lib_validation["missing"]:
            log.append("⚠️  MISSING LIBRARIES (#include found but library not compiled):")
            for include in lib_validation["missing"]:
                log.append(f"  ❌ {include}")
            log.append("")

        log.append("💡 FIX: Run 'python3 build.py --sync-libraries' to download missing libraries")
        log.append("")
    elif extract_includes_from_sketch():
        # All includes are valid
        log.append("LIBRARY VALIDATION")
        log.append("-" * 80)
        log.append("✅ All #include libraries are valid and properly compiled")
        log.append("")

    # Platform
    if build_info["platform"]:
        log.append("PLATFORM")
        log.append("-" * 80)
        log.append(f"  • {build_info['platform']['name']:<35} v{build_info['platform']['version']}")
        log.append(f"    {build_info['platform']['path']}")
        log.append("")

    # Firmware Signature Details
    if sig_data:
        log.append("FIRMWARE SIGNATURE DETAILS")
        log.append("-" * 80)
        for key, value in sig_data.items():
            if key in ['FW_VERSION', 'FW_DATE', 'FW_BOARD', 'FW_AUTHOR']:
                log.append(f"  {key:<20} {value}")
        log.append("")

    log.append("=" * 80)
    log.append("END OF BUILD LOG")
    log.append("=" * 80)

    return "\n".join(log)


def save_build_log(log_content: str, filename: str = None) -> str:
    """Save build log to /info folder and return the path."""
    if filename is None:
        filename = "build_log.txt"

    # Create /info directory if it doesn't exist
    info_dir = os.path.join(SKETCH_FOLDER, "info")
    os.makedirs(info_dir, exist_ok=True)

    # Save to /info folder
    log_path = os.path.join(info_dir, filename)

    try:
        with open(log_path, "w") as f:
            f.write(log_content)
        print_color(f"✅ Build log saved: {log_path}", "green")
        return log_path
    except Exception as e:
        print_color(f"❌ Failed to save build log: {e}", "red")
        return None


def flash_budget(app_size: int, slot_size: int) -> Dict[str, int]:
    """App binary size against the app0 OTA slot."""
    return {'app': app_size, 'slot': slot_size,
            'percent': app_size * 100 // slot_size, 'remaining': slot_size - app_size}


def report_flash_budget(app_path: str) -> Dict[str, int]:
    """Print the remaining OTA slot margin after every build; warn when nearly full."""
    slot = validate_layout(PARTITIONS_CSV)['app0'][3]
    b = flash_budget(os.path.getsize(app_path), slot)
    color = 'red' if b['percent'] >= 95 else 'yellow' if b['percent'] >= 90 else 'green'
    print_color(f"📐 Flash app0: {b['app']:,} / {b['slot']:,} bytes ({b['percent']}%) — {b['remaining']:,} bytes free", color)
    if b['percent'] >= 90:
        print_color("⚠️  OTA slot nearly full: plan size reduction or a larger flash before adding features", "yellow")
    return b


def read_device_macs(esptool: str, port: str) -> set:
    """MAC/EUI-64 strings reported by the device, lowercase."""
    cmd = build_esptool_cmd(esptool, ["--chip", BUILD_CONFIG["chip"], "-p", port, "read-mac"])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise ValueError("read-mac failed: " + (r.stderr or r.stdout).strip()[:200])
    return set(re.findall(r"(?i)\b((?:[0-9a-f]{2}:){5,7}[0-9a-f]{2})\b", r.stdout.lower()))


def check_expected_mac(esptool: str, port: str, expect_mac: Optional[str]) -> bool:
    """Refuse to touch a device whose MAC does not match --expect-mac."""
    if expect_mac is None:
        return True
    macs = read_device_macs(esptool, port)
    print_color(f"  🪪 Device MAC: {', '.join(sorted(macs)) or 'unknown'}", "blue")
    if expect_mac.strip().lower() in macs:
        return True
    print_color(f"❌ Device MAC does not match --expect-mac {expect_mac}; nothing written", "red")
    return False


def flash_firmware(port: str, firmware_path: str, erase_mode: str = "none", expect_mac: Optional[str] = None) -> bool:
    """
    Flash firmware using esptool with Arduino-compatible multi-file pattern.

    Flashes individual components at their correct addresses:
      - 0x0:     bootloader.bin
      - 0x8000:  partitions.bin
      - 0xe000:  boot_app0.bin
      - 0x10000: app.bin

    Args:
        port: Serial port
        firmware_path: Path to firmware (can be .bin or .merged.bin)
        erase_mode: "none", "all", or "keep_nvs_littlefs"
    """
    print_color(f"\n📝 Flashing firmware to {port}...", "bold")

    esptool = find_esptool_path()
    if not esptool:
        return False

    # Find the firmware directory (contains all binaries)
    firmware_dir = os.path.dirname(firmware_path)
    if not firmware_dir:
        firmware_dir = FIRMWARE_DIR

    # Find individual component files
    bootloader_bin = os.path.join(firmware_dir, f"{SKETCH_NAME}.bootloader.bin")
    partitions_bin = os.path.join(firmware_dir, f"{SKETCH_NAME}.partitions.bin")
    app_bin = os.path.join(firmware_dir, f"{SKETCH_NAME}.bin")

    boot_app0_bin = find_boot_app0_path()

    # Verify all required files exist
    missing_files = []
    if not os.path.exists(bootloader_bin):
        missing_files.append("bootloader.bin")
    if not os.path.exists(partitions_bin):
        missing_files.append("partitions.bin")
    if not boot_app0_bin:
        missing_files.append("boot_app0.bin (from Arduino)")
    if not os.path.exists(app_bin):
        missing_files.append("app.bin")

    if missing_files:
        print_color(f"❌ Missing required files: {', '.join(missing_files)}", "red")
        return False

    # B4E: reject stale/oversized binaries and check actual flash before writes.
    from .partitions import validate_layout, check_table_matches, validate_device
    try:
        layout = validate_layout(PARTITIONS_CSV)
        check_table_matches(PARTITIONS_CSV, Path(partitions_bin).read_bytes())
        if not 0 < os.path.getsize(bootloader_bin) <= 0x8000 - int(BUILD_CONFIG['bootloader_offset'], 0):
            raise ValueError("Bootloader exceeds reserved boot region")
        if not 0 < os.path.getsize(partitions_bin) <= 0x1000:
            raise ValueError("Partition table exceeds reserved region")
        if layout.get('otadata', ())[:2] != ('data', 'ota') or not 0 < os.path.getsize(boot_app0_bin) <= layout['otadata'][3]:
            raise ValueError("OTA boot metadata exceeds/mismatches otadata partition")
        if not 0 < os.path.getsize(app_bin) <= layout["app0"][3]:
            raise ValueError("Application exceeds OTA partition")
        if not check_expected_mac(esptool, port, expect_mac):
            return False
        # Reading the device table before writing refuses a board laid out for another
        # project; a full erase is the explicit migration path. A blank chip passes.
        validate_device(build_esptool_cmd(esptool, []), port, PARTITIONS_CSV, BUILD_PATH,
                        check_partition=erase_mode != "all")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print_color(f"Flash rejected: {exc}", "red")
        return False

    # Build erase command flag
    erase_flag = []
    if erase_mode == "all":
        erase_flag = ["--erase-all"]
        print_color("  🗑️  Erasing entire flash...", "yellow")
    elif erase_mode == "keep_nvs_littlefs":
        print_color("  ⏭️  Keeping NVS and LittleFS (app partitions only)...", "yellow")

    # Build esptool command (matches Arduino IDE pattern)
    cmd_args = [
        "--chip", BUILD_CONFIG["chip"],
        "-p", port,
        "-b", BAUD_RATE,
        "write-flash"
    ] + erase_flag + [
        "-z",
        "--flash-mode", "keep",
        "--flash-freq", "keep",
        "--flash-size", "keep",
        BUILD_CONFIG["bootloader_offset"], bootloader_bin,
        "0x8000", partitions_bin,
        hex(layout["otadata"][2]), boot_app0_bin,
        hex(layout["app0"][2]), app_bin
    ]

    cmd = build_esptool_cmd(esptool, cmd_args)

    print_color(f"  📍 {BUILD_CONFIG['bootloader_offset']}: {os.path.basename(bootloader_bin)}", "blue")
    print_color(f"  📍 0x8000:  {os.path.basename(partitions_bin)}", "blue")
    print_color(f"  📍 {hex(layout['otadata'][2])}: boot_app0.bin", "blue")
    print_color(f"  📍 {hex(layout['app0'][2])}: {os.path.basename(app_bin)}", "blue")

    return run_command(cmd)


def find_mklittlefs_path() -> Optional[str]:
    from .toolchain import selected_tool
    return selected_tool('mklittlefs')


def build_littlefs_image(output_path: str = "littlefs.bin") -> bool:
    """
    Build LittleFS image from /data directory.

    Args:
        output_path: Output file path for littlefs.bin

    Returns:
        True if successful, False otherwise
    """
    print_color(f"\n🧱 Building LittleFS image from /data directory...", "bold")
    if os.path.exists(output_path):
        os.remove(output_path)

    # Ensure firmware directory exists
    os.makedirs(FIRMWARE_DIR, exist_ok=True)

    # Check if /data directory exists
    data_dir = os.path.join(SKETCH_FOLDER, "data")
    if not os.path.isdir(data_dir):
        print_color(f"❌ Data directory not found: {data_dir}", "red")
        return False

    # Find mklittlefs
    mklittlefs = find_mklittlefs_path()
    if not mklittlefs:
        return False

    # Get partitions to determine LittleFS size
    partitions = get_partitions()
    if not partitions or "littlefs" not in partitions:
        print_color("❌ littlefs partition not found in partitions.csv", "red")
        return False

    # Convert hex size to integer for mklittlefs
    size_hex = partitions["littlefs"]["size"]
    try:
        size_int = int(size_hex, 16)
    except ValueError:
        print_color(f"❌ Invalid size in partitions.csv: {size_hex}", "red")
        return False

    print_color(f"📁 Data directory: {data_dir}", "blue")
    print_color(f"📊 LittleFS size: {size_hex} ({size_int:,} bytes)", "blue")

    # Build the command
    cmd = [
        mklittlefs,
        "-c", data_dir,
        "-p", "256",          # page size
        "-b", "4096",         # block size
        "-s", str(size_int),  # total size
        output_path
    ]

    print_color(f"▶️  Running: {' '.join(cmd)}", "blue")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            print_color(f"❌ mklittlefs failed:", "red")
            if result.stderr:
                print_color(f"   {result.stderr}", "red")
            return False

        # Check if output file was created
        if not os.path.exists(output_path):
            print_color(f"❌ LittleFS image file not created: {output_path}", "red")
            return False

        # Get file size
        file_size = os.path.getsize(output_path)
        print_color(f"✅ LittleFS image created: {output_path}", "green")
        print_color(f"   Size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)", "green")

        return True

    except subprocess.TimeoutExpired:
        print_color(f"❌ mklittlefs timed out (> 120s)", "red")
        return False
    except Exception as e:
        print_color(f"❌ Error building LittleFS image: {e}", "red")
        return False


def flash_littlefs(port: str, littlefs_path: str, expect_mac: Optional[str] = None) -> bool:
    """Flash LittleFS partition."""
    print_color(f"\n📦 Flashing LittleFS to {port}...", "bold")

    esptool = find_esptool_path()
    if not esptool:
        return False

    partitions = get_partitions()
    if not partitions or "littlefs" not in partitions:
        print_color("❌ littlefs partition not found in partitions.csv", "red")
        return False

    from .partitions import validate_device, validate_layout
    try:
        layout = validate_layout(PARTITIONS_CSV)
        if os.path.getsize(littlefs_path) != layout["littlefs"][3]:
            raise ValueError("LittleFS image size differs from partition")
        if not check_expected_mac(esptool, port, expect_mac):
            return False
        validate_device(build_esptool_cmd(esptool, []), port, PARTITIONS_CSV,
                        BUILD_PATH, check_partition=True)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print_color(f"LittleFS flash rejected: {exc}", "red")
        return False
    offset = partitions["littlefs"]["offset"]

    cmd = build_esptool_cmd(esptool, [
        "-p", port,
        "-b", BAUD_RATE,
        "write-flash",
        offset, littlefs_path
    ])

    return run_command(cmd)


def erase_flash(port: str) -> bool:
    """Erase entire flash."""
    print_color(f"\n🗑️  Erasing flash on {port}...", "bold")

    esptool = find_esptool_path()
    if not esptool:
        return False

    cmd = build_esptool_cmd(esptool, [
        "-p", port,
        "erase-flash"
    ])

    return run_command(cmd)


# ============================================================================
# MAIN
# ============================================================================

def interactive_auto_mode(verbose: bool = False):
    """Interactive mode with prompts for each action."""
    print_color("\n--- Interactive Auto Mode ---", "bold")

    # Ask about compilation
    print_color("❓ Compile the sketch? (Y/n): ", "yellow", end="")
    compile_choice = input().strip().lower()
    do_compile = compile_choice != 'n'

    # Ask about verbose mode if compiling
    verbose_mode = verbose
    if do_compile and not verbose:
        print_color("❓ Enable verbose build output? (y/N): ", "yellow", end="")
        verbose_choice = input().strip().lower()
        verbose_mode = verbose_choice == 'y'

    # Ask about upload
    print_color("❓ Upload the firmware? (Y/n): ", "yellow", end="")
    upload_choice = input().strip().lower()
    do_upload = upload_choice != 'n'

    # Ask about erase mode
    print_color("❓ Erase mode:", "yellow")
    print("   1. None (default)")
    print("   2. All Flash Contents")
    print("   3. Keep NVS & FS (App only)")
    print_color("Enter choice (1, 2, 3): ", "yellow", end="")
    erase_choice = input().strip()

    erase_mode = "none"
    if erase_choice == "2":
        erase_mode = "all"
    elif erase_choice == "3":
        erase_mode = "app"

    # Ask about verification
    print_color("❓ Verify flash after upload? (y/N): ", "yellow", end="")
    verify_choice = input().strip().lower()
    do_verify = verify_choice == 'y'

    # Get serial port
    port = None
    if do_upload:
        port = get_port_with_confirmation()
        if not port:
            print_color("❌ No serial port specified", "red")
            sys.exit(1)

    print_color("\n--- Executing Actions ---", "bold")

    # Compile
    if do_compile:
        print_color("\n--- 🏗️  Compiling Sketch ---", "bold")
        success, build_output = build_sketch(verbose=verbose_mode)
        if not success:
            sys.exit(1)

        # Find firmware in ./firmware directory
        firmware_file = find_compiled_firmware()
        if not firmware_file:
            print_color(f"⚠️  Could not locate compiled firmware binary", "yellow")
        else:
            # Keep firmware only in ./firmware/ directory (no copy to root)
            # firmware_file = copy_firmware_to_local(firmware_file)
            pass
            if firmware_file:
                app_bin = os.path.join(os.path.dirname(firmware_file), f"{SKETCH_NAME}.bin")
                if os.path.exists(app_bin):
                    report_flash_budget(app_bin)
                # Generate and save build log
                log_content = generate_build_log(build_output or "", firmware_file)
                save_build_log(log_content, filename=args.log)

    # Upload
    if do_upload:
        print_color("\n--- 📤 Uploading Firmware ---", "bold")

        # Find firmware file
        firmware_file = f"{BUILD_PATH}/esp32.esp32.{FQBN.split(':')[-1]}/{SKETCH_NAME}.bin"
        if not os.path.exists(firmware_file):
            print_color(f"❌ Error: Binary file not found: {firmware_file}", "red")
            print_color(f"   Have you compiled the sketch first? (use --compile)", "yellow")
            sys.exit(1)

        # Handle erase modes
        esptool = find_esptool_path()
        if not esptool:
            sys.exit(1)

        if erase_mode == "all":
            print_color("\n🗑️  Erasing all flash...", "yellow")
            erase_cmd = build_esptool_cmd(esptool, [
                "-p", port,
                "-b", BAUD_RATE,
                "erase-flash"
            ])
            if not run_command(erase_cmd):
                sys.exit(1)
        elif erase_mode == "app":
            print_color("\n🗑️  Erasing app partition...", "yellow")
            partitions = get_partitions()
            if partitions and "app0" in partitions:
                app0_offset = partitions["app0"]["offset"]
                app0_size = partitions["app0"]["size"]
                erase_cmd = build_esptool_cmd(esptool, [
                    "-p", port,
                    "-b", BAUD_RATE,
                    "erase-region",
                    app0_offset,
                    app0_size
                ])
                if not run_command(erase_cmd):
                    sys.exit(1)

        # Flash firmware
        print_color(f"\nSHA256: {calculate_sha256(firmware_file)}", "yellow")
        if not flash_firmware(port, firmware_file, erase_mode=erase_mode):
            sys.exit(1)

        # Verify if requested
        if do_verify:
            print_color("\n✅ Verifying flash...", "yellow")
            # Simple verification: just read back the first 512 bytes and check
            verify_cmd = build_esptool_cmd(esptool, [
                "-p", port,
                "read-flash",
                "0x0", "512", os.path.join(BUILD_PATH, "verify.bin")
            ])
            if run_command(verify_cmd):
                print_color("✅ Flash verified successfully", "green")
            else:
                print_color("⚠️  Verification failed", "yellow")

    print_color("\n" + "="*60, "bold")
    print_color("✅ Operation completed", "green")
    print_color("="*60 + "\n", "bold")


def verify_flash_against_binary(port: str, firmware_path: str, offset: str = "0x0") -> bool:
    """
    Read firmware back from ESP32 and compare with local binary.
    Returns: True if verified, False otherwise
    """
    if not os.path.exists(firmware_path):
        print_color(f"❌ Firmware file not found: {firmware_path}", "red")
        return False

    esptool = find_esptool_path()
    if not esptool:
        return False

    file_size = os.path.getsize(firmware_path)
    temp_read_file = os.path.join(BUILD_PATH, "esp32_flash_readback.bin")

    print_color(f"\n🔍 Verifying flash against binary ({file_size} bytes)...", "bold")

    # Read back from ESP32
    print_color(f"   Reading {file_size} bytes from ESP32 at offset {offset}...", "yellow")
    read_cmd = build_esptool_cmd(esptool, [
        "-p", port,
        "-b", BAUD_RATE,
        "read-flash",
        offset,
        str(file_size),
        temp_read_file
    ])

    if not run_command(read_cmd):
        print_color("❌ Failed to read flash from ESP32", "red")
        return False

    # Compare files
    print_color(f"   Comparing files...", "yellow")
    try:
        with open(firmware_path, "rb") as f:
            local_data = f.read()

        with open(temp_read_file, "rb") as f:
            flash_data = f.read()

        if len(local_data) != len(flash_data):
            print_color(f"❌ Size mismatch: local {len(local_data)} bytes vs flash {len(flash_data)} bytes", "red")
            return False

        # Compare byte by byte
        mismatches = 0
        for i, (local_byte, flash_byte) in enumerate(zip(local_data, flash_data)):
            if local_byte != flash_byte:
                mismatches += 1
                if mismatches <= 10:  # Show first 10 mismatches
                    print_color(f"      Mismatch at offset 0x{i:x}: local=0x{local_byte:02x} flash=0x{flash_byte:02x}", "yellow")

        if mismatches > 0:
            print_color(f"❌ Verification failed: {mismatches} byte(s) differ", "red")
            return False

        # Calculate hashes
        local_hash = calculate_sha256(firmware_path)
        flash_hash = hashlib.sha256(flash_data).hexdigest()

        if local_hash == flash_hash:
            print_color(f"✅ Flash verified successfully (SHA256: {local_hash[:16]}...)", "green")
            return True
        else:
            print_color(f"❌ Hash mismatch: local {local_hash} vs flash {flash_hash}", "red")
            return False

    except Exception as e:
        print_color(f"❌ Error during verification: {e}", "red")
        return False
    finally:
        # Clean up temp file
        if os.path.exists(temp_read_file):
            try:
                os.remove(temp_read_file)
            except:
                pass


def verify_flashed_components(port: str, firmware_path: str) -> bool:
    """Read back each flashed component at its own offset.

    A merged.bin covers the whole flash including NVS/LittleFS/Zigbee regions the
    device legitimately rewrites, so verifying it always fails on a used board.
    otadata (boot_app0.bin) is skipped for the same reason: the app owns it.
    """
    firmware_dir = os.path.dirname(firmware_path) or FIRMWARE_DIR
    from .partitions import validate_layout
    layout = validate_layout(PARTITIONS_CSV)
    components = [
        (os.path.join(firmware_dir, f"{SKETCH_NAME}.bootloader.bin"), BUILD_CONFIG["bootloader_offset"]),
        (os.path.join(firmware_dir, f"{SKETCH_NAME}.partitions.bin"), "0x8000"),
        (os.path.join(firmware_dir, f"{SKETCH_NAME}.bin"), hex(layout["app0"][2])),
    ]
    for path, offset in components:
        if not verify_flash_against_binary(port, path, offset):
            return False
    return True


def erase_regions(port: str, erase_mode: str) -> bool:
    """Erase flash regions based on erase_mode."""
    if erase_mode == "none":
        print_color("⏭️  Skipping erase (will write only necessary regions)", "yellow")
        return True

    esptool = find_esptool_path()
    if not esptool:
        return False

    partitions = get_partitions()
    if not partitions:
        return False

    if erase_mode == "all":
        print_color("\n🗑️  Erasing all flash...", "yellow")
        erase_cmd = build_esptool_cmd(esptool, [
            "-p", port,
            "-b", BAUD_RATE,
            "erase-flash"
        ])
        return run_command(erase_cmd)

    elif erase_mode == "keep_nvs_littlefs":
        print_color("\n🗑️  Erasing app partitions (keeping NVS & LittleFS)...", "yellow")

        # Erase app0 and app1 partitions
        if "app0" in partitions:
            app0_offset = partitions["app0"]["offset"]
            app0_size = partitions["app0"]["size"]
            print_color(f"   Erasing app0: {app0_offset} ({app0_size} bytes)", "yellow")
            erase_cmd = build_esptool_cmd(esptool, [
                "-p", port,
                "-b", BAUD_RATE,
                "erase-region",
                app0_offset,
                app0_size
            ])
            if not run_command(erase_cmd):
                return False

        if "app1" in partitions:
            app1_offset = partitions["app1"]["offset"]
            app1_size = partitions["app1"]["size"]
            print_color(f"   Erasing app1: {app1_offset} ({app1_size} bytes)", "yellow")
            erase_cmd = build_esptool_cmd(esptool, [
                "-p", port,
                "-b", BAUD_RATE,
                "erase-region",
                app1_offset,
                app1_size
            ])
            if not run_command(erase_cmd):
                return False

        return True

    return False


def clean_project(clean_all: bool = False, dry_run: bool = False) -> bool:
    """
    Clean project by removing build artifacts, cache, and temporary files.

    Args:
        clean_all: If True, also removes downloaded libraries and caches
        dry_run: If True, shows what would be deleted without actually deleting

    Returns:
        True if successful, False otherwise
    """
    print_color("\n🧹 Cleaning project", "bold")

    if dry_run:
        print_color("   (DRY RUN - no files will be deleted)\n", "yellow")

    items_to_clean = []
    total_size = 0

    # Always cleaned
    patterns_always = [
        ("build/", "Build artifacts"),
        ("firmware/", "Compiled firmware"),
        ("build.log", "Raw build output"),
        ("__pycache__/", "Python cache"),
        ("**/__pycache__/", "Python cache (nested)"),
        ("**/*.pyc", "Compiled Python files"),
        ("**/*.pyo", "Optimized Python files"),
        ("**/*.pyd", "Python DLL files"),
        ("*.bak", "Backup files"),
        ("*.bak_*", "Timestamped backups"),
        ("*~", "Editor temporary files"),
        ("*.swp", "Vim swap files"),
        ("*.swo", "Vim swap files"),
        ("*.tmp", "Temporary files"),
        (".DS_Store", "macOS system files"),
        (".DS_Store?", "macOS system variants"),
        (".Spotlight-V100", "macOS spotlight"),
        (".Trashes", "macOS trash"),
        ("Thumbs.db", "Windows thumbnail cache"),
        ("ehthumbs.db", "Windows thumbnail cache"),
    ]

    # Only with --clean-all
    patterns_clean_all = [
        ("libraries/", "Downloaded external libraries"),
        ("info/build_log.txt", "Build log file"),
        ("info/arduino_index_cache.json", "Arduino index cache"),
        ("info/libraries_updates_cache.json", "Libraries updates cache"),
        ("info/libraries_setup.json", "Libraries setup info"),
    ]

    all_patterns = patterns_always + (patterns_clean_all if clean_all else [])

    # Process each pattern
    for pattern, description in all_patterns:
        if "*" in pattern or "?" in pattern:
            # Glob pattern
            import glob
            matches = glob.glob(os.path.join(SKETCH_FOLDER, pattern), recursive=True)
            for match in matches:
                try:
                    if os.path.isfile(match):
                        size = os.path.getsize(match)
                        total_size += size
                        items_to_clean.append((match, description, size))
                    elif os.path.isdir(match):
                        for root, dirs, files in os.walk(match):
                            for file in files:
                                file_path = os.path.join(root, file)
                                size = os.path.getsize(file_path)
                                total_size += size
                                items_to_clean.append((file_path, description, size))
                except Exception as e:
                    print_color(f"   ⚠️  Error processing {match}: {e}", "yellow")
        else:
            # Direct path
            full_path = os.path.join(SKETCH_FOLDER, pattern)
            if os.path.exists(full_path):
                try:
                    if os.path.isfile(full_path):
                        size = os.path.getsize(full_path)
                        total_size += size
                        items_to_clean.append((full_path, description, size))
                    elif os.path.isdir(full_path):
                        for root, dirs, files in os.walk(full_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                size = os.path.getsize(file_path)
                                total_size += size
                                items_to_clean.append((file_path, description, size))
                except Exception as e:
                    print_color(f"   ⚠️  Error processing {full_path}: {e}", "yellow")

    if not items_to_clean:
        # No files to delete, but still check for empty directories
        def remove_dir_recursive_if_empty(path):
            """Remove directory and its empty parent directories recursively."""
            if not os.path.isdir(path):
                return False
            # First, try to remove empty subdirectories
            removed_any = False
            for item in os.listdir(path):
                subpath = os.path.join(path, item)
                if os.path.isdir(subpath):
                    if remove_dir_recursive_if_empty(subpath):
                        removed_any = True
            # Then try to remove this directory if it's now empty
            try:
                if not os.listdir(path):
                    os.rmdir(path)
                    print_color(f"   🗑️  Removed empty folder: {os.path.relpath(path, SKETCH_FOLDER)}/", "cyan")
                    return True
            except Exception:
                pass
            return removed_any

        # Check for common empty build directories
        removed_any = False
        dirs_to_check_empty = ["build", "firmware"]
        if clean_all:
            dirs_to_check_empty.append("libraries")
        for dirname in dirs_to_check_empty:
            full_path = os.path.join(SKETCH_FOLDER, dirname)
            if remove_dir_recursive_if_empty(full_path):
                removed_any = True

        if not removed_any:
            print_color("   ✅ Project is already clean, nothing to remove", "green")
        return True

    # Group by description and show summary
    grouped = {}
    for path, desc, size in items_to_clean:
        if desc not in grouped:
            grouped[desc] = []
        grouped[desc].append((path, size))

    # Display what will be cleaned
    print_color("   Items to be removed:", "blue")
    for desc in sorted(grouped.keys()):
        items = grouped[desc]
        total_desc = sum(size for _, size in items)
        count = len(items)

        if count == 1:
            print_color(f"     ✓ {desc}", "cyan")
            print_color(f"       {items[0][0]} ({format_hex_size(hex(items[0][1]))})", "cyan")
        else:
            print_color(f"     ✓ {desc} ({count} files, {format_hex_size(hex(total_desc))})", "cyan")

    # Convert to MB for display
    total_mb = total_size / (1024 * 1024)

    if dry_run:
        print_color(f"\n   📊 Would free: {total_mb:.1f} MB", "yellow")
        print_color("   (Use '--clean' without '--dry-run' to actually delete)", "yellow")
        return True

    # Ask for confirmation
    try:
        response = input(f"\n   ⚠️  Delete {len(items_to_clean)} items ({total_mb:.1f} MB)? (y/n): ").strip().lower()
        if response != 'y':
            print_color("   ❌ Cleanup cancelled", "yellow")
            return False
    except KeyboardInterrupt:
        print_color("\n   ❌ Cleanup cancelled", "yellow")
        return False

    # Actually delete files
    deleted_count = 0
    failed_count = 0
    dirs_to_check = set()

    for path, desc, size in items_to_clean:
        try:
            if os.path.isfile(path):
                parent_dir = os.path.dirname(path)
                os.remove(path)
                deleted_count += 1
                # Track parent directory for potential removal if empty
                if parent_dir and parent_dir != SKETCH_FOLDER:
                    dirs_to_check.add(parent_dir)
            elif os.path.isdir(path):
                shutil.rmtree(path)
                deleted_count += 1
        except Exception as e:
            print_color(f"   ❌ Failed to delete {path}: {e}", "red")
            failed_count += 1

    # Remove empty directories (build/, firmware/, etc.)
    # Walk through tracked directories from deepest to shallowest
    for dir_path in sorted(dirs_to_check, reverse=True):
        try:
            if os.path.isdir(dir_path) and not os.listdir(dir_path):
                os.rmdir(dir_path)
                print_color(f"   🗑️  Removed empty folder: {os.path.relpath(dir_path, SKETCH_FOLDER)}/", "cyan")
        except Exception:
            pass  # Ignore errors (folder might not be empty or might not exist)

    # Also remove well-known build directories if they're empty (including subdirectories)
    def remove_dir_recursive_if_empty(path):
        """Remove directory and its empty parent directories recursively."""
        if not os.path.isdir(path):
            return
        # First, try to remove empty subdirectories
        for item in os.listdir(path):
            subpath = os.path.join(path, item)
            if os.path.isdir(subpath):
                remove_dir_recursive_if_empty(subpath)
        # Then try to remove this directory if it's now empty
        try:
            if not os.listdir(path):
                os.rmdir(path)
                print_color(f"   🗑️  Removed empty folder: {os.path.relpath(path, SKETCH_FOLDER)}/", "cyan")
        except Exception:
            pass

    # Remove common build directories
    dirs_to_remove = ["build", "firmware"]
    if clean_all:
        dirs_to_remove.append("libraries")
    for dirname in dirs_to_remove:
        full_path = os.path.join(SKETCH_FOLDER, dirname)
        remove_dir_recursive_if_empty(full_path)

    # Remove all __pycache__ directories recursively
    for root, dirs, files in os.walk(SKETCH_FOLDER, topdown=False):
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            remove_dir_recursive_if_empty(pycache_path)

    # Show results
    print()
    if failed_count > 0:
        print_color(f"   ⚠️  Cleanup partial: {deleted_count} deleted, {failed_count} failed", "yellow")
        return False
    else:
        print_color(f"   ✅ Cleanup complete - {total_mb:.1f} MB freed", "green")
        print_color(f"   📊 Deleted {deleted_count} items/folders", "green")
        return True


def main():
    parser = argparse.ArgumentParser(
        description=BUILD_CONFIG["project"] + " — build.py est le point d entree utilisateur",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Depuis le depot d'outils, selectionner le projet :
  python3 build.py --project CHEMIN --info
  python3 build.py --project CHEMIN --check-environment
  python3 build.py --project CHEMIN --check-libraries
  python3 build.py --project CHEMIN --build
  python3 build.py --project CHEMIN --build-littlefs
  python3 build.py --project CHEMIN --flash --port PORT_CONFIRME
  python3 build.py --project CHEMIN --littlefs --port PORT_CONFIRME

--build construit aussi LittleFS si le dossier data/ du sketch existe.
Aucun flash avec --build. Configuration : build-config.json dans le projet.
Le packaging OTA autonome utilise les scripts du dossier ota/.
Un wrapper de projet peut ajouter ses propres commandes.
        """
    )

    parser.add_argument(
        "--auto",
        action="store_true",
        help="Compiler puis ecrire firmware et LittleFS ; --port explicite requis"
    )

    parser.add_argument(
        "--build",
        action="store_true",
        help="Compile the sketch"
    )

    parser.add_argument(
        "--flash",
        action="store_true",
        help="Flash firmware to device"
    )

    parser.add_argument(
        "--littlefs",
        action="store_true",
        help="Flash LittleFS partition"
    )

    parser.add_argument(
        "--erase",
        choices=["none", "all", "keep_nvs_littlefs"],
        default="none",
        help="Effacement desactive : proteger les partitions persistantes"
    )

    parser.add_argument(
        "-p", "--port",
        help="Port confirme obligatoire pour les ecritures appareil",
        default=None
    )

    parser.add_argument(
        "-b", "--baud",
        help="Baud rate",
        default=BAUD_RATE
    )

    parser.add_argument(
        "--info",
        action="store_true",
        help="Show configuration"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output for build process"
    )

    parser.add_argument(
        "--log",
        help="Custom build log filename (default: build_log_YYYYMMDD_HHMMSS.txt)",
        default=None
    )

    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify flashed firmware against local binary (byte-by-byte + SHA256)"
    )

    parser.add_argument(
        "--expect-mac",
        default=None,
        help="Refuse to flash unless the device reports this MAC (as shown by esptool read-mac)"
    )

    # Library management arguments
    parser.add_argument(
        "--sync-libraries",
        action="store_true",
        help="Sync libraries from .ino file (auto-discover and download)"
    )

    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Check for available library updates"
    )

    parser.add_argument(
        "--update-libraries",
        action="store_true",
        help="Update libraries to latest versions"
    )

    parser.add_argument(
        "--list-libs",
        action="store_true",
        help="List all installed Arduino libraries (core + user-installed)"
    )

    parser.add_argument(
        "--ext-libs-bckp",
        type=str,
        nargs="?",
        const="",  # Empty string when flag provided without argument
        default=None,  # None when flag not provided at all
        metavar="DIR",
        help="Backup external libraries to directory (default: ./arduino-libs)"
    )

    parser.add_argument(
        "--auto-update",
        action="store_true",
        help="Check for updates before building and auto-apply if found"
    )

    parser.add_argument(
        "--build-littlefs",
        action="store_true",
        help="Build LittleFS image from /data directory"
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="Desactive pour ce projet : conserver les archives privees"
    )

    parser.add_argument(
        "--clean-all",
        action="store_true",
        help="Desactive pour ce projet"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting (use with --clean or --clean-all)"
    )

    parser.add_argument(
        "--silent",
        action="store_true",
        help="Non-interactive mode: skip all prompts and use defaults"
    )

    parser.add_argument(
        "--check-libraries",
        action="store_true",
        help="Check if required libraries are installed with correct versions"
    )

    parser.add_argument("--check-environment", action="store_true", help="Verifier le core, les partitions et la politique du projet, sans ecriture appareil")
    args = parser.parse_args()
    from .partitions import validate_layout
    try:
        validate_layout(os.path.join(SKETCH_FOLDER, PARTITIONS_CSV))
    except ValueError as exc:
        parser.error(str(exc))
    if args.erase != "none":
        parser.error("Erase modes disabled: preserve NVS and Zigbee pairing")
    if args.auto:
        args.build = args.flash = args.littlefs = True
        args.auto = False
    if (args.flash or args.littlefs) and not args.port:
        parser.error("Explicit --port required: confirm the connected C6 first")
    if args.clean or args.clean_all:
        parser.error("Use --build, --build-littlefs, --flash and --littlefs explicitly for this bench")


    print_color(f"\n{'='*60}", "bold")
    print_color(f"{BUILD_CONFIG['project']} — ESP32 Build & Flash Utility", "header")
    print_color(f"{'='*60}", "bold")

    # Clean mode (can be combined with --build, --flash, etc.)
    if args.clean or args.clean_all:
        success = clean_project(clean_all=args.clean_all, dry_run=args.dry_run)
        if args.dry_run:
            return  # Dry run, don't do anything else
        if not success:
            sys.exit(1)
        # If ONLY clean was requested, stop here
        if not (args.build or args.flash or args.littlefs or args.build_littlefs):
            return
        # Otherwise continue to build/flash operations below

    # Library management modes
    if args.check_libraries:
        requirements_file = str(project_path(ROOT, BUILD_CONFIG["paths"]["requirements"]))
        all_ok, passed, failed = check_requirements(requirements_file, verbose=True)
        if not all_ok:
            sys.exit(1)
        return

    if args.sync_libraries:
        manager = LibraryManager(SKETCH_FOLDER)
        success, libs = manager.sync_from_ino(SKETCH_NAME)
        if success:
            # Count library types
            user_libs = [lib for lib in libs if lib.get("source") != "board_package"]
            core_libs = [lib for lib in libs if lib.get("source") == "board_package"]

            print_color(f"\n📚 Library Summary:", "bold")
            print_color(f"  • User Libraries:  {len(user_libs)}", "blue")
            for lib in user_libs:
                print_color(f"    - {lib['name']:<30} v{lib['version']}", "blue")

            print_color(f"  • Core Libraries:  {len(core_libs)} (ESP32 board package)", "blue")
            for lib in core_libs:
                print_color(f"    - {lib['name']:<30} (bundled)", "blue")

            print_color(f"\n✅ Library sync complete! ({len(libs)} total libraries)", "green")
        else:
            print_color(f"\n❌ Library sync failed", "red")
            sys.exit(1)
        return

    if args.check_updates:
        manager = LibraryManager(SKETCH_FOLDER)
        updates = manager.check_updates(use_cache=not args.verbose)

        # Show summary
        if updates:
            print_color(f"\n📊 Update Summary:", "bold")
            print_color(f"  • {len(updates)} update(s) available:", "yellow")
            for lib_name, info in updates.items():
                print_color(f"    - {lib_name:<30} {info['current']} → {info['latest']}", "yellow")
            print_color(f"\n💡 Run 'python3 build.py --update-libraries' to apply updates", "blue")
        else:
            print_color(f"\n✅ All libraries are up to date!", "green")
        return

    if args.update_libraries:
        manager = LibraryManager(SKETCH_FOLDER)
        success, updated = manager.update_libraries()
        if success:
            if updated:
                print_color(f"\n✅ Successfully updated {len(updated)} library/libraries:", "green")
                for lib_name in updated:
                    print_color(f"  • {lib_name}", "green")
            else:
                print_color(f"\n✅ All libraries are already up to date", "green")
        else:
            print_color(f"\n❌ Update failed", "red")
            sys.exit(1)
        return

    if args.list_libs:
        manager = LibraryManager(SKETCH_FOLDER)
        manager.list_all_libraries()
        return

    if args.ext_libs_bckp is not None:
        manager = LibraryManager(SKETCH_FOLDER)
        # Empty string means use default, otherwise use provided path
        backup_dir = args.ext_libs_bckp if args.ext_libs_bckp else None
        success = manager.backup_external_libraries(backup_dir)
        if success:
            print_color(f"\n✅ External libraries backup completed", "green")
        else:
            print_color(f"\n❌ Backup failed", "red")
            sys.exit(1)
        return

    if args.check_environment:
        try:
            report = check_environment(ROOT, BUILD_CONFIG)
        except (ValueError, OSError, KeyError) as exc:
            parser.error(str(exc))
        print(f"Environnement OK : core {report['core']}, firmware {report['version']}, slot {report['maximum_size']} octets")
        print('Controle projet :', report.get('zigbee_changed_files', []))
        return

    # Independent flags: --build-littlefs builds, --flash writes firmware,
    # --littlefs writes the FS. No implicit conversion of one into another.
    if args.build_littlefs:
        if not build_littlefs_image(LITTLEFS_PATH):
            sys.exit(1)
        if not (args.build or args.flash or args.littlefs):
            return

    if args.info:
        print_color("\nConfiguration:", "bold")
        print(f"  Configuration: {ROOT / 'build-config.json'}")
        print(f"  Firmware: {FW_VERSION} (depuis {BUILD_CONFIG['paths']['version_header']})")
        print(f"  Core requis: {BUILD_CONFIG['core']['id']} {BUILD_CONFIG['core']['version']}")
        print(f"  Carte: {BUILD_CONFIG['board']['id']} ({BUILD_CONFIG['chip']})")
        print(f"  Partitions: {BUILD_CONFIG['paths']['partitions']}")
        print(f"  Bibliotheques: {BUILD_CONFIG['paths']['requirements']}")
        print(f"  Politique projet: {BUILD_CONFIG.get('policy', 'standard')}")
        if "local_zigbee" in BUILD_CONFIG:
            print(f"  Adaptation Zigbee: {BUILD_CONFIG['local_zigbee']['patched_file']}")
        print(f"  Sketch: {SKETCH_NAME}")
        print(f"  FQBN: {FQBN}")
        print(f"  Build Path: {BUILD_PATH}")
        print(f"  Firmware Dir: {FIRMWARE_DIR}")
        print(f"  Baud Rate: {BAUD_RATE}")
        return

    # Auto mode
    if args.auto:
        interactive_auto_mode(verbose=args.verbose)
        return

    # Regular mode with flags
    if not (args.build or args.flash or args.littlefs or args.erase != "none"):
        parser.print_help()
        return

    # Get serial port if needed
    port = None
    if args.flash or args.littlefs or args.erase != "none":
        if args.port:
            port = args.port
        else:
            port = get_port_with_confirmation()
            if not port:
                print_color("❌ No serial port specified", "red")
                sys.exit(1)

    # Build
    if args.build:
        try:
            report = check_environment(ROOT, BUILD_CONFIG)
        except (ValueError, OSError, KeyError) as exc:
            parser.error(str(exc))
        print(f"Core {report['core']}, partitions et copie Zigbee locale verifies")
        # Check library requirements before building
        print_color("\n📚 Checking library requirements...", "blue")
        requirements_file = str(project_path(ROOT, BUILD_CONFIG["paths"]["requirements"]))
        all_ok, passed, failed = check_requirements(requirements_file, verbose=False)

        if not all_ok:
            print_color("\n❌ Library requirements not satisfied!", "red")
            print_color("   Run: python3 build.py --check-libraries", "yellow")
            sys.exit(1)
        else:
            print_color(f"✅ All {len(passed)} library requirements satisfied", "green")

        # SxS can generate a boot-display header from a synchronized catalog.
        # This bench uses the checked requirements file and has no such display.
        manager = LibraryManager(SKETCH_FOLDER)
        if os.path.isfile(manager.libraries_json):
            if not manager.generate_libraries_header():
                print_color("Failed to generate libraries header", "red")
                sys.exit(1)

        # Auto-update libraries if requested
        if args.auto_update:
            manager = LibraryManager(SKETCH_FOLDER)
            updates = manager.check_updates(use_cache=True)
            if updates:
                print_color(f"\n📦 {len(updates)} library update(s) available", "yellow")
                try:
                    response = input("Apply updates before building? (y/n): ").strip().lower()
                    if response == 'y':
                        success, updated = manager.update_libraries()
                        if success:
                            print_color(f"✅ Updated {len(updated)} libraries", "green")
                        else:
                            print_color(f"⚠️  Some updates failed, continuing with build...", "yellow")
                except KeyboardInterrupt:
                    print_color("\n❌ Cancelled", "red")
                    sys.exit(1)

        success, build_output = build_sketch(verbose=args.verbose)
        if not success:
            sys.exit(1)

        # Find firmware in ./firmware directory
        firmware_file = find_compiled_firmware()
        if not firmware_file:
            print_color(f"⚠️  Could not locate compiled firmware binary", "yellow")
        else:
            # Keep firmware only in ./firmware/ directory (no copy to root)
            # firmware_file = copy_firmware_to_local(firmware_file)
            pass
            if firmware_file:
                app_bin = os.path.join(os.path.dirname(firmware_file), f"{SKETCH_NAME}.bin")
                if os.path.exists(app_bin):
                    report_flash_budget(app_bin)
                # Generate and save build log
                log_content = generate_build_log(build_output or "", firmware_file)
                save_build_log(log_content, filename=args.log)

                # Check for library issues
                build_info = extract_build_info(build_output or "")
                lib_validation = validate_libraries(build_info)
                if lib_validation["incomplete"]:
                    print_color(f"\n⚠️  LIBRARY ISSUES DETECTED:", "yellow")
                    for item in lib_validation["incomplete"]:
                        print_color(f"   ❌ {item['include']} - Library: {item['library']}", "yellow")
                        print_color(f"      Issue: {item['reason']}", "yellow")
                    print_color(f"\n   💡 Fix: Run 'python3 build.py --sync-libraries' to download missing libraries\n", "yellow")
                elif lib_validation["missing"]:
                    print_color(f"\n⚠️  MISSING LIBRARIES DETECTED:", "yellow")
                    for include in lib_validation["missing"]:
                        print_color(f"   ❌ {include} (#include found but not compiled)", "yellow")
                    print_color(f"\n   💡 Fix: Run 'python3 build.py --sync-libraries' to download missing libraries\n", "yellow")

        # Auto-build LittleFS if /data directory exists
        data_dir = os.path.join(SKETCH_FOLDER, "data")
        if os.path.isdir(data_dir):
            print_color("\n📁 Detected /data directory - building LittleFS image...", "blue")
            if build_littlefs_image(LITTLEFS_PATH):
                print_color("✅ LittleFS image built successfully!", "green")
                print_color(f"   Location: {LITTLEFS_PATH}", "blue")
            else:
                print_color("❌ LittleFS build failed; build rejected", "red")
                sys.exit(1)

    # Show flash plan summary
    if args.flash or args.littlefs:
        print_color("\n" + "="*60, "bold")
        print_color("📋 Flash Plan Summary", "bold")
        print_color("="*60, "bold")

        # Check what will be flashed
        flash_items = []

        if args.flash:
            # Show individual components that will actually be flashed
            firmware_dir = FIRMWARE_DIR
            bootloader_bin = os.path.join(firmware_dir, f"{SKETCH_NAME}.bootloader.bin")
            partitions_bin = os.path.join(firmware_dir, f"{SKETCH_NAME}.partitions.bin")
            app_bin = os.path.join(firmware_dir, f"{SKETCH_NAME}.bin")

            total_size = 0
            if os.path.exists(bootloader_bin):
                size = os.path.getsize(bootloader_bin)
                total_size += size
                flash_items.append(f"    • {BUILD_CONFIG['bootloader_offset']}: bootloader.bin ({size:,} bytes)")
            if os.path.exists(partitions_bin):
                size = os.path.getsize(partitions_bin)
                total_size += size
                flash_items.append(f"    • 0x8000:  partitions.bin ({size:,} bytes)")

            boot_app0_path = find_boot_app0_path()
            if boot_app0_path:
                size = os.path.getsize(boot_app0_path)
                total_size += size
                flash_items.append(f"    • OTA boot metadata: boot_app0.bin ({size:,} bytes)")

            if os.path.exists(app_bin):
                size = os.path.getsize(app_bin)
                total_size += size
                flash_items.append(f"    • {hex(validate_layout(PARTITIONS_CSV)['app0'][2])}: app.bin ({size:,} bytes)")

            if total_size > 0:
                flash_items.insert(0, f"  ✓ Firmware components (total: {total_size:,} bytes):")
            else:
                flash_items.append("  ✗ Firmware: NOT FOUND")

        if args.littlefs:
            if os.path.exists(LITTLEFS_PATH):
                flash_items.append(f"  ✓ LittleFS: {os.path.basename(LITTLEFS_PATH)} ({os.path.getsize(LITTLEFS_PATH):,} bytes)")
            else:
                flash_items.append(f"  ✗ LittleFS: NOT FOUND (will build if needed)")

        if args.erase != "none":
            erase_desc = {
                "all": "Complete flash erase (everything)",
                "keep_nvs_littlefs": "Erase app partitions only (keep WiFi/settings/LittleFS)"
            }
            flash_items.append(f"  🗑️  Erase: {erase_desc.get(args.erase, args.erase)}")
        else:
            flash_items.append(f"  ⏭️  Erase: None (incremental update)")

        print_color("\nWhat will be flashed:", "yellow")
        for item in flash_items:
            print(item)

        print_color(f"\nTarget port: {port}", "blue")
        print_color("="*60 + "\n", "bold")

    # Flash firmware (includes erase if specified)
    if args.flash:
        # Try to find the compiled firmware
        firmware_file = find_compiled_firmware()
        if not firmware_file:
            print_color(f"❌ Firmware not found in build directories", "red")
            print_color(f"   Have you compiled the sketch? (use --build)", "yellow")
            sys.exit(1)

        print_color(f"📦 Firmware: {firmware_file}", "blue")
        print_color(f"SHA256: {calculate_sha256(firmware_file)}", "yellow")
        if not flash_firmware(port, firmware_file, erase_mode=args.erase, expect_mac=args.expect_mac):
            sys.exit(1)

        # Verify if requested: per component, never the merged image (it spans
        # NVS/LittleFS regions the device rewrites, so it can never match).
        if args.verify:
            if not verify_flashed_components(port, firmware_file):
                sys.exit(1)

        # Auto-flash LittleFS if it exists (when using --flash)
        if False:  # B4E: LittleFS flash must always be explicit (--littlefs).
            print_color("\n📁 LittleFS image detected - flashing filesystem...", "blue")
            if not flash_littlefs(port, LITTLEFS_PATH):
                print_color("⚠️  LittleFS flash failed (firmware was flashed successfully)", "yellow")
            else:
                print_color("✅ LittleFS flashed successfully!", "green")

    # Flash LittleFS (explicit --littlefs flag)
    if args.littlefs:
        # Auto-build if image doesn't exist
        if not os.path.exists(LITTLEFS_PATH):
            print_color(f"\n⚠️  LittleFS image not found: {LITTLEFS_PATH}", "yellow")
            try:
                response = input("Build LittleFS image from /data directory? (y/n): ").strip().lower()
                if response == 'y':
                    if not build_littlefs_image(LITTLEFS_PATH):
                        print_color("\n❌ Failed to build LittleFS image", "red")
                        sys.exit(1)
                else:
                    print_color("❌ LittleFS image required to flash", "red")
                    sys.exit(1)
            except KeyboardInterrupt:
                print_color("\n❌ Cancelled by user", "red")
                sys.exit(1)

        if not flash_littlefs(port, LITTLEFS_PATH, expect_mac=args.expect_mac):
            sys.exit(1)

    # Erase only (if no flash/littlefs)
    if args.erase != "none" and not (args.flash or args.littlefs):
        if not erase_regions(port, args.erase):
            sys.exit(1)

    print_color("\n" + "="*60, "bold")
    print_color("✅ Operation completed", "green")
    print_color("="*60 + "\n", "bold")


if __name__ == "__main__":
    main()
