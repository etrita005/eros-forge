#include "dependency.h"

#include <atomic>
#include <mutex>
#include <thread>

extern "C" int forge_sanitizer_value(int input) {
  return input * 2 + 3;
}

extern "C" int forge_sanitizer_asan(int index) {
  volatile int* values = new int[2]{41, 42};
  const int result = values[index];
  delete[] values;
  return result;
}

extern "C" int forge_sanitizer_ubsan(int input) {
  volatile int value = input;
  return value + 1;
}

extern "C" int forge_sanitizer_race(bool race) {
  alignas(64) volatile int value = 0;
  std::atomic<bool> start{false};
  std::mutex mutex;
  const auto worker = [&] {
    while (!start.load(std::memory_order_acquire)) std::this_thread::yield();
    for (int i = 0; i < 10000; ++i) {
      if (race) {
        value = value + 1;
      } else {
        const std::lock_guard<std::mutex> lock(mutex);
        value = value + 1;
      }
    }
  };
  std::thread first(worker);
  std::thread second(worker);
  start.store(true, std::memory_order_release);
  first.join();
  second.join();
  return value;
}
