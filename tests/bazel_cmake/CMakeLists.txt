cmake_minimum_required(VERSION 3.16)
project(hello_cmake)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(hello_cmake main.cpp)

install(TARGETS hello_cmake DESTINATION bin)
