cmake_minimum_required(VERSION 3.14)
project(physics2d CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

# ---------- GoogleTest ----------
FetchContent_Declare(
  googletest
  URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

# ---------- raylib (그래픽 뷰어용) ----------
FetchContent_Declare(
  raylib
  URL https://github.com/raysan5/raylib/archive/refs/tags/5.0.tar.gz
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_GAMES OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(raylib)

# 콘솔 데모
add_executable(physics2d main.cpp)

# 그래픽 뷰어
add_executable(viewer viewer.cpp)
target_link_libraries(viewer raylib)

# 테스트
enable_testing()
add_executable(physics_test physics_test.cpp)
target_link_libraries(physics_test GTest::gtest_main)

if(MSVC)
  target_compile_options(physics2d PRIVATE /utf-8)
  target_compile_options(physics_test PRIVATE /utf-8)
  target_compile_options(viewer PRIVATE /utf-8)
endif()

include(GoogleTest)
gtest_discover_tests(physics_test)