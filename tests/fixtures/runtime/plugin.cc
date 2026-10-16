#include <cstring>

extern "C" int forge_plugin_dependency_value();
extern "C" int forge_plugin_value(const char* marker) {
  return std::strcmp(marker, "FORGE_RUNTIME_MARKER_62b591") == 0
             ? forge_plugin_dependency_value() + 6
             : -1;
}
