# Common Bugs & Security Issues in ESP32/Embedded C

This reference covers frequent bugs and security vulnerabilities found in embedded systems code.

## Table of Contents
1. [Integer Issues](#integer-issues)
2. [String Handling](#string-handling)
3. [Concurrency Bugs](#concurrency-bugs)
4. [Logic Errors](#logic-errors)
5. [Security Vulnerabilities](#security-vulnerabilities)
6. [Performance Issues](#performance-issues)

## Integer Issues

### Integer Overflow

**Problem:** Math operations overflow silently, wrapping around

**BAD:**
```c
uint32_t buffer_size = user_input;
uint32_t total_size = buffer_size * sizeof(struct_t);  // Overflow if buffer_size > 1M
void *buffer = malloc(total_size);
```

**Why it's bad:** If `buffer_size = 0x10000001` and `sizeof(struct_t) = 256`:
- Expected: 0x10000001 * 256 = 0x1000000100 (4GB+)
- Actual: Wraps to 0x100 (256 bytes)
- Result: Tiny buffer allocated, massive overflow

**GOOD:**
```c
#define MAX_BUFFER_COUNT (SIZE_MAX / sizeof(struct_t))

uint32_t buffer_count = user_input;
if (buffer_count > MAX_BUFFER_COUNT) {
    ESP_LOGE(TAG, "Buffer size would overflow");
    return ESP_ERR_INVALID_ARG;
}
void *buffer = malloc(buffer_count * sizeof(struct_t));
```

### Sign Conversion Issues

**BAD:**
```c
int8_t signed_value = -1;
uint8_t unsigned_value = signed_value;  // -1 becomes 255!
if (unsigned_value > 10) {
    // Always true, even though original was negative
}
```

**GOOD:**
```c
int8_t signed_value = -1;
uint8_t unsigned_value;

if (signed_value < 0) {
    ESP_LOGE(TAG, "Expected positive value");
    return ESP_ERR_INVALID_ARG;
}
unsigned_value = (uint8_t)signed_value;
```

### Off-by-One Errors

**BAD - Common array bug:**
```c
uint8_t buffer[100];

// Loop goes 0-100 inclusive (101 iterations!)
for (int i = 0; i <= sizeof(buffer); i++) {
    buffer[i] = 0;  // Writes past end on last iteration
}
```

**GOOD:**
```c
uint8_t buffer[100];

// Loop goes 0-99 (100 iterations)
for (int i = 0; i < sizeof(buffer); i++) {
    buffer[i] = 0;
}

// Or use a constant
for (size_t i = 0; i < ARRAY_SIZE(buffer); i++) {
    buffer[i] = 0;
}
```

## String Handling

### Buffer Overflow from String Input

**CRITICAL - BAD:**
```c
void process_command(const char *user_input)
{
    char command[50];
    strcpy(command, user_input);  // No bounds checking!
    
    // If user_input is 100 bytes, this overflows stack
    // Attacker can overwrite return address
}
```

**GOOD:**
```c
void process_command(const char *user_input)
{
    char command[50];
    
    // Use strncpy with size limit
    strncpy(command, user_input, sizeof(command) - 1);
    command[sizeof(command) - 1] = '\0';  // Ensure null termination
    
    // Process command safely
    execute_command(command);
}
```

### Missing Null Terminators

**BAD:**
```c
char buffer[10];
memcpy(buffer, user_data, 10);  // No null terminator!
printf("%s", buffer);  // Reads past buffer looking for \0
```

**GOOD:**
```c
char buffer[11];  // 10 + 1 for null terminator
memcpy(buffer, user_data, 10);
buffer[10] = '\0';  // Explicit null terminator
printf("%s", buffer);
```

### String Concatenation Overflow

**BAD:**
```c
char full_path[256];
strcpy(full_path, user_directory);  // Directory might be 200 bytes
strcat(full_path, user_filename);   // Filename might be 100 bytes = overflow!
```

**GOOD:**
```c
char full_path[256];
int written = snprintf(full_path, sizeof(full_path), "%s/%s",
                       user_directory, user_filename);
if (written >= sizeof(full_path)) {
    ESP_LOGE(TAG, "Path too long");
    return ESP_ERR_INVALID_ARG;
}
```

## Concurrency Bugs

### Race Condition on Shared Variable

**BAD:**
```c
static int s_counter = 0;

void task1(void *arg) {
    while (1) {
        int val = s_counter;
        s_counter = val + 1;
        vTaskDelay(10);
    }
}

void task2(void *arg) {
    while (1) {
        int val = s_counter;
        s_counter = val + 10;
        vTaskDelay(10);
    }
}

// If task1 reads s_counter (0), then task2 writes (10), 
// then task1 writes (1), we lost the increment!
```

**GOOD:**
```c
static int s_counter = 0;
static SemaphoreHandle_t s_counter_mutex = NULL;

void task1(void *arg) {
    while (1) {
        xSemaphoreTake(s_counter_mutex, portMAX_DELAY);
        s_counter++;
        xSemaphoreGive(s_counter_mutex);
        vTaskDelay(10);
    }
}

void task2(void *arg) {
    while (1) {
        xSemaphoreTake(s_counter_mutex, portMAX_DELAY);
        s_counter += 10;
        xSemaphoreGive(s_counter_mutex);
        vTaskDelay(10);
    }
}
```

### ISR Modifying Unprotected Variable

**BAD:**
```c
static int s_flag = 0;

void IRAM_ATTR isr_handler(void *arg) {
    s_flag = 1;  // Not volatile, might not be visible to tasks
}

void task(void *arg) {
    while (!s_flag) {  // Compiler might optimize to while(1) since flag doesn't change in task
        vTaskDelay(100);
    }
}
```

**GOOD:**
```c
static volatile int s_flag = 0;  // Volatile ensures memory access

void IRAM_ATTR isr_handler(void *arg) {
    s_flag = 1;
}

void task(void *arg) {
    while (!s_flag) {  // Will see ISR changes
        vTaskDelay(100);
    }
}
```

## Logic Errors

### Comparison Logic Error

**BAD:**
```c
uint8_t battery_level = adc_read();

// Intended to check if battery is in valid range 0-100
if (battery_level < 0 || battery_level > 100) {
    // This condition is always false!
    // uint8_t can never be < 0
    ESP_LOGE(TAG, "Invalid battery");
}
```

**GOOD:**
```c
uint8_t battery_level = adc_read();

// Correct - battery can be 0-255
if (battery_level > 100) {
    ESP_LOGE(TAG, "Invalid battery reading");
}
```

### Uninitialized Variable Use

**BAD:**
```c
void process_config(void)
{
    int value;
    if (read_config(&value) == ESP_OK) {
        // value is now initialized
    }
    
    // But what if read_config fails?
    printf("Value: %d\n", value);  // Garbage if read_config failed
}
```

**GOOD:**
```c
void process_config(void)
{
    int value = 0;  // Initialize to safe default
    
    esp_err_t err = read_config(&value);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read config: %s", esp_err_to_name(err));
        value = DEFAULT_VALUE;
    }
    
    printf("Value: %d\n", value);  // Always initialized
}
```

### Floating Point Comparison

**BAD:**
```c
float temperature = read_temp();

if (temperature == 25.0) {
    // Floating point comparison! Due to rounding, may never be exactly 25.0
    set_cooling(true);
}
```

**GOOD:**
```c
float temperature = read_temp();
const float TEMP_THRESHOLD = 25.0;
const float EPSILON = 0.1;

if (fabs(temperature - TEMP_THRESHOLD) < EPSILON) {
    // Range check instead of exact equality
    set_cooling(true);
}
```

## Security Vulnerabilities

### Command Injection via String Format

**BAD - Format String Vulnerability:**
```c
void log_user_input(const char *user_input)
{
    // User input used as format string!
    printf(user_input);
    
    // Attacker input: "%x %x %x" reads stack
    // Attacker input: "%n" writes to memory
}
```

**GOOD:**
```c
void log_user_input(const char *user_input)
{
    // User input is DATA, not format string
    printf("User said: %s\n", user_input);
}
```

### Path Traversal

**BAD:**
```c
void read_file(const char *filename)
{
    char full_path[256];
    snprintf(full_path, sizeof(full_path), "/data/%s", filename);
    
    FILE *f = fopen(full_path, "r");
    // If filename is "../../../etc/config", reads outside /data!
}
```

**GOOD:**
```c
void read_file(const char *filename)
{
    // Validate filename contains no path separators
    if (strchr(filename, '/') || strchr(filename, '\\')) {
        ESP_LOGE(TAG, "Invalid filename");
        return;
    }
    
    char full_path[256];
    snprintf(full_path, sizeof(full_path), "/data/%s", filename);
    FILE *f = fopen(full_path, "r");
}
```

### Unchecked External Input

**BAD:**
```c
void process_network_packet(const uint8_t *data, size_t len)
{
    struct packet_t *pkt = (struct packet_t *)data;
    
    // No validation!
    int index = pkt->array_index;
    int value = my_array[index];  // Out of bounds access possible
}
```

**GOOD:**
```c
#define MY_ARRAY_SIZE 100

void process_network_packet(const uint8_t *data, size_t len)
{
    if (len < sizeof(struct packet_t)) {
        ESP_LOGE(TAG, "Packet too small");
        return;
    }
    
    struct packet_t *pkt = (struct packet_t *)data;
    
    if (pkt->array_index >= MY_ARRAY_SIZE) {
        ESP_LOGE(TAG, "Invalid index: %d", pkt->array_index);
        return;
    }
    
    int value = my_array[pkt->array_index];  // Safe
}
```

## Performance Issues

### Busy-Wait Loops

**BAD - Wastes CPU:**
```c
void wait_for_ready(void)
{
    while (!device_ready_flag) {
        // Spinning: wastes all CPU cycles, 100% usage
        // Prevents other tasks from running
    }
}
```

**GOOD - Block the task:**
```c
void wait_for_ready(void)
{
    while (!device_ready_flag) {
        vTaskDelay(pdMS_TO_TICKS(10));  // Block for 10ms, yields CPU
    }
}

// Even better - use event signaling
void IRAM_ATTR device_ready_isr(void *arg) {
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    xSemaphoreGiveFromISR(ready_semaphore, &xHigherPriorityTaskWoken);
    if (xHigherPriorityTaskWoken) portYIELD_FROM_ISR();
}

void wait_for_ready(void)
{
    xSemaphoreTake(ready_semaphore, portMAX_DELAY);  // Block until ready
}
```

### Logging at High Frequency

**BAD - Performance bottleneck:**
```c
void high_speed_isr(void *arg)
{
    // Logging from ISR can block for milliseconds!
    // Causes missed samples, watchdog resets
    
    for (int i = 0; i < 1000; i++) {
        int sample = read_adc();
        ESP_LOGI(TAG, "Sample %d: %d", i, sample);  // VERY SLOW
    }
}
```

**GOOD - Log selectively:**
```c
void high_speed_isr(void *arg)
{
    for (int i = 0; i < 1000; i++) {
        int sample = read_adc();
        
        if (i % 100 == 0) {  // Log every 100th sample
            ESP_LOGI(TAG, "Sample %d: %d", i, sample);
        }
    }
}

// Or use a circular buffer to log later
void sampling_task(void *arg)
{
    while (1) {
        int sample;
        if (xQueueReceive(sample_queue, &sample, 0) == pdTRUE) {
            ESP_LOGI(TAG, "Sample: %d", sample);
        }
        vTaskDelay(1);
    }
}
```

### Dynamic Allocation in Real-Time Path

**BAD - Can fail anytime:**
```c
void real_time_control_task(void *arg)
{
    while (1) {
        // This CAN FAIL at any time, unpredictable
        uint8_t *buffer = malloc(1000);
        if (!buffer) {
            // What do we do now? Control missed, system unstable
        }
        
        // Use buffer
        process_control_data(buffer);
        free(buffer);
        vTaskDelay(10);
    }
}
```

**GOOD - Pre-allocate:**
```c
typedef struct {
    uint8_t buffer[1000];
    QueueHandle_t queue;
} control_context_t;

static control_context_t s_control = {};

void app_init(void)
{
    // Allocate once at startup
    s_control.queue = xQueueCreate(10, sizeof(uint8_t*));
}

void real_time_control_task(void *arg)
{
    while (1) {
        // No allocation, predictable timing
        process_control_data(s_control.buffer);
        vTaskDelay(10);
    }
}
```

## Debugging Checklist

When code misbehaves:

### Memory Issues
- [ ] Check for buffer overflows (especially string functions)
- [ ] Verify malloc/free balance
- [ ] Look for use-after-free
- [ ] Check for uninitialized variables
- [ ] Monitor stack usage with `uxTaskGetStackHighWaterMark()`

### Concurrency Issues
- [ ] Check for race conditions on shared variables
- [ ] Verify all shared variables are volatile
- [ ] Ensure proper mutex/semaphore usage
- [ ] Check for deadlocks (circular waits)
- [ ] Look for ISRs modifying shared state unsafely

### Logic Issues
- [ ] Verify integer overflow handling
- [ ] Check comparison logic (especially with unsigned)
- [ ] Ensure proper error handling
- [ ] Verify off-by-one loop conditions
- [ ] Check floating point comparisons

### Performance Issues
- [ ] Look for busy-wait loops
- [ ] Check ISR execution time
- [ ] Monitor task priorities and starvation
- [ ] Review logging frequency
- [ ] Check for unnecessary allocations
