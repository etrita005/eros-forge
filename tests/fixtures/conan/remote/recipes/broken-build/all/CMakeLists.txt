cmake_minimum_required(VERSION 3.24)
project(controlled_failure LANGUAGES CXX)
add_library(broken STATIC broken.cc)
