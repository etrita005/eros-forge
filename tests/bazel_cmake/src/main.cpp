#include <iostream>
#include "lib/math_utils.h"

int main() {
    std::cout << "Hello from EROS Forge Bazel + CMake Test!" << std::endl;
    
    int64_t sum = eros_test::calculate_sum(1, 10);
    std::cout << "Sum from 1 to 10: " << sum << std::endl;
    
    std::string greeting = eros_test::get_greeting("EROS");
    std::cout << greeting << std::endl;
    
    int fib = eros_test::fibonacci(10);
    std::cout << "Fibonacci(10): " << fib << std::endl;
    
    std::cout << "CMake integration test passed!" << std::endl;
    
    return 0;
}
