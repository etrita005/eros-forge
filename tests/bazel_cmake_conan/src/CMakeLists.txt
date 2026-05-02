cmake_minimum_required(VERSION 3.16)
project(hello_cmake_conan VERSION 1.0)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(fmt REQUIRED)

add_library(mylib_static STATIC mylib.cpp)
target_include_directories(mylib_static PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(mylib_static PUBLIC fmt::fmt)

add_library(mylib_shared SHARED mylib.cpp)
target_include_directories(mylib_shared PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(mylib_shared PUBLIC fmt::fmt)

add_executable(hello main.cpp)
target_link_libraries(hello PRIVATE mylib_static)

install(TARGETS hello
    RUNTIME DESTINATION bin
)
install(TARGETS mylib_static mylib_shared
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)
