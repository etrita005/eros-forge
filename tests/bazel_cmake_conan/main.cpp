#include <iostream>
#include <fmt/core.h>

int main() {
    std::string message = "Hello from EROS Forge Bazel + CMake + Conan Test!";
    fmt::print("{}\n", message);
    
    int result = 0;
    for (int i = 1; i <= 5; ++i) {
        result += i * i * i;
    }
    
    fmt::print("Sum of cubes 1³ to 5³: {}\n", result);
    fmt::print("CMake + Conan integration test passed!\n");
    
    return 0;
}
