#include "math_utils.h"
#include <algorithm>

namespace eros_test {

int64_t calculate_sum(int start, int end) {
    int64_t sum = 0;
    for (int i = start; i <= end; ++i) {
        sum += i;
    }
    return sum;
}

std::string get_greeting(const std::string& name) {
    return "Hello, " + name + "! Welcome to EROS Forge.";
}

int fibonacci(int n) {
    if (n <= 1) return n;
    int a = 0, b = 1;
    for (int i = 2; i <= n; ++i) {
        int temp = a + b;
        a = b;
        b = temp;
    }
    return b;
}

}
