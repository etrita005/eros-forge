#include <iostream>
#include <string_view>

#ifdef FORGE_QUOTED_TEXT
static_assert(std::string_view(FORGE_QUOTED_TEXT) == "hello world");
#endif

__attribute__((noinline)) int forge_basic_value(int input) { return input * 2 + 1; }

int main() {
  const int result = forge_basic_value(20);
  std::cout << "forge-basic=" << result << '\n';
  return result == 41 ? 0 : 1;
}
