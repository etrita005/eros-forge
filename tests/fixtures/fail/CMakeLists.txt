cmake_minimum_required(VERSION 3.24)
project(forge_fail LANGUAGES CXX)
add_library(valid STATIC valid.cc)
install(TARGETS valid ARCHIVE DESTINATION lib)
