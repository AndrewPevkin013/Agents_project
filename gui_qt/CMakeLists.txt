cmake_minimum_required(VERSION 3.14)

project(MultiAgentChat LANGUAGES CXX)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(QT NAMES Qt6 Qt5 REQUIRED COMPONENTS Core Widgets Network)
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Core Widgets Network)

add_executable(MultiAgentChat
    main.cpp
    api_client.h
    api_client.cpp
    main_window.h
    main_window.cpp
    settings_dialog.h
    settings_dialog.cpp
)

target_link_libraries(MultiAgentChat PRIVATE
    Qt${QT_VERSION_MAJOR}::Core
    Qt${QT_VERSION_MAJOR}::Widgets
    Qt${QT_VERSION_MAJOR}::Network
)
