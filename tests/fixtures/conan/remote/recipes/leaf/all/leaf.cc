#include "leaf.h"
extern "C" __attribute__((noinline)) int forge_leaf_value(int input) {
  return input * 2;
}
