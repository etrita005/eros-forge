#pragma once

extern "C" {
int forge_sanitizer_value(int input);
int forge_sanitizer_asan(int index);
int forge_sanitizer_ubsan(int input);
int forge_sanitizer_race(bool race);
}
