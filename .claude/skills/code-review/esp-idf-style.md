# ESP-IDF Style Guide & Formatting

This reference covers the official Espressif style guide for ESP-IDF projects and formatting standards.

## Table of Contents
1. [Include Order](#include-order)
2. [Naming Conventions](#naming-conventions)
3. [Header Files](#header-files)
4. [Code Formatting](#code-formatting)
5. [Assertions & Error Handling](#assertions--error-handling)
6. [Comments & Documentation](#comments--documentation)
7. [Common Warnings](#common-warnings)

## Include Order

**CORRECT Order (Always Follow This):**
```c
#pragma once

#include <stdint.h>           // C standard library headers
#include <stdbool.h>
#include <string.h>

#include <sys/queue.h>        // POSIX headers and extensions

#include "esp_log.h"          // IDF common headers
#include "esp_system.h"
#include "esp_timer.h"

#include "freertos/FreeRTOS.h" // FreeRTOS headers
#include "freertos/task.h"
#include "freertos/queue.h"

#include "driver/gpio.h"       // Component/peripheral headers

#include "my_component.h"      // Project component headers (public)

#include "my_private.h"        // Private headers
```

**Why This Order Matters:**
- Each section is self-contained
- Dependencies are resolved correctly
- Prevents circular dependencies
- Makes includes easier to review

## Naming Conventions

### Functions & Variables

**Good:** Lowercase with underscores
```c
void initialize_peripherals(void);
esp_err_t read_sensor_data(int *out_value);
uint32_t calculate_checksum(const uint8_t *data, size_t len);
```

**Bad:** Mixed case or inconsistent
```c
void initializePeripherals(void);  // camelCase - don't use
void INITIALIZE_PERIPHERALS(void); // ALL_CAPS - only for macros
```

### Public Functions (Component API)

**MUST use component prefix:**
```c
// For "my_sensor" component:
esp_err_t my_sensor_init(void);
esp_err_t my_sensor_read(int *value);
void my_sensor_deinit(void);
```

**Use `esp_` prefix for Espressif-defined functions:**
```c
esp_err_t esp_flash_read(esp_flash_t *chip, void *buffer, uint32_t address, uint32_t length);
esp_err_t esp_timer_create(const esp_timer_create_args_t *create_args, esp_timer_handle_t *out_handle);
```

### Static Variables

**ALWAYS prefix with `s_` for easy identification:**
```c
static int s_counter = 0;           // Good
static SemaphoreHandle_t s_mutex = NULL;  // Good

static int counter = 0;              // Bad - unclear if static
```

### Constants & Macros

**Use UPPER_CASE for both:**
```c
#define MAX_BUFFER_SIZE 1024
#define TIMEOUT_MS 5000

const int DEFAULT_PRIORITY = 2;
const uint32_t CONFIG_TIMEOUT = 5000;
```

### Type Definitions

**Use _t suffix for typedef'd types:**
```c
typedef struct {
    int x;
    int y;
} point_t;

typedef enum {
    STATE_IDLE,
    STATE_RUNNING,
    STATE_ERROR
} device_state_t;
```

## Header Files

### Header Guard & C++ Support

**CORRECT Pattern:**
```c
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Public declarations here

#ifdef __cplusplus
}
#endif
```

**Order:** pragma once → includes → extern "C"

### What Goes in Headers

**Public API (what external code calls):**
```c
// my_sensor.h - PUBLIC
#pragma once

#include <esp_err.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t my_sensor_init(void);
esp_err_t my_sensor_read(int *out_value);
void my_sensor_deinit(void);

#ifdef __cplusplus
}
#endif
```

**Implementation (keep in .c file):**
```c
// my_sensor.c - PRIVATE
#include "my_sensor.h"

#include "esp_log.h"
#include "driver/gpio.h"

static const char *TAG = "my_sensor";
static int s_sensor_value = 0;

// Private helper functions
static esp_err_t _read_adc(void);
static void _apply_calibration(int *value);

// Public API implementation
esp_err_t my_sensor_init(void) {
    // ...
}
```

## Code Formatting

### Brace Style

**Function definition - brace on new line:**
```c
// CORRECT
void my_function(void)
{
    // code
}

// WRONG
void my_function(void) {
    // code
}
```

**Inside function - brace on same line:**
```c
// CORRECT
if (condition) {
    // code
}

for (int i = 0; i < 10; i++) {
    // code
}

// WRONG
if (condition)
{
    // code
}
```

### Indentation

**Use 4 spaces (not tabs):**
```c
void function(void)
{
    if (condition) {
        do_something();
        
        if (nested) {
            do_more();
        }
    }
}
```

### Line Length

**Keep lines reasonable (~80 characters):**
```c
// GOOD
esp_err_t err = esp_flash_read(
    chip, buffer, address, length);

// AVOID - Too long
esp_err_t err = esp_flash_read(chip, buffer, address_that_is_very_long, length_parameter);

// GOOD - Aligned parameters
void some_function(
    int first_parameter,
    int second_parameter,
    int third_parameter);
```

### Whitespace

**One blank line between logical sections:**
```c
void initialize_system(void)
{
    esp_err_t err;
    
    // Section 1: Initialize GPIO
    gpio_config_t io_conf = {};
    io_conf.pin_bit_mask = GPIO_SEL_0;
    io_conf.mode = GPIO_MODE_OUTPUT;
    gpio_config(&io_conf);
    
    // Section 2: Initialize timer
    esp_timer_create_args_t timer_args = {
        .callback = timer_callback,
    };
    esp_timer_create(&timer_args, &timer_handle);
}
```

**No trailing whitespace** at end of lines.

## Assertions & Error Handling

### Assertions

**Use ONLY for internal logic bugs:**
```c
// CORRECT - Internal invariant, shouldn't happen
assert(pointer != NULL);  // This is a programming bug if NULL

// WRONG - Recoverable error
assert(input_from_user > 0);  // User might give invalid input
```

**Avoid side effects in assertions:**
```c
// WRONG - Side effect if assertions disabled
assert(process_data(ptr) == 0);  // process_data() won't be called if assertions off!

// CORRECT
int res = process_data(ptr);
assert(res == 0);
(void)res;  // Suppress unused warning if assertions disabled
```

### Error Return Codes

**Always use esp_err_t for ESP-IDF functions:**
```c
esp_err_t my_init(void)
{
    esp_err_t err;
    
    err = initialize_peripheral();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Initialization failed: %s", esp_err_to_name(err));
        return err;
    }
    
    return ESP_OK;
}
```

### Error Checking Macro

**Use ESP_ERROR_CHECK() for unrecoverable errors:**
```c
// For errors that should never happen in normal operation
esp_err_t err = esp_flash_read(chip, buffer, address, length);
ESP_ERROR_CHECK(err);  // Logs error and calls abort() if err != ESP_OK

// Don't use for recoverable errors:
// esp_err_t err = read_user_input();
// ESP_ERROR_CHECK(err);  // WRONG - user input might be invalid
```

## Comments & Documentation

### Good Comments

**Explain WHY, not WHAT:**
```c
// GOOD - Explains rationale
// Use 10ms delay to allow capacitor discharge after GPIO toggle
vTaskDelay(pdMS_TO_TICKS(10));

// BAD - Just restates code
vTaskDelay(pdMS_TO_TICKS(10));  // Delay for 10ms
```

**Function documentation:**
```c
/**
 * @brief Initialize the sensor subsystem
 * 
 * @param config Configuration struct with sensor parameters
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if config is NULL
 */
esp_err_t sensor_init(const sensor_config_t *config);
```

### Comment Frequency

**Not every line needs a comment:**
```c
// OVER-COMMENTED
int x = 5;      // Set x to 5
x++;            // Increment x
if (x > 5) {    // If x is greater than 5
    printf("x is large\n");  // Print message
}

// WELL-COMMENTED
// Clear previous state before reinitialization
x = 5;
x++;
if (x > 5) {
    // x larger than threshold indicates overflow condition
    printf("x is large\n");
}
```

## Common Warnings

### Compilation Flags

**Always enable warnings:**
```bash
# In your build or CMakeLists.txt
-Wall -Wextra -Wpedantic -Werror
```

### Unused Variables

**Suppress intentionally unused parameters:**
```c
// BAD - Compiler warning
void callback(int unused_param)
{
    do_something();
}

// GOOD - Suppress warning
void callback(int __attribute__((unused)) unused_param)
{
    do_something();
}

// ALSO GOOD
void callback(int unused_param)
{
    (void)unused_param;  // Acknowledge unused
    do_something();
}
```

### Unused Functions

**Mark internal functions as static:**
```c
// BAD - Compiler might warn about unused global function
void helper_function(void)
{
    // only called within this file
}

// GOOD - Hide from linker
static void helper_function(void)
{
    // only called within this file
}
```

### Implicit Type Conversion

**Use explicit casts when needed:**
```c
// BAD - Loss of precision warning
int percentage = (total / 100);

// GOOD - Explicit cast shows intent
int percentage = (int)((total / 100.0) * 100);
```

### Format String Mismatches

**Always match format specifiers:**
```c
// WRONG
int value = 42;
printf("%s\n", value);  // Warning: %s expects char*

// CORRECT
printf("%d\n", value);

// Safe for ESP-IDF:
esp_err_t err = some_function();
ESP_LOGI(TAG, "Result: %s", esp_err_to_name(err));
```

## Static Analysis Tools

### Cppcheck Integration

**Configuration for ESP-IDF:**
```bash
cppcheck --enable=all \
         --addon=misra.py \
         --suppress=missingIncludeSystem \
         --suppress=unusedFunction \
         src/
```

**Configuration file (.cppcheckignore):**
```
# Ignore vendor code
vendor/
build/
.idf_build/
```

### Compiler Warnings

**Review warnings carefully:**
```bash
# Build with warnings
idf.py build

# Common warnings to fix:
# - "variable set but not used"
# - "unused function"
# - "implicit declaration"
# - "format string expects"

# Make them errors in CI:
idf.py build -DCMAKE_C_FLAGS="-Wall -Wextra -Werror"
```

## Checklist for Code Review

### Before Submitting

- [ ] Includes are in correct order
- [ ] Function names use lowercase with underscores
- [ ] Public functions prefixed with component name
- [ ] Static variables prefixed with `s_`
- [ ] Header guards use `#pragma once`
- [ ] C++ guard present in headers with `extern "C"`
- [ ] No trailing whitespace
- [ ] Functions use 4-space indentation
- [ ] Braces follow correct style
- [ ] Comments explain WHY not WHAT
- [ ] Error codes checked with `if (err != ESP_OK)`
- [ ] No side effects in asserts
- [ ] Compiles with `-Wall -Wextra`
- [ ] Magic numbers replaced with named constants
- [ ] No dead code or commented code
- [ ] Unused parameters marked with `(void)` or attribute
