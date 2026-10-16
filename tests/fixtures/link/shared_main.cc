#include <iostream>
extern "C" int forge_shared_value();
int main() {
  const int value = forge_shared_value();
  std::cout << "forge-pic=" << value << '\n';
  return value == 41 ? 0 : 1;
}
