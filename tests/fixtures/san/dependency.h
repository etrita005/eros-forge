#pragma once

extern "C" {
int forge_dependency_value(int input);
int forge_dependency_asan(int index);
int forge_dependency_ubsan(int input);
int forge_dependency_race(int race);
void forge_dependency_crash();
}
