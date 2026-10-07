# =============================================================================
#  yolo_mfg : 제조업용 YOLOv8 개체탐지(검사) 프로그램
#  - OpenCV 5 (4.x도 호환)
#  - OpenVINO Runtime  (Intel Arc A770 / UHD 770 / CPU)
#  - ONNX Runtime      (+ OpenVINO Execution Provider)
# =============================================================================
cmake_minimum_required(VERSION 3.16)
project(yolo_mfg LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)            # std::filesystem 사용
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 두 백엔드 모두 기본 ON. 한쪽만 쓰려면 -DENABLE_ONNXRUNTIME=OFF 처럼 끄면 됩니다.
option(ENABLE_OPENVINO    "OpenVINO 백엔드 포함"     ON)
option(ENABLE_ONNXRUNTIME "ONNX Runtime 백엔드 포함" ON)

if(MSVC)
    # 소스의 한글 주석/문자열을 UTF-8로 처리
    add_compile_options(/utf-8 /W3 /permissive-)
endif()

# ---------------------------------------------------------------- OpenCV
# OpenCV_DIR 에 OpenCVConfig.cmake 가 있는 폴더를 지정하세요.
find_package(OpenCV REQUIRED COMPONENTS core imgproc imgcodecs videoio highgui)
message(STATUS "OpenCV version : ${OpenCV_VERSION}")

add_executable(yolo_mfg
    src/main.cpp
    src/common.cpp
    src/config.cpp
    src/inspection.cpp
    src/part_trigger.cpp    # 소프트웨어 부품 감지 트리거
    src/yolo_tasks.cpp      # 검출(YoloDetector) / 분류(YoloClassifier) + 엔진 생성
)
target_include_directories(yolo_mfg PRIVATE ${CMAKE_SOURCE_DIR}/include ${OpenCV_INCLUDE_DIRS})
target_link_libraries(yolo_mfg PRIVATE ${OpenCV_LIBS})

# ---------------------------------------------------------------- OpenVINO
if(ENABLE_OPENVINO)
    # OpenVINO 설치 후 setupvars.bat(.sh) 를 실행하면 OpenVINO_DIR 이 자동 설정됩니다.
    find_package(OpenVINO REQUIRED COMPONENTS Runtime)
    target_sources(yolo_mfg PRIVATE src/openvino_engine.cpp)
    target_link_libraries(yolo_mfg PRIVATE openvino::runtime)
    target_compile_definitions(yolo_mfg PRIVATE USE_OPENVINO)
    message(STATUS "OpenVINO backend : ON")
endif()

# ---------------------------------------------------------------- ONNX Runtime
if(ENABLE_ONNXRUNTIME)
    # ONNX Runtime 은 공식 CMake config 가 없는 배포판이 많아 경로를 직접 지정합니다.
    #   예) -DONNXRUNTIME_DIR=C:/libs/onnxruntime-openvino
    #   폴더 구조: include/onnxruntime_cxx_api.h, lib/onnxruntime.lib(.so)
    set(ONNXRUNTIME_DIR "" CACHE PATH "ONNX Runtime 루트 폴더")
    find_path(ORT_INCLUDE_DIR onnxruntime_cxx_api.h
        PATHS ${ONNXRUNTIME_DIR}/include
              ${ONNXRUNTIME_DIR}/include/onnxruntime
              ${ONNXRUNTIME_DIR}/include/onnxruntime/core/session
        NO_DEFAULT_PATH)
    find_library(ORT_LIBRARY onnxruntime PATHS ${ONNXRUNTIME_DIR}/lib NO_DEFAULT_PATH)

    if(NOT ORT_INCLUDE_DIR OR NOT ORT_LIBRARY)
        message(FATAL_ERROR "ONNX Runtime 을 찾지 못했습니다. -DONNXRUNTIME_DIR=경로 를 지정하거나 "
                            "-DENABLE_ONNXRUNTIME=OFF 로 끄세요.")
    endif()

    target_sources(yolo_mfg PRIVATE src/ort_engine.cpp)
    target_include_directories(yolo_mfg PRIVATE ${ORT_INCLUDE_DIR})
    target_link_libraries(yolo_mfg PRIVATE ${ORT_LIBRARY})
    target_compile_definitions(yolo_mfg PRIVATE USE_ONNXRUNTIME)
    message(STATUS "ONNX Runtime backend : ON (${ORT_LIBRARY})")

    # Windows: 실행 폴더로 ORT DLL 복사 (OpenVINO EP 용 DLL 포함)
    if(WIN32)
        file(GLOB ORT_DLLS "${ONNXRUNTIME_DIR}/lib/*.dll" "${ONNXRUNTIME_DIR}/bin/*.dll")
        foreach(dll ${ORT_DLLS})
            add_custom_command(TARGET yolo_mfg POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy_if_different ${dll} $<TARGET_FILE_DIR:yolo_mfg>)
        endforeach()
    endif()
endif()

# 설정 파일을 실행 파일 옆으로 복사 (실행 위치에 상관없이 동작하도록)
if(EXISTS ${CMAKE_SOURCE_DIR}/config)   # ai_factory 배치에서는 config 가 엔진 폴더 밖에 있음
    add_custom_command(TARGET yolo_mfg POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
                ${CMAKE_SOURCE_DIR}/config $<TARGET_FILE_DIR:yolo_mfg>/config)
endif()
