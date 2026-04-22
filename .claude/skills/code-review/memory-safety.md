# Memory Safety in Embedded C

This reference guide covers critical memory safety patterns and common vulnerabilities in embedded systems C code.

## Table of Contents
1. [Buffer Overflows](#buffer-overflows)
2. [Pointer Management](#pointer-management)
3. [Memory Allocation](#memory-allocation)
4. [Stack Management](#stack-management)
5. [Common Mistakes](#common-mistakes)

## Buffer Overflows

### Why It Matters
Buffer overflows are the most exploitable memory safety vulnerability in embedded systems. They allow:
- Memory corruption (crashes)
- Code execution if properly exploited
- System takeover in IoT devices

### Dangerous Functions to Avoid
```c
// NEVER USE THESE:
strcpy()      // No bounds checking
strcat()      // No bounds checking
gets()        // Removed from C standard
sprintf()     // No bounds checking
scanf("%s")   // No bounds checking
```

### Safe Alternatives
```c
// USE THESE INSTEAD:
strncpy(dest, src, sizeof(dest) - 1)
strncat(dest, src, sizeof(dest) - strlen(dest) - 1)
snprintf(buf, sizeof(buf), format, args)
sscanf(str, "%256s", buffer)  // Specify max length
```

### Buffer Overflow Example - BAD
```c
void process_data(const char *input) {
    char buffer[64];
    strcpy(buffer, input);  // VULNERABLE! If input > 64 bytes, overflow
    // attacker can overwrite return address on stack
}
```

### Buffer Overflow Example - GOOD
```c
void process_data(const char *input) {
    char buffer[64];
    strncpy(buffer, input, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\0';  // Ensure null termination
}
```

## Pointer Management

### Stack Pointer Returns (Use After Free)

**BAD** - Returning pointer to stack variable:
```c
int* get_value() {
    int value = 42;
    return &value;  // WRONG! 'value' goes out of scope
}
```

Once function returns, `value` is deallocated. Any use of the pointer is undefined behavior.

**GOOD** - Return by value or allocate on heap:
```c
// Option 1: Return by value
int get_value() {
    int value = 42;
    return value;  // OK
}

// Option 2: Use output parameter
void get_value(int *out_value) {
    *out_value = 42;
}

// Option 3: Allocate on heap (remember to free!)
int* get_value() {
    int *value = malloc(sizeof(int));
    *value = 42;
    return value;  // Caller must free this
}
```

### Pointer Modification Before Free

**BAD** - Modifying pointer before free:
```c
char *ptr = malloc(100);
ptr++;  // Move pointer forward
free(ptr);  // WRONG! Must free with original pointer
```

The heap allocator doesn't know where the block started, causing memory corruption.

**GOOD** - Preserve original pointer:
```c
char *ptr = malloc(100);
char *iter = ptr;  // Use iterator

while (*iter) {
    iter++;
}

free(ptr);  // Free original pointer
```

### NULL Pointer Dereferencing

**BAD**:
```c
char *buffer = malloc(100);
// ... no check if malloc returned NULL ...
strcpy(buffer, "data");  // CRASH if malloc failed!
```

**GOOD**:
```c
char *buffer = malloc(100);
if (buffer == NULL) {
    ESP_LOGE(TAG, "malloc failed");
    return ESP_ERR_NO_MEM;
}
strcpy(buffer, "data");
```

## Memory Allocation

### Allocation Error Checking

**BAD** - No error checks:
```c
int *array = malloc(1000 * sizeof(int));
array[0] = 42;  // Crashes if malloc failed!
```

**GOOD** - Always check allocation:
```c
int *array = malloc(1000 * sizeof(int));
if (array == NULL) {
    ESP_LOGE(TAG, "malloc(%d) failed", 1000 * sizeof(int));
    return ESP_ERR_NO_MEM;
}
array[0] = 42;
free(array);
```

### Realloc Gotchas

**BAD**:
```c
char *buffer = malloc(10);
// ... fill buffer ...
char *new_buffer = realloc(buffer, 20);
// If realloc fails, new_buffer is NULL but old buffer is still allocated (leak!)
free(new_buffer);  // Frees NULL, original buffer leaked
```

**GOOD**:
```c
char *buffer = malloc(10);
char *temp = realloc(buffer, 20);
if (temp == NULL) {
    ESP_LOGE(TAG, "realloc failed");
    free(buffer);  // Free original on realloc failure
    return ESP_ERR_NO_MEM;
}
buffer = temp;  // Only update after successful realloc
```

### Integer Overflow in Size Calculations

**BAD**:
```c
uint32_t count = some_large_value;
uint32_t size = count * sizeof(struct_t);  // Can overflow!
void *buffer = malloc(size);
```

**GOOD**:
```c
uint32_t count = some_large_value;
// Check for overflow before multiplication
if (count > SIZE_MAX / sizeof(struct_t)) {
    ESP_LOGE(TAG, "Size calculation would overflow");
    return ESP_ERR_INVALID_ARG;
}
void *buffer = malloc(count * sizeof(struct_t));
```

## Stack Management

### Stack Overflow from Recursion

**BAD** - No recursion limit:
```c
void recursive_process(int depth) {
    // ... do work ...
    recursive_process(depth + 1);  // Infinite recursion, stack overflow!
}
```

**GOOD** - Bounded recursion:
```c
#define MAX_DEPTH 10

void recursive_process(int depth) {
    if (depth >= MAX_DEPTH) {
        return;  // Base case
    }
    // ... do work ...
    recursive_process(depth + 1);
}
```

### Large Local Variables

**BAD** - Large stack allocation:
```c
void process_frame(void) {
    uint8_t large_buffer[10240];  // 10KB on stack! Very risky
    // ... fill buffer ...
}
```

On ESP32 with limited SRAM and typical 4KB task stacks, this can cause stack overflow.

**GOOD** - Use heap for large buffers:
```c
void process_frame(void) {
    uint8_t *large_buffer = malloc(10240);
    if (large_buffer == NULL) {
        return;
    }
    // ... fill buffer ...
    free(large_buffer);
}
```

### Stack Usage Monitoring

In FreeRTOS, monitor stack usage:
```c
UBaseType_t stack_high_water = uxTaskGetStackHighWaterMark(NULL);
ESP_LOGI(TAG, "Stack high water mark: %d words", stack_high_water);
```

## Common Mistakes

### 1. Assuming malloc Always Succeeds
```c
// BAD
char *buf = malloc(size);
strcpy(buf, data);  // Crashes if malloc returned NULL

// GOOD
char *buf = malloc(size);
if (!buf) {
    ESP_LOGE(TAG, "malloc failed");
    return ESP_ERR_NO_MEM;
}
strcpy(buf, data);
```

### 2. Memory Leaks from Early Returns
```c
// BAD
void do_work() {
    char *buffer = malloc(100);
    if (validate_something() == false) {
        return;  // LEAK! buffer not freed
    }
    // ... use buffer ...
    free(buffer);
}

// GOOD
void do_work() {
    char *buffer = malloc(100);
    if (buffer == NULL) {
        return;
    }
    
    if (validate_something() == false) {
        free(buffer);  // Free before returning
        return;
    }
    // ... use buffer ...
    free(buffer);
}

// EVEN BETTER - Use goto cleanup pattern
void do_work() {
    char *buffer = malloc(100);
    if (buffer == NULL) {
        return;
    }
    
    if (validate_something() == false) {
        goto cleanup;
    }
    // ... use buffer ...
    
cleanup:
    free(buffer);
}
```

### 3. Use-After-Free
```c
// BAD
char *ptr = malloc(100);
free(ptr);
strcpy(ptr, "data");  // Use after free!

// GOOD
char *ptr = malloc(100);
strcpy(ptr, "data");
free(ptr);
ptr = NULL;  // Nullify after freeing
```

### 4. Off-by-One Errors
```c
// BAD - Loop condition error
for (int i = 0; i <= size; i++) {
    buffer[i] = 0;  // Accesses buffer[size] which is out of bounds!
}

// GOOD
for (int i = 0; i < size; i++) {
    buffer[i] = 0;
}

// BAD - Size calculation error
char buf[MAX_SIZE];
strncpy(buf, data, MAX_SIZE);  // Should be MAX_SIZE - 1 to leave room for null terminator

// GOOD
char buf[MAX_SIZE];
strncpy(buf, data, MAX_SIZE - 1);
buf[MAX_SIZE - 1] = '\0';
```

### 5. Uninitialized Variables
```c
// BAD
void process() {
    int value;
    if (value > 10) {  // Garbage value, undefined behavior
        // ...
    }
}

// GOOD
void process() {
    int value = 0;
    if (get_value(&value) != ESP_OK) {
        return;
    }
    if (value > 10) {
        // ...
    }
}
```

## ESP32-S3 Specific Considerations

### IRAM vs DRAM
- **IRAM**: Fast instruction RAM (in-memory), limited (~400 KB on S3)
- **DRAM**: Main data RAM; more space but cache-accessed
- **PSRAM/SPIRAM**: External SPI RAM (up to 8 MB on S3); slow, cache-mediated, not DMA-safe by default

**BAD** - Large static allocation in IRAM:
```c
uint8_t large_buffer[10000] = {...};  // Wastes scarce IRAM if not forced to DRAM
```

**GOOD** - Force large static data to DRAM:
```c
static DRAM_ATTR uint8_t large_buffer[10000];  // Explicitly in DRAM
```

### PSRAM / DMA Cache Coherency

When using PSRAM (external RAM) on ESP32-S3, the CPU accesses it via a cache. DMA hardware bypasses the cache. Failing to synchronize causes stale data reads.

**BAD** - DMA result read without cache invalidation:
```c
uint8_t *buf = heap_caps_malloc(size, MALLOC_CAP_SPIRAM);
spi_device_transmit(spi, &trans);  // DMA writes to buf
process(buf);  // CPU reads stale cached values, not what DMA wrote!
```

**GOOD** - Invalidate cache after DMA write:
```c
uint8_t *buf = heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_DMA);
spi_device_transmit(spi, &trans);
esp_cache_msync(buf, size, ESP_CACHE_MSYNC_FLAG_DIR_M2C);  // Memory→Cache
process(buf);  // Now reads DMA-written data
```

**Direction flags:**
- `ESP_CACHE_MSYNC_FLAG_DIR_C2M` — Cache→Memory: flush CPU writes before DMA reads
- `ESP_CACHE_MSYNC_FLAG_DIR_M2C` — Memory→Cache: invalidate cache after DMA writes

### DMA Descriptors Must Not Be in PSRAM

DMA linked-list descriptors (used by SPI, I2S, LCD) must reside in internal DRAM.

**BAD:**
```c
dma_descriptor_t *desc = heap_caps_malloc(sizeof(*desc), MALLOC_CAP_SPIRAM);
// Hardware DMA cannot address PSRAM for descriptors — crashes silently
```

**GOOD:**
```c
dma_descriptor_t *desc = heap_caps_malloc(sizeof(*desc),
                              MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
```

### Critical Sections and ISRs
Memory access from ISR without proper synchronization:
```c
// BAD - Race condition
volatile int counter = 0;  // ISR updates, task reads
void task(void *arg) {
    while (1) {
        int val = counter;  // Can read partially updated value (16-bit arch)
    }
}

// GOOD - Protect with critical section
void task(void *arg) {
    while (1) {
        portENTER_CRITICAL();
        int val = counter;
        portEXIT_CRITICAL();
    }
}
```
