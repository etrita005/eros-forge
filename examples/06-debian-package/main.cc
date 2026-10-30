#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

fs::path FindResource(const char* argv0) {
  const fs::path executable = fs::canonical("/proc/self/exe");
  const fs::path private_resource = executable.parent_path().parent_path() / "share/debian-package.txt";
  if (fs::exists(private_resource)) return private_resource;

  std::vector<fs::path> runfiles;
  for (const char* variable : {"RUNFILES_DIR", "TEST_SRCDIR"}) {
    if (const char* value = std::getenv(variable)) runfiles.emplace_back(value);
  }
  runfiles.emplace_back(std::string(argv0) + ".runfiles");
  runfiles.emplace_back(executable.parent_path() / "app.runfiles");
  for (const fs::path& directory : runfiles) {
    for (const char* repository : {"_main", "forge_examples"}) {
      const fs::path candidate = directory / repository / "06-debian-package/resource.txt";
      if (fs::exists(candidate)) return candidate;
    }
  }
  return {};
}

}

int main(int argc, char** argv) {
  const fs::path resource = FindResource(argv[0]);
  std::string marker;
  if (!resource.empty()) {
    std::ifstream input(resource);
    std::getline(input, marker);
  }
  const int result = 20 * 2 + 1;
  const bool private_layout = resource.string().find(".runfiles") == std::string::npos;
  std::cout << "result=" << result << " marker=" << marker
            << " layout=" << (private_layout ? "private" : "runfiles") << '\n';
  return result == 41 && marker == "FORGE_DEBIAN_PACKAGE_MARKER" ? 0 : 1;
}
