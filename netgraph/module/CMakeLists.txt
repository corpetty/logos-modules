cmake_minimum_required(VERSION 3.14)
project(NetgraphModulePlugin LANGUAGES CXX)

if(DEFINED ENV{LOGOS_MODULE_BUILDER_ROOT})
    include($ENV{LOGOS_MODULE_BUILDER_ROOT}/cmake/LogosModule.cmake)
elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/cmake/LogosModule.cmake")
    include(cmake/LogosModule.cmake)
else()
    message(FATAL_ERROR "LogosModule.cmake not found. LOGOS_MODULE_BUILDER_ROOT is not set.")
endif()

# Universal module. The builder runs `logos-cpp-generator --from-header` for the
# Qt glue and, because metadata.json declares `interface_dependencies`,
# `--interface connection_source=interfaces/connection_source.h=IConnectionSource`
# to produce the bound `ConnectionSource` wrapper + `bind_connection_source`
# factory.
#
# SKELETON source list. The M0 collector adds the platform-split socket table:
#     src/collector.h
#     src/linux_socket_table.cpp   # /proc/net + /proc/<pid>/fd
#     src/macos_socket_table.cpp   # libproc
#     src/fake_socket_table.cpp    # tests / doctest fixture
#     src/socket_table_factory.cpp # makeSocketTable() platform pick
# gated by CMAKE_SYSTEM_NAME so each host compiles only its own impl.
logos_module(
    NAME netgraph
    SOURCES
        src/netgraph_impl.h
        src/netgraph_impl.cpp
        src/collector.h
)
