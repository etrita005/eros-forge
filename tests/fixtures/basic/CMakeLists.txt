cmake_minimum_required(VERSION 3.24)
project(forge_basic LANGUAGES CXX)
add_executable(forge_basic main.cc)
install(TARGETS forge_basic RUNTIME DESTINATION bin)
