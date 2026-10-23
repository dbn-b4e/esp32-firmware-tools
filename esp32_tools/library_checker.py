#!/usr/bin/env python3
"""
Library Requirements Checker for Arduino Projects

Checks installed arduino-cli libraries against requirements specified in arduino_libraries.txt
"""

import os
import re
import subprocess
from typing import Dict, List, Tuple, Optional

# Colors for terminal output
COLORS = {
    "green": "\033[92m",
    "red": "\033[91m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def print_color(msg: str, color: str = "reset") -> None:
    """Print colored text to terminal."""
    print(f"{COLORS.get(color, '')}{msg}{COLORS['reset']}")


def parse_version(ver_str: str) -> Tuple[int, ...]:
    """
    Parse version string to tuple of integers for comparison.
    Examples: "1.2.3" -> (1, 2, 3), "3.4.9" -> (3, 4, 9)
    """
    try:
        return tuple(int(x) for x in ver_str.split('.'))
    except:
        # Fallback for malformed versions
        return (0,)


class LibraryRequirement:
    """Represents a library requirement with version constraint."""

    def __init__(self, name: str, operator: str, required_version: str):
        self.name = name
        self.operator = operator  # ==, >=, >, <=, <
        self.required_version = required_version

    def check(self, installed_version: Optional[str]) -> Tuple[bool, str]:
        """
        Check if installed version meets requirement.
        Returns: (passes, message)
        """
        if installed_version is None:
            return False, f"❌ {self.name} is NOT installed"

        try:
            installed = parse_version(installed_version)
            required = parse_version(self.required_version)

            if self.operator == "==":
                passes = installed == required
                symbol = "✅" if passes else "❌"
                return passes, f"{symbol} {self.name}: {installed_version} (required: =={self.required_version})"

            elif self.operator == ">=":
                passes = installed >= required
                symbol = "✅" if passes else "❌"
                return passes, f"{symbol} {self.name}: {installed_version} (required: >={self.required_version})"

            elif self.operator == ">":
                passes = installed > required
                symbol = "✅" if passes else "❌"
                return passes, f"{symbol} {self.name}: {installed_version} (required: >{self.required_version})"

            elif self.operator == "<=":
                passes = installed <= required
                symbol = "✅" if passes else "❌"
                return passes, f"{symbol} {self.name}: {installed_version} (required: <={self.required_version})"

            elif self.operator == "<":
                passes = installed < required
                symbol = "✅" if passes else "❌"
                return passes, f"{symbol} {self.name}: {installed_version} (required: <{self.required_version})"

            else:
                return False, f"❌ {self.name}: Unknown operator '{self.operator}'"

        except Exception as e:
            return False, f"❌ {self.name}: Error comparing versions: {e}"

    def __repr__(self):
        return f"LibraryRequirement({self.name} {self.operator} {self.required_version})"


def parse_requirements_file(filepath: str) -> List[LibraryRequirement]:
    """
    Parse arduino_libraries.txt file.
    Format:
      Library Name==1.2.3
      Library Name>=1.0.0
      # Comment lines ignored
    """
    requirements = []

    if not os.path.exists(filepath):
        print_color(f"⚠️  Requirements file not found: {filepath}", "yellow")
        return requirements

    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Parse requirement: "Library Name==1.2.3" or "Library Name>=1.0.0"
            match = re.match(r'^(.+?)(==|>=|>|<=|<)(.+)$', line)
            if match:
                name = match.group(1).strip()
                operator = match.group(2).strip()
                ver = match.group(3).strip()
                requirements.append(LibraryRequirement(name, operator, ver))
            else:
                print_color(f"⚠️  Line {line_num}: Invalid format: {line}", "yellow")

    return requirements


def get_core_libraries() -> Dict[str, str]:
    """
    Get ESP32 core libraries (WiFi, Preferences, LittleFS, etc.)
    These are bundled with the board package, not shown in arduino-cli lib list
    Returns: {"Library Name": "3.3.3", ...}
    """
    libraries = {}

    from .arduino import build_properties
    core_libs_dir = os.path.join(build_properties()['runtime.platform.path'], 'libraries')
    try:
        # Scan each library directory
        for lib_name in os.listdir(core_libs_dir):
            lib_dir = os.path.join(core_libs_dir, lib_name)
            if not os.path.isdir(lib_dir):
                continue

            # Read library.properties file
            props_file = os.path.join(lib_dir, "library.properties")
            if os.path.exists(props_file):
                with open(props_file, 'r') as f:
                    for line in f:
                        if line.startswith('version='):
                            version = line.split('=')[1].strip()
                            libraries[lib_name] = version
                            break

    except Exception as e:
        # Silently fail - core libraries are optional for checking
        pass

    return libraries


def get_installed_libraries() -> Dict[str, str]:
    """
    Get installed arduino-cli libraries (user + core libraries).
    Returns: {"Library Name": "1.2.3", ...}
    """
    try:
        result = subprocess.run(
            ["arduino-cli", "lib", "list"],
            capture_output=True,
            text=True,
            check=True
        )

        libraries = {}
        for line in result.stdout.splitlines():
            # Parse lines like: "Async TCP                 3.4.9    -         user     -"
            # Format: Name, Installed, Available, Location, Description
            parts = line.split()
            if len(parts) >= 2:
                # Library name might have spaces, version is next non-space token
                # Find the version (looks like x.y.z)
                for i, part in enumerate(parts):
                    if re.match(r'^\d+\.\d+', part):
                        # Everything before this is the library name
                        name = ' '.join(parts[:i])
                        version = part
                        libraries[name] = version
                        break

        # Add ESP32 core libraries (WiFi, Preferences, LittleFS, etc.)
        core_libs = get_core_libraries()
        libraries.update(core_libs)

        return libraries

    except subprocess.CalledProcessError as e:
        print_color(f"❌ Failed to get installed libraries: {e}", "red")
        # Still try to get core libraries even if arduino-cli fails
        return get_core_libraries()
    except FileNotFoundError:
        print_color(f"❌ arduino-cli not found. Please install it first.", "red")
        return get_core_libraries()


def check_requirements(requirements_file: str, verbose: bool = False) -> Tuple[bool, List[str], List[str]]:
    """
    Check if all requirements are satisfied.

    Returns:
        (all_satisfied, passed_checks, failed_checks)
    """
    requirements = parse_requirements_file(requirements_file)

    if not requirements:
        print_color("⚠️  No requirements found to check", "yellow")
        return True, [], []

    installed = get_installed_libraries()

    if verbose:
        print_color(f"\n📚 Found {len(installed)} installed libraries", "blue")
        print_color(f"📋 Checking {len(requirements)} requirements\n", "blue")

    passed = []
    failed = []

    for req in requirements:
        installed_version = installed.get(req.name)
        passes, message = req.check(installed_version)

        if passes:
            passed.append(message)
        else:
            failed.append(message)

        if verbose or not passes:
            print_color(message, "green" if passes else "red")

    return len(failed) == 0, passed, failed


def print_install_instructions(failed_requirements: List[str]) -> None:
    """Print installation instructions for failed requirements."""
    print_color("\n" + "="*60, "bold")
    print_color("📦 To fix missing/outdated libraries, run:", "yellow")
    print_color("="*60, "bold")
    print()

    # Parse failed requirements to extract library names
    for msg in failed_requirements:
        # Extract library name from message like "❌ Async TCP: ..."
        match = re.match(r'❌\s+(.+?):', msg)
        if match:
            lib_name = match.group(1).strip()
            # Try to extract required version
            version_match = re.search(r'required: [>=<]+(.+?)\)', msg)
            if version_match:
                req_version = version_match.group(1).strip()
                print(f'  arduino-cli lib install "{lib_name}@{req_version}"')
            else:
                print(f'  arduino-cli lib install "{lib_name}"')

    print()


def main():
    """CLI entry point for standalone usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Check Arduino library requirements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 library_checker.py                    # Check requirements
  python3 library_checker.py --verbose          # Verbose output
  python3 library_checker.py --file libs.txt    # Custom requirements file
"""
    )

    parser.add_argument(
        "--file",
        default="../config/arduino_libraries.txt",
        help="Path to requirements file (default: ../config/arduino_libraries.txt)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Make path relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    requirements_file = os.path.join(script_dir, args.file)

    print_color("\n" + "="*60, "bold")
    print_color("Arduino Library Requirements Check", "bold")
    print_color("="*60 + "\n", "bold")

    all_ok, passed, failed = check_requirements(requirements_file, verbose=args.verbose)

    if all_ok:
        print_color(f"\n✅ All {len(passed)} library requirements satisfied!", "green")
        return 0
    else:
        print_color(f"\n❌ {len(failed)} requirement(s) NOT satisfied", "red")
        print_install_instructions(failed)
        return 1


if __name__ == "__main__":
    exit(main())
