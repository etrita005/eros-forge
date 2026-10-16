#include "foo.h"
#include <iostream>
int main() {
  const int value = forge_foo(20);
  std::cout << "forge-link=" << value << '\n';
  return value == FORGE_PUBLIC_EXPECTED ? 0 : 1;
}
