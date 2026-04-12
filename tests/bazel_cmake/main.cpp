#include <iostream>

int main() {
    std::cout << "Hello from EROS Forge Bazel + CMake Test!" << std::endl;
    
    int result = 0;
    for (int i = 1; i <= 5; ++i) {
        result += i * i;
    }
    
    std::cout << "Sum of squares 1² to 5²: " << result << std::endl;
    std::cout << "CMake integration test passed!" << std::endl;
    
    return 0;
}
