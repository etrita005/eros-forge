#include <iostream>

extern "C" int forge_private_version();
int main() {
  const int version = forge_private_version();
  std::cout << "F-VERSIONS version=" << version << '\n';
  return version == EXPECTED_VERSION ? 0 : 1;
}
