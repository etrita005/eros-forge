#include "dependency.h"

#include <atomic>
#include <climits>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>

namespace {

__attribute__((noinline)) int BusinessAsan(int index) {
  volatile int* values = new int[2]{41, 42};
  const int result = values[index];
  delete[] values;
  return result;
}

__attribute__((noinline)) int BusinessUbsan(int input) {
  volatile int value = input;
  return value + 1;
}

__attribute__((noinline)) int BusinessRace(bool race) {
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

}

int main(int argc, char** argv) {
  std::string source = "business";
  std::string bug = "none";
  int input = 0;
  for (int i = 1; i < argc; ++i) {
    const std::string argument = argv[i];
    if (argument.starts_with("--source=")) source = argument.substr(9);
    else if (argument.starts_with("--bug=")) bug = argument.substr(6);
    else if (argument.starts_with("--input=")) input = std::stoi(argument.substr(8));
    else return 2;
  }
  const bool dependency = source == "dependency";
  if (bug == "asan") {
    std::cout << (dependency ? forge_sanitizer_asan(input) : BusinessAsan(input)) << '\n';
  } else if (bug == "ubsan") {
    std::cout << (dependency ? forge_sanitizer_ubsan(input) : BusinessUbsan(input)) << '\n';
  } else if (bug == "race" || bug == "synchronized") {
    const bool race = bug == "race";
    const int result = dependency ? forge_sanitizer_race(race) : BusinessRace(race);
    std::cout << "threads=" << result << '\n';
    if (!race && result != 20000) return 1;
  } else if (bug == "none") {
    const int result = forge_sanitizer_value(20);
    std::cout << "forge-san=" << result << '\n';
    return result == 43 ? 0 : 1;
  } else {
    return 2;
  }
  return 0;
}
