#include "plugin_api.h"
extern "C" int forge_cmake_private_value();
extern "C" int forge_cmake_plugin_value() { return forge_cmake_private_value() + 1; }
