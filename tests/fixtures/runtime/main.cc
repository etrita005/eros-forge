#include <dlfcn.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

extern "C" int forge_a_value();
namespace fs = std::filesystem;

int main(int argc, char** argv) {
  const auto executable = fs::canonical("/proc/self/exe");
  const auto root = executable.parent_path().parent_path();
  fs::path plugin = root / "lib/libforge_plugin.so.1";
  fs::path resource = root / "share/runtime-marker.txt";
  std::string layout = "private";
  if (!fs::exists(resource)) {
    layout = "runfiles";
    std::vector<fs::path> runfiles;
    for (const char* variable : {"RUNFILES_DIR", "TEST_SRCDIR"}) {
      if (const char* value = std::getenv(variable)) runfiles.emplace_back(value);
    }
    runfiles.emplace_back(std::string(argv[0]) + ".runfiles");
    runfiles.emplace_back(executable.parent_path() / "app.runfiles");
    bool found = false;
    for (const auto& directory : runfiles) {
      for (const char* repository : {"_main", "eros_forge"}) {
        const auto package = directory / repository / "tests/fixtures/runtime";
        if (fs::exists(package / "marker.txt")) {
          resource = package / "marker.txt";
          plugin = package / "libforge_plugin.so.1";
          found = true;
          break;
        }
      }
      if (found) break;
    }
    if (!found) {
      std::cerr << "missing declared resource in private/runfiles layout\n";
      return 2;
    }
  }
  std::ifstream input(resource);
  std::string marker;
  std::getline(input, marker);
  if (!input && marker.empty()) return 3;
  void* module = dlopen(plugin.c_str(), RTLD_NOW | RTLD_LOCAL);
  if (!module) {
    std::cerr << "dlopen " << plugin << ": " << dlerror() << '\n';
    return 4;
  }
  auto value = reinterpret_cast<int (*)(const char*)>(dlsym(module, "forge_plugin_value"));
  const int linked = forge_a_value();
  const int loaded = value ? value(marker.c_str()) : -1;
  dlclose(module);
  std::cout << "F-RUNTIME linked=" << linked << " plugin=" << loaded
            << " marker=" << marker << " layout=" << layout << '\n';
  return linked == 42 && loaded == 23 ? 0 : 5;
}
