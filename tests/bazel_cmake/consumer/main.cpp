#include <iostream>
#include <cassert>
#include "lib/math_utils.h"

int main() {
    std::cout << "Consumer test: depending on bazel_cmake math_utils" << std::endl;

    int64_t sum = eros_test::calculate_sum(1, 10);
    assert(sum == 55);
    std::cout << "Sum of 1 to 10: " << sum << std::endl;

    std::string greeting = eros_test::get_greeting("EROS");
    assert(greeting == "Hello, EROS! Welcome to EROS Forge.");
    std::cout << greeting << std::endl;

    int fib = eros_test::fibonacci(10);
    assert(fib == 55);
    std::cout << "Fibonacci(10): " << fib << std::endl;

    std::cout << "Consumer dependency test passed!" << std::endl;
    return 0;
}
