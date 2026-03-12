cmake_minimum_required(VERSION 3.18)
project(cpp_path LANGUAGES CXX)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(cpp_path path.cpp)

target_compile_features(cpp_path PRIVATE cxx_std_17)

if (MSVC)
    target_compile_options(cpp_path PRIVATE /permissive-)
endif()

install(TARGETS cpp_path DESTINATION .)