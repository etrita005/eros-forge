#!/bin/bash
# Run linux_arm64 configuration tests for all test projects

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(dirname "$SCRIPT_DIR")"

CONFIG="linux_arm64"

echo "========================================="
echo "Running $CONFIG configuration tests for all projects"
echo "========================================="
echo ""

# List of test projects
TEST_PROJECTS=(
    "bazel_simple"
    "bazel_cmake"
    "bazel_cmake_conan"
)

TOTAL_PASSED=0
TOTAL_FAILED=0

for project in "${TEST_PROJECTS[@]}"; do
    echo ""
    echo "========================================="
    echo "Testing project: $project"
    echo "Configuration: $CONFIG"
    echo "========================================="
    
    cd "$TESTS_DIR/$project"
    
    if [ -f "test_configs/test_platform_configs.sh" ]; then
        if bash test_configs/test_platform_configs.sh "$CONFIG"; then
            echo "✓ $project test passed"
            TOTAL_PASSED=$((TOTAL_PASSED + 1))
        else
            echo "✗ $project test failed"
            TOTAL_FAILED=$((TOTAL_FAILED + 1))
        fi
    else
        echo "⚠ Test script not found: $project/test_configs/test_platform_configs.sh"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    fi
    
    echo ""
done

echo "========================================="
echo "Test Summary"
echo "========================================="
echo "Passed: $TOTAL_PASSED"
echo "Failed: $TOTAL_FAILED"
echo "Total: $((TOTAL_PASSED + TOTAL_FAILED))"
echo ""

if [ $TOTAL_FAILED -eq 0 ]; then
    echo "✓ All tests passed!"
    exit 0
else
    echo "✗ Some tests failed"
    exit 1
fi
