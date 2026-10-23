#!/usr/bin/env python3
"""
Library Manager - Handles library discovery, version checking, and updates
Works with any Arduino project - auto-discovers libraries from Arduino's official sources
"""

import os
from .console import safe_print as print
import json
import re
import subprocess
import requests
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import hashlib

# Colors for terminal output
COLORS = {
    "green": "\033[92m",
    "red": "\033[91m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def print_color(msg: str, color: str = "reset", **kwargs) -> None:
    """Print colored text to terminal."""
    print(f"{COLORS.get(color, '')}{msg}{COLORS['reset']}", **kwargs)


class LibraryManager:
    """Manages library discovery, updates, and version checking for any Arduino project."""

    def __init__(self, sketch_folder: str):
        """Initialize LibraryManager."""
        self.sketch_folder = sketch_folder
        self.info_dir = os.path.join(sketch_folder, "info")
        self.libraries_json = os.path.join(self.info_dir, "libraries.json")
        self.libraries_dir = os.path.join(sketch_folder, "libraries")
        self.index_cache_file = os.path.join(self.info_dir, "arduino_index_cache.json")
        self.cache_ttl = 3600  # 1 hour

        # Arduino Library Index will be loaded lazily (on first use)
        self._arduino_index = None

    def _load_arduino_index(self, use_cache: bool = True) -> Dict[str, Dict]:
        """
        Load Arduino Library Index and build header→library mapping.
        Returns: {"ArduinoJson.h": {"library": "ArduinoJson", ...}, ...}
        """
        # Return cached if already loaded
        if self._arduino_index is not None:
            return self._arduino_index

        # Try cache first
        if use_cache and os.path.exists(self.index_cache_file):
            try:
                with open(self.index_cache_file, "r") as f:
                    cache = json.load(f)
                    if datetime.fromisoformat(cache.get("expires_at", "")) > datetime.now():
                        self._arduino_index = cache.get("index", {})
                        return self._arduino_index
            except Exception:
                pass

        # Fetch from Arduino's official library index
        print_color("📥 Loading Arduino Library Index...", "blue")
        try:
            url = "https://downloads.arduino.cc/libraries/library_index.json"
            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                data = response.json()
                index = {}

                # Build mapping: header → library info
                for lib in data.get("libraries", []):
                    lib_name = lib.get("name", "")

                    # Add common header variants
                    headers = [
                        f"{lib_name}.h",                          # Exact match
                        f"{lib_name.replace(' ', '_')}.h",        # Space → underscore
                        f"{lib_name.replace('_', '')}.h",         # Remove underscores
                        lib_name.lower() + ".h",                  # Lowercase
                        lib_name.replace(" ", "_").lower() + ".h", # Space → underscore + lowercase
                    ]

                    for header in headers:
                        index[header] = {
                            "library": lib_name,
                            "source": "library_manager",
                            "version": lib.get("version", "unknown"),
                            "url": lib.get("website", ""),
                            "github": lib.get("repository", ""),
                        }

                # Note: Board package libraries (WiFi.h, Arduino.h, etc.) are NOT hardcoded
                # They will be discovered automatically:
                # 1. If they're in the Arduino Library Index (unlikely)
                # 2. As unknown headers → treated as board package
                # 3. arduino-cli will validate them during compilation

                self._arduino_index = index

                # Cache for 24 hours
                self._save_index_cache(index)
                print_color(f"✅ Loaded {len(index)} library headers", "green")
                return index

            else:
                print_color(f"⚠️  Could not fetch Arduino Index (HTTP {response.status_code})", "yellow")
                return {}

        except requests.exceptions.Timeout:
            print_color("⚠️  Arduino Index fetch timeout - using defaults", "yellow")
            return {}
        except Exception as e:
            print_color(f"⚠️  Error loading Arduino Index: {e}", "yellow")
            return {}

    def _save_index_cache(self, index: Dict) -> None:
        """Cache Arduino Library Index."""
        try:
            os.makedirs(self.info_dir, exist_ok=True)
            cache = {
                "timestamp": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(seconds=86400)).isoformat(),  # 24 hours
                "index": index,
            }
            with open(self.index_cache_file, "w") as f:
                json.dump(cache, f, indent=2)
        except Exception:
            pass  # Silent fail on cache write

    def parse_includes_from_ino(self, ino_file: str) -> List[str]:
        """
        Parse .ino file AND all src/ files to extract #include directives.
        Returns list of header files: ["ArduinoJson.h", "WiFi.h", ...]
        """
        if not os.path.exists(ino_file):
            print_color(f"❌ .ino file not found: {ino_file}", "red")
            return []

        includes = set()  # Use set to avoid duplicates
        files_to_scan = [ino_file]
        files_to_scan.extend(str(p) for p in Path(self.sketch_folder).iterdir()
                             if p.is_file() and p.suffix in ('.cpp', '.h'))

        # Add all .h and .cpp files from src/ directory
        src_dir = os.path.join(self.sketch_folder, "src")
        if os.path.exists(src_dir):
            for root, dirs, files in os.walk(src_dir):
                for file in files:
                    if file.endswith(('.h', '.cpp')):
                        files_to_scan.append(os.path.join(root, file))

        try:
            # Scan all files for #include statements
            for file_path in files_to_scan:
                try:
                    with open(file_path, "r") as f:
                        content = f.read()

                    # Find all #include <...> and #include "..."
                    pattern = r'#include\s+[<"]([^>"]+)[>"]'
                    matches = re.findall(pattern, content)

                    for match in matches:
                        if (Path(file_path).parent / match).is_file():
                            continue
                        # Skip project-local includes (src/*, lib/*, etc.)
                        if match.startswith(("src/", "lib/", "libraries/", "../", "certs/")):
                            continue

                        # Skip ESP32 system/IDF headers
                        if match.startswith(("esp_", "mbedtls/", "freertos/", "rom/", "soc/", "ping/", "lwip/")):
                            continue

                        # Skip standard C/C++ headers
                        if not match.endswith(".h"):
                            continue
                        if match in ("string.h", "stdarg.h", "math.h", "stdlib.h", "stdio.h",
                                    "stdint.h", "stdbool.h", "time.h", "errno.h", "assert.h",
                                    "limits.h", "float.h", "ctype.h", "wchar.h"):
                            continue

                        # Check if this header exists in the src/ directory (project header)
                        # This catches relative includes like "logger.h", "cli.h", etc.
                        src_dir = os.path.join(self.sketch_folder, "src")
                        if os.path.exists(src_dir):
                            # Search for the header in src/ directory
                            header_found_in_src = False
                            for root, dirs, files in os.walk(src_dir):
                                if match in files:
                                    header_found_in_src = True
                                    break
                            if header_found_in_src:
                                continue  # Skip project headers

                        # Add external library header
                        includes.add(match)
                except Exception as e:
                    # Skip files that can't be read
                    continue

            return sorted(list(includes))
        except Exception as e:
            print_color(f"❌ Error parsing includes: {e}", "red")
            return []

    def map_include_to_library(self, header_file: str) -> Optional[Dict]:
        """
        Map a header file to library information using Arduino's official index.
        Returns: {"library": "name", "source": "library_manager", "url": "...", ...}
        """
        # ESP32 Core Libraries - These are NOT installable via arduino-cli
        # They come with the ESP32 board package and must NOT be treated as library_manager libraries
        ESP32_CORE_LIBRARIES = {
            "WiFi.h", "Preferences.h", "LittleFS.h", "SPIFFS.h", "FS.h",
            "ESPmDNS.h", "Update.h", "HTTPClient.h", "HTTPUpdate.h",
            "WebServer.h", "ArduinoOTA.h", "EEPROM.h", "Wire.h", "SPI.h",
            "SD.h", "SD_MMC.h", "FFat.h", "Ticker.h", "BluetoothSerial.h",
            "BLE.h", "esp_now.h", "NetworkClientSecure.h", "Network.h",
            "Hash.h", "DNSServer.h", "AsyncUDP.h",
        }

        # Check if this is an ESP32 core library BEFORE checking Arduino Index
        if header_file in ESP32_CORE_LIBRARIES:
            return None  # Treat as board_package (will be validated at compile time)

        # Load Arduino Index (cached after first call)
        index = self._load_arduino_index()

        # Direct lookup
        if header_file in index:
            return index[header_file]

        # Try variations
        variants = [
            header_file.replace(".h", "").replace("/", "") + ".h",
            header_file.split("/")[0] + ".h",  # For headers like "mbedtls/sha256.h"
        ]

        for variant in variants:
            if variant in index:
                return index[variant]

        # Not found
        return None

    def query_github_latest_version(self, repo: str) -> Optional[str]:
        """
        Query GitHub API for latest release version.
        repo format: "user/repo"
        Returns: "1.2.3" or None
        """
        try:
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            headers = {"Accept": "application/vnd.github.v3+json"}
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                tag = data.get("tag_name", "").lstrip("v")
                if tag:
                    return tag
            elif response.status_code == 403:
                # Rate limited - return None silently
                return None
            return None
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.ConnectionError:
            return None
        except Exception as e:
            return None

    def query_arduino_index_version(self, library_name: str) -> Optional[str]:
        """
        Query Arduino Library Index for latest version.
        Returns: "1.2.3" or None
        """
        try:
            url = "https://downloads.arduino.cc/libraries/library_index.json"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                # Find all versions of the library (index has multiple entries per library)
                versions = []
                for lib in data.get("libraries", []):
                    if lib.get("name") == library_name:
                        version = lib.get("version")
                        if version:
                            versions.append(version)

                # Return the last version (they're sorted in the index)
                if versions:
                    return versions[-1]

            return None
        except Exception as e:
            print_color(f"⚠️  Arduino Index error for {library_name}: {e}", "yellow")
            return None

    def get_installed_version(self, library_name: str) -> Optional[str]:
        """
        Query arduino-cli for installed library version.
        Returns: "1.2.3" or None
        """
        try:
            result = subprocess.run(
                ["arduino-cli", "lib", "list", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                for lib_entry in data.get("installed_libraries", []):
                    lib = lib_entry.get("library", {})
                    if lib.get("name") == library_name:
                        return lib.get("version")
            return None
        except Exception as e:
            return None

    def backup_external_libraries(self, backup_dir: str = None) -> bool:
        """
        Backup project's external libraries to backup directory with versions.txt
        Only backs up libraries listed in libraries.json (source: library_manager)
        Returns: True if successful, False otherwise
        """
        # Default to arduino-libs in sketch folder
        if backup_dir is None:
            backup_dir = os.path.join(self.sketch_folder, "arduino-libs")
        import shutil
        from datetime import datetime

        try:
            # Create backup directory
            os.makedirs(backup_dir, exist_ok=True)
            print_color(f"\n📦 Backing up project external libraries to: {backup_dir}", "bold")

            # Read libraries.json to get project libraries
            if not os.path.exists(self.libraries_json):
                print_color("❌ libraries.json not found - run --sync-libraries first", "red")
                return False

            with open(self.libraries_json, "r") as f:
                lib_data = json.load(f)

            # Extract project library names (source: library_manager only)
            project_lib_names = set()
            for lib in lib_data.get("libraries", []):
                if lib.get("source") == "library_manager":
                    project_lib_names.add(lib.get("name"))

            if not project_lib_names:
                print_color("⚠️  No external libraries found in project", "yellow")
                return False

            print_color(f"📋 Found {len(project_lib_names)} project libraries to backup", "blue")

            # Query arduino-cli for user-installed libraries
            result = subprocess.run(
                ["arduino-cli", "lib", "list", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print_color("❌ Failed to query arduino-cli", "red")
                return False

            data = json.loads(result.stdout)
            user_libs = []

            # Filter to only project libraries + dependencies
            for lib_entry in data.get("installed_libraries", []):
                lib = lib_entry.get("library", {})
                lib_name = lib.get("name")

                # Include if:
                # 1. It's in our project list, OR
                # 2. It's a known dependency (Async TCP for ESP Async WebServer)
                if lib.get("location") == "user":
                    if lib_name in project_lib_names:
                        user_libs.append({
                            "name": lib_name,
                            "version": lib.get("version"),
                            "install_dir": lib.get("install_dir")
                        })
                    elif "Async TCP" in lib_name and "ESP Async WebServer" in project_lib_names:
                        # Include Async TCP as it's a dependency of ESP Async WebServer
                        user_libs.append({
                            "name": lib_name,
                            "version": lib.get("version"),
                            "install_dir": lib.get("install_dir")
                        })

            if not user_libs:
                print_color("⚠️  No project libraries found in arduino-cli", "yellow")
                return False

            # Create versions manifest
            manifest_path = os.path.join(backup_dir, "library_versions.txt")
            with open(manifest_path, "w") as f:
                f.write("="*80 + "\n")
                f.write("SxS-FW Project External Libraries Backup\n")
                f.write(f"Backup Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Project: SxS-FW\n")
                f.write(f"Total Libraries: {len(user_libs)}\n")
                f.write("="*80 + "\n\n")

                # Copy each library and write to manifest
                copied_count = 0
                failed = []

                for lib_info in sorted(user_libs, key=lambda x: x["name"]):
                    lib_name = lib_info["name"]
                    lib_version = lib_info["version"]
                    source_dir = lib_info["install_dir"]

                    if not source_dir or not os.path.exists(source_dir):
                        failed.append(lib_name)
                        continue

                    # Destination directory for this library
                    dest_dir = os.path.join(backup_dir, os.path.basename(source_dir))

                    try:
                        # Remove existing backup if present
                        if os.path.exists(dest_dir):
                            shutil.rmtree(dest_dir)

                        # Copy library directory
                        shutil.copytree(source_dir, dest_dir)

                        # Write to manifest
                        f.write(f"{lib_name:<40} v{lib_version}\n")
                        print_color(f"  ✓ {lib_name:<40} v{lib_version}", "green")
                        copied_count += 1

                    except Exception as e:
                        f.write(f"{lib_name:<40} v{lib_version} (FAILED: {str(e)})\n")
                        print_color(f"  ✗ {lib_name:<40} FAILED: {str(e)}", "red")
                        failed.append(lib_name)

                # Summary in manifest
                f.write("\n" + "="*80 + "\n")
                f.write(f"Summary: {copied_count} backed up, {len(failed)} failed\n")
                if failed:
                    f.write(f"Failed: {', '.join(failed)}\n")
                f.write("="*80 + "\n")

            # Print summary
            print_color(f"\n📊 Backup Summary:", "bold")
            print_color(f"  • Libraries backed up: {copied_count}", "green")
            if failed:
                print_color(f"  • Failed: {len(failed)}", "red")
            print_color(f"  • Manifest: {manifest_path}", "blue")
            print_color(f"  • Location: {backup_dir}", "blue")

            return True

        except Exception as e:
            print_color(f"❌ Backup failed: {e}", "red")
            return False

    def generate_libraries_header(self, output_path: str = None) -> bool:
        """
        Generate libraries.h header file from libraries used in the project.
        Reads from libraries.json and queries arduino-cli for current versions + dependencies.

        Args:
            output_path: Path to output header file (default: src/fw_config/libraries.h)

        Returns:
            True if successful, False otherwise
        """
        from datetime import datetime

        try:
            # Default output path
            if output_path is None:
                output_path = os.path.join(self.sketch_folder, "src", "fw_config", "libraries.h")

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Read libraries.json to get the base list of project libraries
            if not os.path.exists(self.libraries_json):
                print_color(f"⚠️  libraries.json not found - run with --sync-libraries first", "yellow")
                return False

            with open(self.libraries_json, "r") as f:
                data = json.load(f)

            # Get names of libraries from libraries.json (source=library_manager only)
            project_lib_names = set()
            for lib in data.get("libraries", []):
                if lib.get("source") == "library_manager":
                    project_lib_names.add(lib.get("name"))

            # Query arduino-cli for all user libraries to get current versions
            result = subprocess.run(
                ["arduino-cli", "lib", "list", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print_color("❌ Failed to query arduino-cli for libraries", "red")
                return False

            arduino_data = json.loads(result.stdout)
            external_libs = []

            # Match user libraries against project libraries + check for dependencies
            for lib_entry in arduino_data.get("installed_libraries", []):
                lib = lib_entry.get("library", {})
                lib_name = lib.get("name", "Unknown")

                # Include if:
                # 1. It's in our project list, OR
                # 2. It's a known dependency (Async TCP for ESP Async WebServer)
                if lib.get("location") == "user":
                    if lib_name in project_lib_names:
                        external_libs.append({
                            "name": lib_name,
                            "version": lib.get("version", "Unknown")
                        })
                    elif "Async TCP" in lib_name and "ESP Async WebServer" in project_lib_names:
                        # Include Async TCP as it's a dependency of ESP Async WebServer
                        external_libs.append({
                            "name": lib_name,
                            "version": lib.get("version", "Unknown")
                        })

            # Sort by name
            external_libs.sort(key=lambda x: x["name"])

            # Generate header file content
            header_content = f"""/**
 * @file    libraries.h
 * @brief   External library versions used in firmware build
 * @note    Auto-generated file - DO NOT EDIT MANUALLY
 * @date    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
 */

#pragma once

// Number of external libraries
#define EXTERNAL_LIBS_COUNT {len(external_libs)}

// Library name and version strings
const char* EXTERNAL_LIBS_NAMES[] = {{
"""

            # Add library names
            for i, lib in enumerate(external_libs):
                comma = "," if i < len(external_libs) - 1 else ""
                header_content += f'    "{lib["name"]}"{comma}\n'

            header_content += "};\n\nconst char* EXTERNAL_LIBS_VERSIONS[] = {\n"

            # Add library versions
            for i, lib in enumerate(external_libs):
                comma = "," if i < len(external_libs) - 1 else ""
                header_content += f'    "{lib["version"]}"{comma}\n'

            header_content += "};\n"

            # Write header file
            with open(output_path, "w") as f:
                f.write(header_content)

            print_color(f"✅ Generated {output_path}", "green")
            print_color(f"   Libraries: {len(external_libs)}", "blue")

            return True

        except Exception as e:
            print_color(f"❌ Failed to generate libraries header: {e}", "red")
            return False

    def list_all_libraries(self) -> None:
        """
        List all installed Arduino libraries (ESP32 core + user-installed).
        """
        import sys
        import os

        # Add tools directory to path for importing library_checker
        tools_dir = os.path.dirname(os.path.abspath(__file__))
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)

        from .library_checker import get_core_libraries

        print_color("\n📚 Installed Arduino Libraries", "bold")
        print_color("="*80, "blue")

        # Get ESP32 core libraries
        print_color("\n📦 ESP32 Core Libraries (bundled with board package):", "cyan")
        core_libs = get_core_libraries()
        if core_libs:
            for lib_name, version in sorted(core_libs.items()):
                print_color(f"  • {lib_name:<40} v{version}", "blue")
        else:
            print_color("  (none found)", "yellow")

        # Get user-installed libraries
        print_color("\n📚 User-Installed Libraries:", "cyan")
        try:
            result = subprocess.run(
                ["arduino-cli", "lib", "list", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                user_libs = []
                for lib_entry in data.get("installed_libraries", []):
                    lib = lib_entry.get("library", {})
                    if lib.get("location") == "user":  # Only user-installed
                        user_libs.append((lib.get("name"), lib.get("version")))

                if user_libs:
                    for lib_name, version in sorted(user_libs):
                        print_color(f"  • {lib_name:<40} v{version}", "green")
                    print_color(f"\n📊 Total: {len(core_libs)} core + {len(user_libs)} user = {len(core_libs) + len(user_libs)} libraries", "bold")
                else:
                    print_color("  (none installed)", "yellow")
            else:
                print_color("  ❌ Failed to query arduino-cli", "red")
        except Exception as e:
            print_color(f"  ❌ Error: {e}", "red")

    def get_latest_version(self, library_name: str, source: str) -> Optional[str]:
        """
        Get latest version from appropriate source.
        source: "github", "library_manager", "board_package"
        """
        if source == "board_package":
            # Board package versions are fixed
            return None

        elif source == "library_manager":
            # Query Arduino Library Index directly
            return self.query_arduino_index_version(library_name)

        elif source == "github":
            # Load the Arduino Index to get GitHub repo URL
            index = self._load_arduino_index()
            lib_info = index.get(f"{library_name}.h") or index.get(library_name)

            if not lib_info:
                return None

            repo = lib_info.get("github", "").replace("https://github.com/", "")
            if repo:
                return self.query_github_latest_version(repo)
            return None

        return None

    def _remove_incomplete_libraries(self) -> List[str]:
        """
        Remove incomplete/empty libraries from /libraries folder.
        Returns: list of removed library names
        """
        if not os.path.exists(self.libraries_dir):
            return []

        removed = []
        try:
            for lib_folder in os.listdir(self.libraries_dir):
                lib_path = os.path.join(self.libraries_dir, lib_folder)

                if not os.path.isdir(lib_path):
                    continue

                # Check if src folder exists and has content
                is_incomplete = False
                src_path = os.path.join(lib_path, "src")

                if os.path.exists(src_path):
                    src_files = [f for f in os.listdir(src_path) if f.endswith(('.h', '.cpp', '.c'))]
                    if not src_files:
                        is_incomplete = True
                else:
                    # Check for direct .h/.cpp files in root
                    root_files = [f for f in os.listdir(lib_path) if f.endswith(('.h', '.cpp', '.c'))]
                    if not root_files:
                        is_incomplete = True

                if is_incomplete:
                    # Remove the incomplete library folder
                    try:
                        shutil.rmtree(lib_path)
                        removed.append(lib_folder)
                        print_color(f"  🗑️  Removed incomplete library: {lib_folder}", "yellow")
                    except Exception as e:
                        print_color(f"  ⚠️  Failed to remove {lib_folder}: {e}", "yellow")

        except Exception as e:
            print_color(f"⚠️  Error scanning libraries: {e}", "yellow")

        return removed

    def _install_library_via_arduino_cli(self, lib_name: str, version: str = None) -> bool:
        """
        Install a library using arduino-cli lib install.
        Returns: True if successful
        """
        try:
            # Build the library specification
            if version and version != "unknown":
                lib_spec = f"{lib_name}@{version}"
            else:
                lib_spec = lib_name

            cmd = ["arduino-cli", "lib", "install", lib_spec]

            print_color(f"    Installing {lib_name}...", "blue")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                print_color(f"    ✅ {lib_name} installed", "green")
                return True
            else:
                # Try to extract meaningful error message
                error_msg = result.stderr.strip()
                if "not found" in error_msg.lower():
                    print_color(f"    ℹ️  {lib_name} already installed or not available", "blue")
                    return True  # Don't fail if already installed
                else:
                    print_color(f"    ⚠️  {lib_name}: {error_msg[:80]}", "yellow")
                    return False
        except Exception as e:
            print_color(f"    ⚠️  {lib_name}: {str(e)[:80]}", "yellow")
            return False

    def sync_from_ino(self, ino_file: str) -> Tuple[bool, List[Dict]]:
        """
        Auto-discover libraries from .ino and src/ files, remove incomplete ones, and install complete versions.
        Returns: (success, list_of_libraries)
        """
        print_color("\n🔍 Scanning project for library dependencies...", "bold")

        # Step 1: Remove incomplete libraries
        print_color("\n🧹 Removing incomplete/skeleton libraries...", "bold")
        removed = self._remove_incomplete_libraries()
        if removed:
            print_color(f"  ✅ Removed {len(removed)} incomplete libraries\n", "green")

        # Step 2: Parse includes
        includes = self.parse_includes_from_ino(ino_file)
        if not includes:
            print_color("⚠️  No #include directives found", "yellow")
            return False, []

        print_color(f"📋 Found {len(includes)} includes", "blue")

        # Step 3: Map to libraries
        libraries = []
        libs_to_install = []

        for include in includes:
            # Skip project-local headers (src/*, lib/*, etc.)
            if include.startswith(("src/", "lib/", "libraries/", "../")):
                continue  # These are project files, not external libraries

            lib_info = self.map_include_to_library(include)

            if lib_info:
                lib_name = lib_info.get("library")
                source = lib_info.get("source", "unknown")

                print_color(f"  ✓ {include:30} → {lib_name:25} ({source})", "blue")

                # Skip core libraries (included with board)
                if source == "board_package":
                    libraries.append({
                        "name": lib_name,
                        "version": lib_info.get("version", "3.3.3"),
                        "source": source,
                        "skip_download": True,
                        "reason": "Included with board package",
                    })
                else:
                    # Try to get installed version first, fallback to latest
                    version = self.get_installed_version(lib_name)
                    if not version:
                        version = self.get_latest_version(lib_name, source)

                    if version:
                        libraries.append({
                            "name": lib_name,
                            "version": version,
                            "source": source,
                            "url": lib_info.get("github", lib_info.get("url")),
                        })

                        # Check if library is already installed
                        installed_version = self.get_installed_version(lib_name)
                        if installed_version:
                            print_color(f"    → Installed: {installed_version}", "green")
                        else:
                            libs_to_install.append((lib_name, version))
                            print_color(f"    → Will install: {version}", "yellow")
                    else:
                        print_color(f"    ⚠️  Could not determine version", "yellow")
                        libraries.append({
                            "name": lib_name,
                            "version": "unknown",
                            "source": source,
                            "url": lib_info.get("github", lib_info.get("url")),
                        })
                        libs_to_install.append((lib_name, None))
            else:
                # Header not in Arduino Index → assume it's part of board package
                # or a custom project header
                lib_name = include.split("/")[0].replace(".h", "").replace("-", "_")

                libraries.append({
                    "name": lib_name,
                    "version": "board_package",
                    "source": "board_package",
                    "skip_download": True,
                    "reason": "System/board package library or custom header",
                    "header": include,
                })
                print_color(f"  ⓘ {include:30} → Assumed board_package (will be validated at compile)", "blue")

        # Step 4: Install libraries using arduino-cli
        if libs_to_install:
            print_color(f"\n📥 Installing {len(libs_to_install)} libraries...", "bold")
            installed_count = 0
            for lib_name, version in libs_to_install:
                if self._install_library_via_arduino_cli(lib_name, version):
                    installed_count += 1

            print_color(f"\n✅ Successfully installed {installed_count}/{len(libs_to_install)} libraries", "green")

        # Save to libraries.json
        success = self._write_libraries_json(libraries)

        print_color(
            f"\n✅ Library sync complete! " f"({len(removed)} removed, {len(libs_to_install)} installed/verified)",
            "green",
        )

        return success, libraries

    def check_updates(self, use_cache: bool = True) -> Dict[str, Dict]:
        """
        Check if updates are available for current libraries.
        Returns: {"LibraryName": {"current": "1.0", "latest": "1.1", "source": "github"}, ...}
        """
        print_color("\n🔄 Checking for library updates...", "bold")

        if not os.path.exists(self.libraries_json):
            print_color(f"❌ libraries.json not found", "red")
            return {}

        try:
            with open(self.libraries_json, "r") as f:
                data = json.load(f)
        except Exception as e:
            print_color(f"❌ Error reading libraries.json: {e}", "red")
            return {}

        updates = {}

        for lib in data.get("libraries", []):
            lib_name = lib.get("name")
            current_version = lib.get("version")
            source = lib.get("source")

            # Skip board package libraries
            if source == "board_package":
                print_color(f"  ℹ️  {lib_name:30} (core - not checked)", "yellow")
                continue

            print_color(f"  🔍 {lib_name:30}", "blue", end=" ")

            latest = self.get_latest_version(lib_name, source)

            if latest:
                if latest == current_version:
                    print_color(f"✓ {current_version} (latest)", "green")
                elif self._version_is_newer(latest, current_version):
                    print_color(f"⚠️  {current_version} → {latest} available", "yellow")
                    updates[lib_name] = {
                        "current": current_version,
                        "latest": latest,
                        "source": source,
                    }
                else:
                    print_color(f"✓ {current_version} (newer)", "green")
            else:
                print_color(f"⚠️  Could not check", "yellow")

        if updates:
            print_color(f"\n📊 {len(updates)} update(s) available", "yellow")
        else:
            print_color(f"\n✅ All libraries are up to date", "green")

        return updates

    def update_libraries(self, specific: List[str] = None) -> Tuple[bool, List[str]]:
        """
        Update libraries to latest versions.
        specific: list of library names to update, or None for all
        """
        # Check for updates (no cache)
        updates = self.check_updates(use_cache=False)

        if not updates:
            print_color("ℹ️  No updates available", "blue")
            return True, []

        # Determine which to update
        to_update = specific if specific else list(updates.keys())

        print_color(f"\n📥 Updating {len(to_update)} library/libraries...", "bold")

        updated = []
        for lib_name in to_update:
            if lib_name not in updates:
                continue

            new_version = updates[lib_name]["latest"]
            source = updates[lib_name]["source"]

            print_color(f"  📦 {lib_name} → {new_version}...", "blue")

            # Download new version
            if self._download_library(lib_name, new_version, source):
                # Update libraries.json
                if self._update_library_version(lib_name, new_version):
                    print_color(f"  ✅ {lib_name} updated to {new_version}", "green")
                    updated.append(lib_name)
                else:
                    print_color(f"  ❌ Failed to update {lib_name} in libraries.json", "red")
            else:
                print_color(f"  ❌ Failed to download {lib_name}", "red")

        return len(updated) == len(to_update), updated

    def _download_library(self, lib_name: str, version: str, source: str) -> bool:
        """Download library from source."""
        # Get library info from Arduino Index
        index = self._load_arduino_index()
        lib_info = index.get(f"{lib_name}.h") or index.get(lib_name) or {}
        url = lib_info.get("github") or lib_info.get("url")

        if not url or source != "library_manager":
            print_color(f"    ⚠️  No GitHub URL for {lib_name}", "yellow")
            return False

        lib_path = os.path.join(self.libraries_dir, lib_name)

        # Remove old version
        if os.path.exists(lib_path):
            import shutil

            shutil.rmtree(lib_path)

        # Clone new version
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", url, lib_path],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return True
            else:
                print_color(f"    Git error: {result.stderr[:100]}", "yellow")
                return False

        except Exception as e:
            print_color(f"    Error: {e}", "red")
            return False

    def _update_library_version(self, lib_name: str, new_version: str) -> bool:
        """Update version in libraries.json."""
        try:
            with open(self.libraries_json, "r") as f:
                data = json.load(f)

            for lib in data.get("libraries", []):
                if lib.get("name") == lib_name:
                    lib["version"] = new_version
                    break

            with open(self.libraries_json, "w") as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print_color(f"Error updating libraries.json: {e}", "red")
            return False

    def _write_libraries_json(self, libraries: List[Dict]) -> bool:
        """Write libraries.json file."""
        try:
            # Get project name from sketch folder
            project_name = os.path.basename(self.sketch_folder) or "Arduino Project"

            data = {
                "project": project_name,
                "sync_date": datetime.now().isoformat(),
                "libraries": libraries,
            }

            os.makedirs(os.path.dirname(self.libraries_json), exist_ok=True)
            with open(self.libraries_json, "w") as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print_color(f"❌ Error writing libraries.json: {e}", "red")
            return False

    @staticmethod
    def _version_is_newer(latest: str, current: str) -> bool:
        """Compare two version strings. Returns True if latest > current."""
        try:
            latest_parts = [int(x) for x in latest.split(".")]
            current_parts = [int(x) for x in current.split(".")]

            # Pad with zeros
            max_len = max(len(latest_parts), len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))

            return latest_parts > current_parts
        except (ValueError, AttributeError):
            # If can't parse, compare as strings
            return latest > current
