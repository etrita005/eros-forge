#include <iostream>

extern "C" __attribute__((noinline)) int forge_release_symbol(int value) {
  volatile int offset = 1;
  return value * 2 + offset;
}

int main() {
  const int result = forge_release_symbol(20);
  std::cout << "result=" << result << '\n';
  return result == 41 ? 0 : 1;
}
