cmake_minimum_required(VERSION 3.16)
project(hello_cmake_conan VERSION 1.0)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(fmt REQUIRED)

add_library(mylib SHARED mylib.cpp)
target_include_directories(mylib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(mylib PUBLIC fmt::fmt)

add_executable(hello main.cpp)
target_link_libraries(hello PRIVATE mylib)

install(TARGETS hello mylib
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
)
