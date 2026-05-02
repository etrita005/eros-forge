#include <iostream>
#include <thread>
#include <vector>
#include <atomic>
#include <memory>
#include "lib/math_utils.h"

int main() {
    std::cout << "Hello from EROS Forge Bazel Simple Test!" << std::endl;
    
    int64_t sum = eros_test::calculate_sum(1, 10);
    std::cout << "Sum of 1 to 10: " << sum << std::endl;
    
    std::string greeting = eros_test::get_greeting("EROS");
    std::cout << greeting << std::endl;
    
    int fib = eros_test::fibonacci(10);
    std::cout << "Fibonacci(10): " << fib << std::endl;
    
    std::atomic<int> counter{0};
    std::vector<std::thread> threads;
    
    for (int i = 0; i < 4; ++i) {
        threads.emplace_back([&counter]() {
            for (int j = 0; j < 1000; ++j) {
                counter.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }
    
    for (auto& t : threads) {
        t.join();
    }
    
    std::cout << "Thread counter: " << counter.load() << std::endl;
    
    auto ptr = std::make_unique<int>(42);
    std::cout << "Smart pointer value: " << *ptr << std::endl;
    
    std::cout << "All tests passed!" << std::endl;
    return 0;
}
