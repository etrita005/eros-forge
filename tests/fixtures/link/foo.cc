#include "foo.h"
#include "forge_dependency.h"
extern "C" __attribute__((noinline)) int forge_foo(int input) {
  return forge_dependency_value(input) - 2;
}
