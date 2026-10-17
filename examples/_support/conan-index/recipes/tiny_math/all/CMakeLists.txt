cmake_minimum_required(VERSION 3.24)
project(tiny_math LANGUAGES CXX)

add_library(tiny_math src/tiny_math.cc)
target_compile_features(tiny_math PUBLIC cxx_std_20)
target_include_directories(tiny_math PUBLIC
  "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
  "$<INSTALL_INTERFACE:include>")

install(TARGETS tiny_math ARCHIVE DESTINATION lib LIBRARY DESTINATION lib)
install(FILES include/tiny_math/answer.h DESTINATION include/tiny_math)
install(FILES LICENSE DESTINATION licenses)
