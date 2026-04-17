# FreeRTOS Best Practices for ESP32

This reference covers proper FreeRTOS usage patterns including task management, synchronization, and interrupt handling.

## Table of Contents
1. [Task Management](#task-management)
2. [Priority Assignment](#priority-assignment)
3. [Stack Management](#stack-management)
4. [Interrupt Handling](#interrupt-handling)
5. [Synchronization Primitives](#synchronization-primitives)
6. [Common Pitfalls](#common-pitfalls)

## Task Management

### Creating Tasks

**Basic Task Creation:**
```c
xTaskCreate(
    vTaskFunction,        // Function implementing the task
    "TaskName",          // Name for debugging
    512,                 // Stack size in words (2-4 KB typical)
    (void*)pvParameters, // Parameters passed to task
    uxPriority,          // Priority (0 = lowest, configMAX_PRIORITIES-1 = highest)
    (TaskHandle_t*)pxCreatedTask  // Handle for later reference
);
```

**ESP32 Specific - Pinned to Core:**
```c
xTaskCreatePinnedToCore(
    vTaskFunction,
    "TaskName",
    1024,
    NULL,
    2,                   // Priority
    NULL,
    0                    // Core affinity (0 = PRO_CPU, 1 = APP_CPU)
);
```

### Task States

```
    Ready ←→ Running
     ↑         ↓
     │      Blocked (waiting for event/delay)
     └──────────┘
     
    Suspended (manually paused)
    Deleted (cleaned up)
```

**State Transitions:**
```c
// Running → Blocked (waiting)
vTaskDelay(1000);                    // Delay for 1000 ms
xQueueReceive(queue, &item, portMAX_DELAY);  // Block until item received
xSemaphoreTake(sem, portMAX_DELAY);  // Block until semaphore available

// Blocked → Ready
// Event occurs (timer, queue item, semaphore given)

// Ready → Running
// Scheduler selects highest priority ready task

// Running → Suspended
vTaskSuspend(taskHandle);

// Suspended → Ready
vTaskResume(taskHandle);

// Any → Deleted
vTaskDelete(taskHandle);
```

## Priority Assignment

### Priority Levels

ESP32 typically has **configMAX_PRIORITIES = 25** priority levels (0-24).

**Recommended Assignment Pattern:**

```c
// Priority 4-5: Real-time critical tasks
// Examples: High-speed ADC sampling, timing-critical control
xTaskCreatePinnedToCore(
    adc_sampling_task,
    "ADC Task",
    2048,
    NULL,
    5,  // High priority
    NULL,
    0
);

// Priority 2-3: Normal operation tasks
// Examples: Sensor reading, data processing, communication
xTaskCreatePinnedToCore(
    sensor_processing_task,
    "Sensor Task",
    2048,
    NULL,
    3,  // Medium priority
    NULL,
    1
);

// Priority 1: Background tasks
// Examples: Logging, housekeeping, non-urgent monitoring
xTaskCreatePinnedToCore(
    logging_task,
    "Log Task",
    1024,
    NULL,
    1,  // Low priority
    NULL,
    1
);
```

### Priority Inversion Problem

**BAD** - Lower priority task blocks higher priority:
```c
// Task A (priority 5) - Time critical
void task_a(void *arg) {
    while (1) {
        int sensor_data = read_sensor();
        xQueueSend(queue, &sensor_data, 0);  // Blocks if queue full (set by Task B)
        vTaskDelay(10);
    }
}

// Task B (priority 2) - Background
void task_b(void *arg) {
    int data;
    while (1) {
        // If this task is running, Task A can't get CPU time!
        xQueueReceive(queue, &data, portMAX_DELAY);  // Consumes data slowly
        process_slow(data);  // Takes 100ms
    }
}
```

**GOOD** - Use priority ceiling:
```c
// Increase priority of Task B or use mutex with priority inheritance
SemaphoreHandle_t mutex = xSemaphoreCreateRecursiveMutex();  // Supports priority inheritance

void task_b(void *arg) {
    int data;
    while (1) {
        if (xQueueReceive(queue, &data, 100) == pdTRUE) {
            xSemaphoreTakeRecursive(mutex, portMAX_DELAY);
            process_with_protection(data);  // Protected, but still lower priority
            xSemaphoreGiveRecursive(mutex);
        }
    }
}
```

### Avoiding Task Starvation

**BAD** - All tasks at high priority:
```c
xTaskCreatePinnedToCore(task1, "T1", 1024, NULL, 5, NULL, 0);
xTaskCreatePinnedToCore(task2, "T2", 1024, NULL, 5, NULL, 0);
xTaskCreatePinnedToCore(task3, "T3", 1024, NULL, 5, NULL, 0);
// If none block, they round-robin. If any is CPU-intensive, lower priority tasks starve
```

**GOOD** - Varied priorities with blocking:
```c
// High: Must complete quickly
xTaskCreatePinnedToCore(isr_handler_task, "ISR", 1024, NULL, 4, NULL, 0);

// Medium: Regular operations
xTaskCreatePinnedToCore(sensor_task, "Sensor", 2048, NULL, 2, NULL, 0);
xTaskCreatePinnedToCore(wifi_task, "WiFi", 3072, NULL, 2, NULL, 0);

// Low: Non-blocking background work
xTaskCreatePinnedToCore(logging_task, "Log", 1024, NULL, 1, NULL, 1);
```

## Stack Management

### Stack Sizing

**Minimum considerations:**
- Local variables
- Function call depth (call stack)
- Library function requirements
- ISR context if critical (ISR doesn't use task stack, but understand depth)

**Typical sizes:**
- Simple polling task: 1-2 KB
- Task using standard library: 2-4 KB
- Task with deep call stacks: 4-6 KB
- Task with large local arrays: 4+ KB

### Stack Overflow Detection

**BAD** - No monitoring:
```c
xTaskCreatePinnedToCore(task, "T", 512, NULL, 1, NULL, 0);
// If task needs 600 bytes, it overflows silently until crash
```

**GOOD** - Monitor stack usage:
```c
void monitoring_task(void *arg) {
    while (1) {
        UBaseType_t hwm = uxTaskGetStackHighWaterMark(NULL);
        // hwm = minimum free bytes at any point since task started
        if (hwm < 100) {
            ESP_LOGW(TAG, "Low stack! Increase allocation");
        }
        vTaskDelay(5000);
    }
}

void app_main(void) {
    xTaskCreatePinnedToCore(monitoring_task, "Mon", 2048, NULL, 1, NULL, 1);
}
```

### Calculating Required Stack

**Example:**
```c
void complex_task(void *arg) {
    // Local variables: ~200 bytes
    uint8_t buffer[100];
    char log_msg[100];
    int values[10];
    
    // Function calls: ~20 bytes per call
    // Deep call stack could be 200-400 bytes
    
    // Library usage: depends on library
    
    // Allocation: 512 words minimum + buffer + overhead
    // Suggested: (512 + 200 + 100 + 100 + 400) / 4 ≈ 300 words minimum
    // Allocate 1024 words (4 KB) for safety
}

// Create with 1024 words = 4096 bytes
xTaskCreatePinnedToCore(complex_task, "Complex", 1024, NULL, 2, NULL, 0);
```

## Interrupt Handling

### ISR Rules

**Absolute Rules for ISRs:**
1. ✅ Keep ISRs SHORT (microseconds, not milliseconds)
2. ❌ Never block (can't call vTaskDelay, take mutex, receive queue)
3. ❌ No normal FreeRTOS functions (only `*FromISR` versions)
4. ✅ Always use `volatile` for shared variables
5. ✅ Use `*FromISR` for FreeRTOS calls
6. ✅ Call `portYIELD_FROM_ISR()` if higher priority task woken

### ISR Pattern - Signaling Task

**BAD** - Doing work in ISR:
```c
volatile int counter = 0;

void IRAM_ATTR gpio_isr_handler(void *arg) {
    // Slow work in ISR - blocks other tasks!
    for (int i = 0; i < 1000000; i++) {
        counter += i;
    }
}
```

**GOOD** - Signal task to do work:
```c
volatile int counter = 0;
SemaphoreHandle_t xSemaphore = NULL;

void IRAM_ATTR gpio_isr_handler(void *arg) {
    // Quick: just signal task
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    xSemaphoreGiveFromISR(xSemaphore, &xHigherPriorityTaskWoken);
    
    if (xHigherPriorityTaskWoken) {
        portYIELD_FROM_ISR();  // Switch to woken task immediately
    }
}

void processing_task(void *arg) {
    while (1) {
        if (xSemaphoreTake(xSemaphore, portMAX_DELAY) == pdTRUE) {
            // Now do the slow work
            for (int i = 0; i < 1000000; i++) {
                counter += i;
            }
        }
    }
}
```

### Volatile Keyword in ISR Context

**BAD** - Missing `volatile`; compiler may cache `flag` in a register and never re-read it:
```c
int flag = 0;  // NOT volatile

void IRAM_ATTR isr_handler(void *arg) {
    flag = 1;
}

void task(void *arg) {
    while (!flag) {  // With -O2, compiler may hoist this to while(1) — never sees ISR write
        vTaskDelay(10);
    }
}
```

**GOOD** - `volatile` forces a memory read on every access:
```c
volatile int flag = 0;

void IRAM_ATTR isr_handler(void *arg) {
    flag = 1;
}

void task(void *arg) {
    while (!flag) {  // Reads from memory each iteration — detects ISR write
        vTaskDelay(10);
    }
}
```

### Queue vs Semaphore vs Notification

**Use Semaphore for simple binary signal:**
```c
SemaphoreHandle_t xSemaphore = xSemaphoreCreateBinary();

void IRAM_ATTR isr_handler(void *arg) {
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    xSemaphoreGiveFromISR(xSemaphore, &xHigherPriorityTaskWoken);
    if (xHigherPriorityTaskWoken) portYIELD_FROM_ISR();
}

void task(void *arg) {
    while (1) {
        xSemaphoreTake(xSemaphore, portMAX_DELAY);
        // Event occurred
    }
}
```

**Use Queue for data transfer from ISR:**
```c
QueueHandle_t xQueue = xQueueCreate(10, sizeof(uint32_t));

void IRAM_ATTR isr_handler(void *arg) {
    uint32_t sample = read_adc();
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    xQueueSendFromISR(xQueue, &sample, &xHigherPriorityTaskWoken);
    if (xHigherPriorityTaskWoken) portYIELD_FROM_ISR();
}

void processing_task(void *arg) {
    uint32_t sample;
    while (1) {
        if (xQueueReceive(xQueue, &sample, portMAX_DELAY) == pdTRUE) {
            process_sample(sample);
        }
    }
}
```

**Use Task Notification for super lightweight signaling:**
```c
TaskHandle_t processing_handle = NULL;

void IRAM_ATTR isr_handler(void *arg) {
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    vTaskNotifyGiveFromISR(processing_handle, &xHigherPriorityTaskWoken);
    if (xHigherPriorityTaskWoken) portYIELD_FROM_ISR();
}

void processing_task(void *arg) {
    processing_handle = xTaskGetCurrentTaskHandle();
    while (1) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        // Task woken by ISR
    }
}
```

## Synchronization Primitives

### Mutex (for resource protection)

**Use when:** Only one task should access resource at a time

```c
SemaphoreHandle_t xMutex = xSemaphoreCreateMutex();

void task1(void *arg) {
    xSemaphoreTake(xMutex, portMAX_DELAY);
    // Protected access to shared resource
    modify_shared_resource();
    xSemaphoreGive(xMutex);
}

void task2(void *arg) {
    xSemaphoreTake(xMutex, portMAX_DELAY);
    // Protected access
    read_shared_resource();
    xSemaphoreGive(xMutex);
}
```

### Semaphore (for counting/signaling)

**Use when:** Resource count or event signaling

```c
SemaphoreHandle_t xSemaphore = xSemaphoreCreateCounting(3, 0);
// 3 available resources, starting at 0

void producer_task(void *arg) {
    xSemaphoreGive(xSemaphore);  // Signal event
}

void consumer_task(void *arg) {
    xSemaphoreTake(xSemaphore, portMAX_DELAY);  // Wait for event
}
```

## Common Pitfalls

### 1. Task Never Runs (Starved by Higher Priority)

**BAD:**
```c
xTaskCreatePinnedToCore(high_prio_task, "H", 1024, NULL, 5, NULL, 0);
xTaskCreatePinnedToCore(low_prio_task, "L", 1024, NULL, 0, NULL, 0);

void high_prio_task(void *arg) {
    while (1) {
        // Infinite loop, CPU intensive - never yields
        process_continuously();
    }
}

// low_prio_task never runs!
```

**GOOD** - High priority tasks must block:
```c
void high_prio_task(void *arg) {
    while (1) {
        process_continuously();
        vTaskDelay(10);  // Yield periodically
    }
}
```

### 2. Stack Overflow Silent Failure

**BAD:**
```c
xTaskCreatePinnedToCore(task_with_arrays, "T", 512, NULL, 2, NULL, 0);

void task_with_arrays(void *arg) {
    uint8_t buffer1[200];
    uint8_t buffer2[200];
    uint8_t buffer3[200];  // 600 bytes total > 512 word stack!
    // Undefined behavior, may crash at any time
}
```

**GOOD** - Verify stack needs:
```c
// Calculate: 512 words * 4 bytes/word = 2048 bytes
// If task needs ~600 bytes, allocate 1024+ words (4096+ bytes)
xTaskCreatePinnedToCore(task_with_arrays, "T", 1024, NULL, 2, NULL, 0);

void task_with_arrays(void *arg) {
    uint8_t *buffer1 = malloc(200);  // Or use heap
    // ...
    free(buffer1);
}
```

### 3. Forgetting to Store Task Handle

**BAD** - Can't control task later:
```c
xTaskCreatePinnedToCore(my_task, "T", 1024, NULL, 2, NULL, NULL);
// Lost handle, can't suspend/resume/delete this task
```

**GOOD** - Store handle if you need it:
```c
TaskHandle_t my_task_handle = NULL;
xTaskCreatePinnedToCore(my_task, "T", 1024, NULL, 2, NULL, &my_task_handle);

// Later, can control it
vTaskSuspend(my_task_handle);
vTaskResume(my_task_handle);
vTaskDelete(my_task_handle);
```

### 4. Blocking in ISR (Impossible but Common Mistake)

**BAD** - Won't compile/work, but shows misunderstanding:
```c
SemaphoreHandle_t xMutex = xSemaphoreCreateMutex();

void IRAM_ATTR isr_handler(void *arg) {
    xSemaphoreTake(xMutex, portMAX_DELAY);  // WRONG! Can't block in ISR
    modify_data();
    xSemaphoreGive(xMutex);
}
```

**GOOD** - Signal task to do protected work:
```c
void IRAM_ATTR isr_handler(void *arg) {
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    xSemaphoreGiveFromISR(xWakeup, &xHigherPriorityTaskWoken);
    if (xHigherPriorityTaskWoken) portYIELD_FROM_ISR();
}

void protected_task(void *arg) {
    while (1) {
        xSemaphoreTake(xWakeup, portMAX_DELAY);
        
        xSemaphoreTake(xMutex, portMAX_DELAY);
        modify_data();  // Now protected
        xSemaphoreGive(xMutex);
    }
}
```

### 5. Deadlock from Circular Wait

**BAD** - Task A waits for Semaphore B, Task B waits for Semaphore A:
```c
SemaphoreHandle_t sem_a = xSemaphoreCreateBinary();
SemaphoreHandle_t sem_b = xSemaphoreCreateBinary();

void task_1(void *arg) {
    xSemaphoreTake(sem_a, portMAX_DELAY);
    // ...
    xSemaphoreTake(sem_b, portMAX_DELAY);  // Waits forever if task_2 has sem_b
}

void task_2(void *arg) {
    xSemaphoreTake(sem_b, portMAX_DELAY);
    // ...
    xSemaphoreTake(sem_a, portMAX_DELAY);  // Waits forever if task_1 has sem_a
}
```

**GOOD** - Always acquire in same order:
```c
void task_1(void *arg) {
    xSemaphoreTake(sem_a, portMAX_DELAY);
    xSemaphoreTake(sem_b, portMAX_DELAY);  // Always A before B
    // ...
    xSemaphoreGive(sem_b);
    xSemaphoreGive(sem_a);
}

void task_2(void *arg) {
    xSemaphoreTake(sem_a, portMAX_DELAY);  // Always A before B
    xSemaphoreTake(sem_b, portMAX_DELAY);
    // ...
    xSemaphoreGive(sem_b);
    xSemaphoreGive(sem_a);
}
```
