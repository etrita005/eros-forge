#include "public.h"
#include "configured.h"
#include "generated.h"
#include "forge_dependency.h"

extern "C" int forge_inputs_value() {
  return FORGE_HEADER_VALUE + FORGE_CONFIGURED_VALUE + FORGE_GENERATED_VALUE + forge_dependency_value(0);
}
