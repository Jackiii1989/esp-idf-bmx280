file(GLOB COMPONENT_SOURCES
	"./src/*.cpp"
    "./src/*.c"
	"./*.cpp"
	"./*.c"
)

set(COMPONENT_INCLUDE_DIRS
	${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/include
    #${CMAKE_CURRENT_LIST_DIR}/src/
)


idf_component_register(
        SRCS ${COMPONENT_SOURCES}
        INCLUDE_DIRS ${COMPONENT_INCLUDE_DIRS}
        REQUIRES esp_driver_pcnt esp_timer esp_driver_gpio
)
