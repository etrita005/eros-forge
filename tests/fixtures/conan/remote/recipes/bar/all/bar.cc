#include "forge_dependency.h"
#include "bar_config.h"
#include "leaf.h"
#include <atomic>
#include <mutex>
#include <thread>

static int forge_bar_patch_value = 1;

extern "C" __attribute__((noinline)) int forge_dependency_value(int input) {
  return forge_leaf_value(input) + forge_bar_patch_value + BAR_GENERATED_BIAS;
}

extern "C" __attribute__((noinline)) int forge_dependency_asan(int index) {
  volatile int* values = new int[1];
  values[0] = 7;
  const int result = values[index];
  delete[] values;
  return result;
}

extern "C" __attribute__((noinline)) int forge_dependency_ubsan(int input) {
  volatile int value = input;
  return value + 1;
}

extern "C" __attribute__((noinline)) int forge_dependency_race(int race) {
  int counter = 0;
  std::atomic<int> ready{0};
  std::mutex mutex;
  auto increment = [&] {
    ready.fetch_add(1);
    while (ready.load() != 2) std::this_thread::yield();
    for (int i = 0; i < 10000; ++i) {
      if (race) ++counter;
      else { std::lock_guard<std::mutex> lock(mutex); ++counter; }
    }
  };
  std::thread first(increment), second(increment);
  first.join();
  second.join();
  return counter;
}

extern "C" __attribute__((noinline)) void forge_dependency_crash() {
  volatile int* null_pointer = nullptr;
  *null_pointer = 42;
}
