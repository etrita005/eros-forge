#include <iostream>

int main() {
  const int result = 20 * 2 + 1;
  std::cout << "result=" << result << '\n';
  return result == 41 ? 0 : 1;
}
