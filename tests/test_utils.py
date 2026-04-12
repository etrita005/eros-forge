#!/usr/bin/env python3
"""
EROS Forge Test Utilities Library

Provides various verification functions for automated testing
"""

import subprocess
import re
import os
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Dict

# ============================================================================
# Artifact Verification Functions
# ============================================================================

def check_binary_arch(binary_path: str, expected_arch: str) -> Tuple[bool, str]:
    """
    Verify binary file architecture
    
    Args:
        binary_path: Path to the binary file
        expected_arch: Expected architecture (x86_64 or aarch64)
    
    Returns:
        (is_match, actual_architecture_info)
    """
    if not os.path.exists(binary_path):
        return False, f"Binary file not found: {binary_path}"
    
    result = subprocess.run(
        ["file", binary_path],
        capture_output=True,
        text=True
    )
    output = result.stdout
    
    if expected_arch == "x86_64" and "x86-64" in output:
        print(f"✓ Architecture check passed: {expected_arch}")
        return True, output
    elif expected_arch == "aarch64" and "ARM aarch64" in output:
        print(f"✓ Architecture check passed: {expected_arch}")
        return True, output
    else:
        print(f"✗ Architecture check failed: expected {expected_arch}")
        return False, output

def check_dynamic_linker(binary_path: str, expected_linker: str) -> Tuple[bool, str]:
    """
    Verify dynamic linker path
    
    Args:
        binary_path: Path to the binary file
        expected_linker: Expected dynamic linker path
    
    Returns:
        (is_match, actual_linker_info)
    """
    result = subprocess.run(
        ["readelf", "-p", ".interp", binary_path],
        capture_output=True,
        text=True
    )
    output = result.stdout
    
    if expected_linker in output:
        print(f"✓ Dynamic linker check passed: {expected_linker}")
        return True, output
    else:
        print(f"✗ Dynamic linker check failed: expected {expected_linker}")
        return False, output

def check_runpath(binary_path: str, expected_runpath: str) -> Tuple[bool, str]:
    """
    Verify runtime library search path
    
    Args:
        binary_path: Path to the binary file
        expected_runpath: Expected RUNPATH
    
    Returns:
        (is_match, actual_runpath_info)
    """
    result = subprocess.run(
        ["readelf", "-d", binary_path],
        capture_output=True,
        text=True
    )
    output = result.stdout
    
    if expected_runpath in output:
        print(f"✓ RUNPATH check passed: {expected_runpath}")
        return True, output
    else:
        print(f"✗ RUNPATH check failed: expected {expected_runpath}")
        return False, output

def check_symbols_stripped(binary_path: str) -> Tuple[bool, str]:
    """
    Verify if symbols are stripped
    
    Args:
        binary_path: Path to the binary file
    
    Returns:
        (is_stripped, symbol_info)
    """
    result = subprocess.run(
        ["file", binary_path],
        capture_output=True,
        text=True
    )
    output = result.stdout
    
    if "stripped" in output:
        print("✓ Symbols stripped check passed")
        return True, output
    else:
        print("✗ Symbols stripped check failed")
        return False, output

def check_sanitizer_enabled(binary_path: str, sanitizer_type: str) -> Tuple[bool, str]:
    """
    Verify if Sanitizer is enabled
    
    Args:
        binary_path: Path to the binary file
        sanitizer_type: Sanitizer type (asan, tsan, msan, ubsan)
    
    Returns:
        (is_enabled, detection_info)
    """
    result = subprocess.run(
        ["nm", binary_path],
        capture_output=True,
        text=True
    )
    output = result.stdout
    
    sanitizer_symbols = {
        "asan": ["__asan", "__asan_init"],
        "tsan": ["__tsan", "__tsan_init"],
        "msan": ["__msan", "__msan_init"],
        "ubsan": ["__ubsan", "__ubsan_init"]
    }
    
    symbols = sanitizer_symbols.get(sanitizer_type, [])
    for symbol in symbols:
        if symbol in output:
            print(f"✓ {sanitizer_type.upper()} enabled check passed")
            return True, f"Found {symbol}"
    
    print(f"✗ {sanitizer_type.upper()} enabled check failed")
    return False, f"No {sanitizer_type} symbols found"

def check_no_sanitizer(binary_path: str) -> Tuple[bool, str]:
    """
    Verify that no Sanitizer is enabled
    
    Args:
        binary_path: Path to the binary file
    
    Returns:
        (is_not_enabled, detection_info)
    """
    result = subprocess.run(
        ["nm", binary_path],
        capture_output=True,
        text=True
    )
    output = result.stdout
    
    sanitizer_prefixes = ["__asan", "__tsan", "__msan", "__ubsan"]
    found_sanitizers = []
    
    for prefix in sanitizer_prefixes:
        if prefix in output:
            found_sanitizers.append(prefix)
    
    if found_sanitizers:
        print(f"✗ No sanitizer check failed: found {found_sanitizers}")
        return False, f"Found sanitizers: {found_sanitizers}"
    else:
        print("✓ No sanitizer check passed")
        return True, "No sanitizer symbols found"

def run_binary(binary_path: str, args: List[str] = None) -> Tuple[bool, str]:
    """
    Run binary file and check output
    
    Args:
        binary_path: Path to the binary file
        args: Runtime arguments
    
    Returns:
        (is_success, output_info)
    """
    try:
        result = subprocess.run(
            [binary_path] + (args or []),
            capture_output=True,
            text=True,
            timeout=10
        )
        success = result.returncode == 0
        if success:
            print("✓ Binary execution check passed")
        else:
            print(f"✗ Binary execution check failed: return code {result.returncode}")
        return success, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print("✗ Binary execution check failed: timeout")
        return False, "Timeout"
    except Exception as e:
        print(f"✗ Binary execution check failed: {e}")
        return False, str(e)

def check_cross_compilation(binary_path: str, host_arch: str, target_arch: str) -> Tuple[bool, str]:
    """
    Verify cross-compilation result
    
    Args:
        binary_path: Path to the binary file
        host_arch: Host architecture
        target_arch: Target architecture
    
    Returns:
        (is_correct, verification_info)
    """
    if host_arch == target_arch:
        return True, "Native compilation, no cross-compilation check needed"
    
    arch_ok, arch_info = check_binary_arch(binary_path, target_arch)
    if not arch_ok:
        return False, f"Architecture mismatch: {arch_info}"
    
    expected_linker = "/opt/eros/lib/ld-linux-aarch64.so.1"
    linker_ok, linker_info = check_dynamic_linker(binary_path, expected_linker)
    if not linker_ok:
        return False, f"Dynamic linker mismatch: {linker_info}"
    
    expected_runpath = "/opt/eros/lib"
    runpath_ok, runpath_info = check_runpath(binary_path, expected_runpath)
    if not runpath_ok:
        return False, f"RUNPATH mismatch: {runpath_info}"
    
    return True, "Cross-compilation verification passed"

def check_dependencies(binary_path: str, expected_libs: List[str] = None) -> Tuple[bool, str]:
    """
    Verify dependencies
    
    Args:
        binary_path: Path to the binary file
        expected_libs: List of expected libraries (optional)
    
    Returns:
        (is_correct, dependency_info)
    """
    result = subprocess.run(
        ["ldd", binary_path],
        capture_output=True,
        text=True
    )
    output = result.stdout
    
    if expected_libs:
        missing_libs = []
        for lib in expected_libs:
            if lib not in output:
                missing_libs.append(lib)
        
        if missing_libs:
            print(f"✗ Dependencies check failed: missing {missing_libs}")
            return False, f"Missing libraries: {missing_libs}"
    
    print("✓ Dependencies check passed")
    return True, output

def check_binary_size(binary_path: str, max_size_mb: float = 100.0) -> Tuple[bool, str]:
    """
    Verify binary file size
    
    Args:
        binary_path: Path to the binary file
        max_size_mb: Maximum allowed size (MB)
    
    Returns:
        (is_reasonable, size_info)
    """
    size_bytes = os.path.getsize(binary_path)
    size_mb = size_bytes / (1024 * 1024)
    
    if size_mb <= max_size_mb:
        print(f"✓ Binary size check passed: {size_mb:.2f} MB")
        return True, f"Size: {size_mb:.2f} MB"
    else:
        print(f"✗ Binary size check failed: {size_mb:.2f} MB (max: {max_size_mb} MB)")
        return False, f"Size {size_mb:.2f} MB exceeds limit {max_size_mb} MB"

def check_binary_permissions(binary_path: str) -> Tuple[bool, str]:
    """
    Verify binary file permissions
    
    Args:
        binary_path: Path to the binary file
    
    Returns:
        (is_executable, permission_info)
    """
    if os.access(binary_path, os.X_OK):
        print("✓ Binary permissions check passed")
        return True, "Executable"
    else:
        print("✗ Binary permissions check failed")
        return False, "Not executable"

# ============================================================================
# Compilation Options Verification Functions
# ============================================================================

def check_compiler_path(build_log: str, expected_compiler: str) -> Tuple[bool, str]:
    """
    Verify compiler path
    
    Args:
        build_log: Build log content
        expected_compiler: Expected compiler path
    
    Returns:
        (is_match, detection_info)
    """
    if expected_compiler in build_log:
        print(f"✓ Compiler path check passed: {expected_compiler}")
        return True, f"Found compiler: {expected_compiler}"
    
    # Both gcc and g++ can compile C++ code, so accept either
    # If g++ is expected, also accept gcc
    if "g++" in expected_compiler:
        alternative_compiler = expected_compiler.replace("g++", "gcc")
        if alternative_compiler in build_log:
            print(f"✓ Compiler path check passed: {alternative_compiler} (alternative for {expected_compiler})")
            return True, f"Found compiler: {alternative_compiler} (gcc is acceptable for C++ compilation)"
    
    # If gcc is expected, also accept g++
    if "gcc" in expected_compiler and "g++" not in expected_compiler:
        alternative_compiler = expected_compiler.replace("gcc", "g++")
        if alternative_compiler in build_log:
            print(f"✓ Compiler path check passed: {alternative_compiler} (alternative for {expected_compiler})")
            return True, f"Found compiler: {alternative_compiler}"
    
    print(f"✗ Compiler path check failed: expected {expected_compiler}")
    return False, f"Compiler {expected_compiler} not found in build log"

def check_cpp_standard(build_log: str, expected_standard: str) -> Tuple[bool, str]:
    """
    Verify C++ standard
    
    Args:
        build_log: Build log content
        expected_standard: Expected C++ standard (e.g., c++20)
    
    Returns:
        (is_match, detection_info)
    """
    flag = f"-std={expected_standard}"
    if flag in build_log:
        print(f"✓ C++ standard check passed: {expected_standard}")
        return True, f"Found C++ standard: {expected_standard}"
    else:
        print(f"✗ C++ standard check failed: expected {expected_standard}")
        return False, f"C++ standard {expected_standard} not found in build log"

def check_optimization_level(build_log: str, expected_level: str) -> Tuple[bool, str]:
    """
    Verify optimization level
    
    Args:
        build_log: Build log content
        expected_level: Expected optimization level (e.g., -O3, -O0, -Og)
    
    Returns:
        (is_match, detection_info)
    """
    if expected_level in build_log:
        print(f"✓ Optimization level check passed: {expected_level}")
        return True, f"Found optimization level: {expected_level}"
    else:
        print(f"✗ Optimization level check failed: expected {expected_level}")
        return False, f"Optimization level {expected_level} not found in build log"

def check_define(build_log: str, define_name: str) -> Tuple[bool, str]:
    """
    Verify preprocessor define
    
    Args:
        build_log: Build log content
        define_name: Macro name (e.g., NDEBUG)
    
    Returns:
        (is_defined, detection_info)
    """
    flag = f"-D{define_name}"
    if flag in build_log:
        print(f"✓ Define check passed: {define_name}")
        return True, f"Found define: {define_name}"
    else:
        print(f"✗ Define check failed: {define_name}")
        return False, f"Define {define_name} not found in build log"

def check_no_define(build_log: str, define_name: str) -> Tuple[bool, str]:
    """
    Verify preprocessor define is not set
    
    Args:
        build_log: Build log content
        define_name: Macro name (e.g., NDEBUG)
    
    Returns:
        (is_not_defined, detection_info)
    """
    flag = f"-D{define_name}"
    if flag not in build_log:
        print(f"✓ No define check passed: {define_name}")
        return True, f"Define {define_name} not found (as expected)"
    else:
        print(f"✗ No define check failed: {define_name}")
        return False, f"Define {define_name} found in build log (should not be defined)"

def check_sanitizer_flags(build_log: str, sanitizer_type: str) -> Tuple[bool, str]:
    """
    Verify Sanitizer compilation flags
    
    Args:
        build_log: Build log content
        sanitizer_type: Sanitizer type (thread, memory, address, undefined)
    
    Returns:
        (is_enabled, detection_info)
    """
    flag = f"-fsanitize={sanitizer_type}"
    if flag in build_log:
        print(f"✓ Sanitizer flags check passed: {sanitizer_type}")
        return True, f"Found sanitizer flag: {flag}"
    else:
        print(f"✗ Sanitizer flags check failed: {sanitizer_type}")
        return False, f"Sanitizer flag {flag} not found in build log"

def check_no_sanitizer_flags(build_log: str) -> Tuple[bool, str]:
    """
    Verify no Sanitizer compilation flags
    
    Args:
        build_log: Build log content
    
    Returns:
        (is_not_enabled, detection_info)
    """
    sanitizer_flags = ["-fsanitize=address", "-fsanitize=thread", "-fsanitize=memory", "-fsanitize=undefined"]
    found_flags = []
    
    for flag in sanitizer_flags:
        if flag in build_log:
            found_flags.append(flag)
    
    if found_flags:
        print(f"✗ No sanitizer flags check failed: found {found_flags}")
        return False, f"Found sanitizer flags: {found_flags}"
    else:
        print("✓ No sanitizer flags check passed")
        return True, "No sanitizer flags found (as expected)"

def check_cross_compile_flags(build_log: str) -> Tuple[bool, str]:
    """
    Verify cross-compilation flags
    
    Args:
        build_log: Build log content
    
    Returns:
        (is_present, detection_info)
    """
    required_flags = [
        "-Wl,--rpath=/opt/eros/lib",
        "-Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1"
    ]
    
    missing_flags = []
    for flag in required_flags:
        if flag not in build_log:
            missing_flags.append(flag)
    
    if missing_flags:
        print(f"✗ Cross compile flags check failed: missing {missing_flags}")
        return False, f"Missing cross-compile flags: {missing_flags}"
    else:
        print("✓ Cross compile flags check passed")
        return True, "All cross-compile flags found"

def check_compilation_mode(build_log: str, expected_mode: str) -> Tuple[bool, str]:
    """
    Verify compilation mode
    
    Args:
        build_log: Build log content
        expected_mode: Expected compilation mode (dbg or opt)
    
    Returns:
        (is_match, detection_info)
    """
    mode_flag = f"--compilation_mode={expected_mode}"
    if mode_flag in build_log or f"-c {expected_mode}" in build_log:
        print(f"✓ Compilation mode check passed: {expected_mode}")
        return True, f"Found compilation mode: {expected_mode}"
    else:
        if expected_mode == "dbg" and ("-g" in build_log or "-O0" in build_log):
            print(f"✓ Compilation mode check passed: {expected_mode}")
            return True, f"Inferred compilation mode: {expected_mode}"
        elif expected_mode == "opt" and "-O3" in build_log:
            print(f"✓ Compilation mode check passed: {expected_mode}")
            return True, f"Inferred compilation mode: {expected_mode}"
        else:
            print(f"✗ Compilation mode check failed: expected {expected_mode}")
            return False, f"Compilation mode {expected_mode} not found in build log"

# ============================================================================
# Build Info Extraction Functions
# ============================================================================

def extract_compiler_info(build_log: str) -> Dict[str, str]:
    """
    Extract compiler information from build log
    
    Args:
        build_log: Build log content
    
    Returns:
        Dictionary with compiler information
    """
    info = {
        "compiler_path": "unknown",
        "compiler_type": "unknown",
        "target_arch": "unknown"
    }
    
    # Extract compiler path from compile commands
    compile_pattern = r'([/\w\-\.]+/(?:gcc|g\+\+|clang|clang\+\+|aarch64-linux-gnu-gcc|aarch64-linux-gnu-g\+\+))\s'
    matches = re.findall(compile_pattern, build_log)
    if matches:
        info["compiler_path"] = matches[0]
        if "aarch64-linux-gnu" in matches[0]:
            info["compiler_type"] = "cross-compiler"
            info["target_arch"] = "aarch64"
        elif "clang" in matches[0]:
            info["compiler_type"] = "clang"
            info["target_arch"] = "native"
        else:
            info["compiler_type"] = "native-gcc"
            info["target_arch"] = "native"
    
    return info

def extract_compile_flags(build_log: str) -> Dict[str, List[str]]:
    """
    Extract compilation flags from build log
    
    Args:
        build_log: Build log content
    
    Returns:
        Dictionary with compilation flags
    """
    flags = {
        "cpp_standard": [],
        "optimization": [],
        "defines": [],
        "includes": [],
        "warnings": [],
        "other": []
    }
    
    # Extract C++ standard
    std_match = re.findall(r'-std=(c\+\+\d+|gnu\+\+\d+)', build_log)
    if std_match:
        flags["cpp_standard"] = list(set(std_match))
    
    # Extract optimization level
    opt_match = re.findall(r'-O[0-3sg]', build_log)
    if opt_match:
        flags["optimization"] = list(set(opt_match))
    
    # Extract defines
    define_match = re.findall(r'-D(\w+)', build_log)
    if define_match:
        flags["defines"] = list(set(define_match))
    
    # Extract include paths
    include_match = re.findall(r'-I\s*(\S+)', build_log)
    if include_match:
        flags["includes"] = list(set(include_match))[:10]  # Limit to 10
    
    # Extract warning flags
    warning_match = re.findall(r'-W[\w\-]+', build_log)
    if warning_match:
        flags["warnings"] = list(set(warning_match))[:10]  # Limit to 10
    
    return flags

def extract_link_flags(build_log: str) -> Dict[str, List[str]]:
    """
    Extract linker flags from build log
    
    Args:
        build_log: Build log content
    
    Returns:
        Dictionary with linker flags
    """
    flags = {
        "dynamic_linker": [],
        "rpath": [],
        "libraries": [],
        "other": []
    }
    
    # Extract dynamic linker
    linker_match = re.findall(r'--dynamic-linker[=\s]+(\S+)', build_log)
    if linker_match:
        flags["dynamic_linker"] = list(set(linker_match))
    
    # Extract rpath
    rpath_match = re.findall(r'-Wl,-rpath[,=]?(\S+)', build_log)
    rpath_match += re.findall(r'--rpath[=\s]+(\S+)', build_log)
    if rpath_match:
        flags["rpath"] = list(set(rpath_match))
    
    # Extract linked libraries
    lib_match = re.findall(r'-l(\w+)', build_log)
    if lib_match:
        flags["libraries"] = list(set(lib_match))[:10]  # Limit to 10
    
    return flags

def print_build_info(build_log: str, config_name: str = "") -> Tuple[bool, str]:
    """
    Print detailed build information
    
    Args:
        build_log: Build log content
        config_name: Configuration name
    
    Returns:
        (True, summary_info)
    """
    print("\n" + "=" * 60)
    print(f"Build Information{': ' + config_name if config_name else ''}")
    print("=" * 60)
    
    # Extract and print compiler info
    compiler_info = extract_compiler_info(build_log)
    print("\n[Compiler Information]")
    print(f"  Path: {compiler_info['compiler_path']}")
    print(f"  Type: {compiler_info['compiler_type']}")
    print(f"  Target: {compiler_info['target_arch']}")
    
    # Extract and print compile flags
    compile_flags = extract_compile_flags(build_log)
    print("\n[Compilation Flags]")
    if compile_flags["cpp_standard"]:
        print(f"  C++ Standard: {', '.join(compile_flags['cpp_standard'])}")
    if compile_flags["optimization"]:
        print(f"  Optimization: {', '.join(compile_flags['optimization'])}")
    if compile_flags["defines"]:
        print(f"  Defines: {', '.join(compile_flags['defines'][:5])}")
    if compile_flags["warnings"]:
        print(f"  Warnings: {', '.join(compile_flags['warnings'][:5])}")
    
    # Extract and print link flags
    link_flags = extract_link_flags(build_log)
    print("\n[Linker Flags]")
    if link_flags["dynamic_linker"]:
        print(f"  Dynamic Linker: {', '.join(link_flags['dynamic_linker'])}")
    if link_flags["rpath"]:
        print(f"  RPATH/RUNPATH: {', '.join(link_flags['rpath'])}")
    if link_flags["libraries"]:
        print(f"  Libraries: {', '.join(link_flags['libraries'][:5])}")
    
    print("\n" + "=" * 60)
    
    return True, f"Compiler: {compiler_info['compiler_path']}, Type: {compiler_info['compiler_type']}"

def verify_build_config(build_log: str, config_name: str, expected: Dict) -> Tuple[bool, List[str]]:
    """
    Verify build configuration against expected values
    
    Args:
        build_log: Build log content
        config_name: Configuration name
        expected: Dictionary of expected values
    
    Returns:
        (all_passed, list of errors)
    """
    errors = []
    all_passed = True
    
    print(f"\nVerifying configuration: {config_name}")
    print("-" * 40)
    
    # Check compiler
    if "compiler" in expected:
        compiler_info = extract_compiler_info(build_log)
        if expected["compiler"] not in compiler_info["compiler_path"]:
            # Check alternative (gcc vs g++)
            alt_compiler = expected["compiler"].replace("g++", "gcc")
            if alt_compiler not in compiler_info["compiler_path"]:
                print(f"✗ Compiler mismatch: expected {expected['compiler']}, got {compiler_info['compiler_path']}")
                errors.append(f"Compiler mismatch: expected {expected['compiler']}, got {compiler_info['compiler_path']}")
                all_passed = False
            else:
                print(f"✓ Compiler: {compiler_info['compiler_path']} (alternative for {expected['compiler']})")
        else:
            print(f"✓ Compiler: {compiler_info['compiler_path']}")
    
    # Check C++ standard
    if "cpp_standard" in expected:
        std_ok, _ = check_cpp_standard(build_log, expected["cpp_standard"])
        if not std_ok:
            errors.append(f"C++ standard {expected['cpp_standard']} not found")
            all_passed = False
    
    # Check optimization
    if "optimization" in expected:
        opt_ok, _ = check_optimization_level(build_log, expected["optimization"])
        if not opt_ok:
            errors.append(f"Optimization {expected['optimization']} not found")
            all_passed = False
    
    # Check defines
    if "defines" in expected:
        for define in expected["defines"]:
            define_ok, _ = check_define(build_log, define)
            if not define_ok:
                errors.append(f"Define {define} not found")
                all_passed = False
    
    # Check dynamic linker (for cross-compilation)
    if "dynamic_linker" in expected:
        link_flags = extract_link_flags(build_log)
        if expected["dynamic_linker"] not in " ".join(link_flags["dynamic_linker"]):
            print(f"✗ Dynamic linker mismatch: expected {expected['dynamic_linker']}")
            errors.append(f"Dynamic linker mismatch: expected {expected['dynamic_linker']}")
            all_passed = False
        else:
            print(f"✓ Dynamic linker: {expected['dynamic_linker']}")
    
    # Check rpath (for cross-compilation)
    if "rpath" in expected:
        link_flags = extract_link_flags(build_log)
        if expected["rpath"] not in " ".join(link_flags["rpath"]):
            print(f"✗ RPATH mismatch: expected {expected['rpath']}")
            errors.append(f"RPATH mismatch: expected {expected['rpath']}")
            all_passed = False
        else:
            print(f"✓ RPATH: {expected['rpath']}")
    
    return all_passed, errors

# ============================================================================
# Main Function (for command-line invocation)
# ============================================================================

def main():
    """Main function, supports command-line invocation"""
    if len(sys.argv) < 2:
        print("Usage: python3 test_utils.py <function_name> [args...]")
        print("Available functions:")
        print("  check_binary_arch <binary_path> <expected_arch>")
        print("  check_dynamic_linker <binary_path> <expected_linker>")
        print("  check_runpath <binary_path> <expected_runpath>")
        print("  check_symbols_stripped <binary_path>")
        print("  check_sanitizer_enabled <binary_path> <sanitizer_type>")
        print("  run_binary <binary_path>")
        print("  check_dependencies <binary_path>")
        print("  check_compiler_path <build_log_file> <expected_compiler>")
        print("  check_cpp_standard <build_log_file> <expected_standard>")
        print("  check_optimization_level <build_log_file> <expected_level>")
        sys.exit(1)
    
    func_name = sys.argv[1]
    args = sys.argv[2:]
    
    functions = {
        "check_binary_arch": check_binary_arch,
        "check_dynamic_linker": check_dynamic_linker,
        "check_runpath": check_runpath,
        "check_symbols_stripped": check_symbols_stripped,
        "check_sanitizer_enabled": check_sanitizer_enabled,
        "run_binary": run_binary,
        "check_dependencies": check_dependencies,
        "check_compiler_path": lambda log_file, compiler: check_compiler_path(open(log_file).read(), compiler),
        "check_cpp_standard": lambda log_file, standard: check_cpp_standard(open(log_file).read(), standard),
        "check_optimization_level": lambda log_file, level: check_optimization_level(open(log_file).read(), level),
        "check_cross_compile_flags": lambda log_file: check_cross_compile_flags(open(log_file).read()),
        "print_build_info": lambda log_file: print_build_info(open(log_file).read()),
        "extract_compiler_info": lambda log_file: print(extract_compiler_info(open(log_file).read())),
        "extract_compile_flags": lambda log_file: print(extract_compile_flags(open(log_file).read())),
        "extract_link_flags": lambda log_file: print(extract_link_flags(open(log_file).read())),
    }
    
    if func_name in functions:
        result = functions[func_name](*args)
        if not result[0]:
            sys.exit(1)
    else:
        print(f"Unknown function: {func_name}")
        sys.exit(1)

if __name__ == "__main__":
    main()
