#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

int main() {
  const auto root = std::filesystem::canonical("/proc/self/exe").parent_path().parent_path();
  const auto plugin_path = root / "lib/libcmake_plugin.so";
  void* plugin = dlopen(plugin_path.c_str(), RTLD_NOW | RTLD_LOCAL);
  if (!plugin) { std::cerr << dlerror() << '\n'; return 1; }
  const auto value = reinterpret_cast<int (*)()>(dlsym(plugin, "forge_cmake_plugin_value"));
  if (!value || value() != 42) return 2;
  std::ifstream resource(root / "share/cmake/marker.txt");
  std::string marker;
  std::getline(resource, marker);
  if (marker != "FORGE_CMAKE_EXPLICIT_PLUGIN_RESOURCE") return 3;
  dlclose(plugin);
  std::cout << "forge-cmake-runtime=42 " << marker << '\n';
  return 0;
}
