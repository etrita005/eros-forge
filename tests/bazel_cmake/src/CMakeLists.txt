cmake_minimum_required(VERSION 3.16)
project(hello_cmake)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(math_utils_static STATIC lib/math_utils.cpp)
target_include_directories(math_utils_static PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

add_library(math_utils_shared SHARED lib/math_utils.cpp)
target_include_directories(math_utils_shared PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

add_executable(hello_cmake main.cpp)
target_link_libraries(hello_cmake PRIVATE math_utils_static)

install(TARGETS hello_cmake DESTINATION bin)
install(TARGETS math_utils_static DESTINATION lib)
install(TARGETS math_utils_shared DESTINATION lib)
