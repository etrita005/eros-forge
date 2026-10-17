cmake_minimum_required(VERSION 3.24)
project(conan_math LANGUAGES CXX)

find_package(tiny_math CONFIG REQUIRED)
add_library(answer STATIC src/answer.cc)
set_target_properties(answer PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_features(answer PUBLIC cxx_std_20)
target_include_directories(answer PUBLIC
  "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
  "$<INSTALL_INTERFACE:include>")
target_link_libraries(answer PRIVATE tiny_math::tiny_math)

install(TARGETS answer ARCHIVE DESTINATION lib)
install(FILES include/conan_math/answer.h DESTINATION include/conan_math)
