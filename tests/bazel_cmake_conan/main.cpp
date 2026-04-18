#include <iostream>
#include <fmt/core.h>
#include "mylib.h"

int main() {
    std::string message = "Hello from EROS Forge Bazel + CMake + Conan Test!";
    fmt::print("{}\n", message);
    
    int64_t sum = eros_test::calculate_sum(1, 10);
    fmt::print("Sum from 1 to 10: {}\n", sum);
    
    std::string greeting = eros_test::get_greeting("EROS");
    fmt::print("{}\n", greeting);
    
    int fib = eros_test::fibonacci(10);
    fmt::print("Fibonacci(10): {}\n", fib);
    
    fmt::print("CMake + Conan integration test passed!\n");
    
    return 0;
}
