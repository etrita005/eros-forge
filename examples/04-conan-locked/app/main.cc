#include "conan_math/answer.h"

#include <iostream>

int main() {
  const int result = conan_math::transform(20);
  std::cout << "result=" << result << '\n';
  return result == 41 ? 0 : 1;
}
