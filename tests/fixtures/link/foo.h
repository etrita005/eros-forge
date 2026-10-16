#pragma once
#ifndef FOO_PUBLIC
#error "the provider must export FOO_PUBLIC"
#endif
#include "public_config.h"
extern "C" int forge_foo(int input);
