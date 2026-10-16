#include <cstring>
#include <iostream>

extern "C" __attribute__((noinline)) int forge_native_debug(int value) {
  volatile int source_line_marker = value + 11;
  return source_line_marker;
}

extern "C" __attribute__((noinline)) void forge_native_crash() {
  volatile int* pointer = nullptr;
  *pointer = forge_native_debug(31);
}

int main(int argc, char** argv) {
  if (argc > 1 && std::strcmp(argv[1], "--crash") == 0) forge_native_crash();
  const int result = forge_native_debug(31);
  std::cout << "F-DEBUG native=" << result << '\n';
  return result == 42 ? 0 : 1;
}
