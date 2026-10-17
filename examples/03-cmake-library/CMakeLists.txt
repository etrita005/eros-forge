cmake_minimum_required(VERSION 3.24)
project(cmake_math LANGUAGES CXX)

add_library(answer STATIC src/answer.cc)
set_target_properties(answer PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_features(answer PUBLIC cxx_std_20)
target_include_directories(answer PUBLIC
  "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
  "$<INSTALL_INTERFACE:include>")

install(TARGETS answer ARCHIVE DESTINATION lib)
install(FILES include/cmake_math/answer.h DESTINATION include/cmake_math)
