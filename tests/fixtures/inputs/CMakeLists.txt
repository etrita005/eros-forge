cmake_minimum_required(VERSION 3.24)
project(forge_inputs LANGUAGES CXX)
find_package(bar CONFIG REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
include(settings.cmake)
configure_file(configured.h.in configured.h @ONLY)
execute_process(
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/generate.py"
  OUTPUT_FILE "${CMAKE_CURRENT_BINARY_DIR}/generated.h"
  COMMAND_ERROR_IS_FATAL ANY)
add_library(forge_inputs STATIC library.cc)
set_target_properties(forge_inputs PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(forge_inputs PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_BINARY_DIR}")
target_link_libraries(forge_inputs PUBLIC bar::bar)
install(TARGETS forge_inputs ARCHIVE DESTINATION lib)
install(FILES public.h DESTINATION include)
